"""
Markdown Parser: Convert Markdown to hierarchical MarkdownBlock objects
"""
from dataclasses import dataclass, field
from typing import Union, Optional
import re


@dataclass
class MarkdownBlock:
    """Output unit of the parsing stage"""
    block_id: str
    heading_path: list[str]      # Heading path this block belongs to
    heading_level: int          # Heading level: 1=H1, 2=H2, 3=H3...
    block_type: str             # "text" | "table" | "code" | "ordered_list" | "unordered_list"

    # For text blocks
    content: Optional[str] = None

    # For ordered_list / unordered_list
    items: list[Union[str, "MarkdownBlock"]] = field(default_factory=list)

    # For table blocks
    table_headers: Optional[list[str]] = None
    table_rows: Optional[list[list[str]]] = None

    # For code blocks
    code: Optional[str] = None
    code_lang: Optional[str] = None

    # Source info
    source_url: Optional[str] = None
    raw_markdown: Optional[str] = None  # Raw markdown (for debugging)


class MarkdownParser:
    """Parse Markdown into list[MarkdownBlock]"""

    MAX_NESTING_DEPTH = 3  # Flatten beyond this depth

    def __init__(self, source_url: str = ""):
        self.source_url = source_url
        self.block_counter = 0

    def _new_block_id(self) -> str:
        self.block_counter += 1
        return f"b_{self.block_counter}"

    def _current_heading_path(self, blocks: list[MarkdownBlock]) -> list[str]:
        """Infer current heading_path from already-parsed blocks"""
        path = []
        for b in blocks:
            if b.heading_level > len(path):
                path.append(b.content.split('\n')[0] if b.content else "")
        return path

    def parse(self, markdown_text: str) -> list[MarkdownBlock]:
        """
        Main entry: parse Markdown text into list[MarkdownBlock]
        """
        blocks = []
        lines = markdown_text.split('\n')
        current_headings = {}  # heading_level -> heading_text

        i = 0
        while i < len(lines):
            line = lines[i]

            # Skip empty lines
            if not line.strip():
                i += 1
                continue

            # Parse headings (H1-H6)
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if heading_match:
                level = len(heading_match.group(1))
                text = heading_match.group(2).strip()
                current_headings[level] = text
                # Remove all headings below current level
                current_headings = {k: v for k, v in current_headings.items() if k <= level}
                heading_path = [current_headings.get(l, "") for l in range(1, level + 1)]

                block = MarkdownBlock(
                    block_id=self._new_block_id(),
                    heading_path=heading_path,
                    heading_level=level,
                    block_type="text",
                    content=text,
                    source_url=self.source_url,
                    raw_markdown=line,
                )
                blocks.append(block)
                i += 1
                continue

            # Parse code blocks
            if line.strip().startswith('```'):
                lang = line.strip()[3:]
                if not lang:
                    lang = "text"
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith('```'):
                    code_lines.append(lines[i])
                    i += 1
                heading_path = [current_headings.get(l, "") for l in range(1, max(current_headings.keys()) + 1)] if current_headings else []

                block = MarkdownBlock(
                    block_id=self._new_block_id(),
                    heading_path=heading_path,
                    heading_level=max(current_headings.keys()) if current_headings else 1,
                    block_type="code",
                    code="\n".join(code_lines),
                    code_lang=lang,
                    source_url=self.source_url,
                    raw_markdown="\n".join(["```" + lang] + code_lines + ["```"]),
                )
                blocks.append(block)
                i += 1
                continue

            # Parse tables
            if self._looks_like_table_header(lines, i):
                table_result = self._parse_table(lines, i, current_headings)
                if table_result:
                    blocks.append(table_result[0])
                    i = table_result[1]
                    continue

            # Parse ordered lists
            ordered_match = re.match(r'^(\d+)\.\s+(.+)$', line)
            if ordered_match:
                list_result = self._parse_ordered_list(lines, i, current_headings)
                blocks.append(list_result[0])
                i = list_result[1]
                continue

            # Parse unordered lists
            if re.match(r'^[-*+]\s+', line):
                list_result = self._parse_unordered_list(lines, i, current_headings)
                blocks.append(list_result[0])
                i = list_result[1]
                continue

            # Regular paragraphs: collect consecutive non-special lines
            paragraph_lines = []
            paragraph_start = i
            while (i < len(lines) and
                   lines[i].strip() and
                   not re.match(r'^(#{1,6})\s+', lines[i]) and
                   not lines[i].strip().startswith('```') and
                   not self._looks_like_table_header(lines, i) and
                   not re.match(r'^(\d+)\.\s+', lines[i]) and
                   not re.match(r'^[-*+]\s+', lines[i])):
                paragraph_lines.append(lines[i])
                i += 1

            if paragraph_lines:
                heading_path = [current_headings.get(l, "") for l in range(1, max(current_headings.keys()) + 1)] if current_headings else []
                block = MarkdownBlock(
                    block_id=self._new_block_id(),
                    heading_path=heading_path,
                    heading_level=max(current_headings.keys()) if current_headings else 1,
                    block_type="text",
                    content="\n".join(paragraph_lines),
                    source_url=self.source_url,
                    raw_markdown="\n".join(paragraph_lines),
                )
                blocks.append(block)

        return blocks

    def _looks_like_table_header(self, lines: list[str], start: int) -> bool:
        """Return True when current line is likely a markdown table header."""
        line = lines[start].strip()
        if "|" not in line:
            return False

        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            return False

        if start + 1 < len(lines):
            separator = lines[start + 1].strip()
            if re.match(r'^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$', separator):
                return True

        return line.startswith("|") and line.endswith("|")

    def _parse_table(self, lines: list[str], start: int, current_headings: dict) -> tuple:
        """Parse table, return (block, next_line_index)"""
        header_line = lines[start]
        headers = [h.strip() for h in header_line.strip().strip("|").split("|")]

        # Skip separator row
        i = start + 1
        if i < len(lines) and re.match(r'^\|[-:\s|]+\|$', lines[i]):
            i += 1

        rows = []
        while i < len(lines) and "|" in lines[i]:
            row = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            rows.append(row)
            i += 1

        heading_path = [current_headings.get(l, "") for l in range(1, max(current_headings.keys()) + 1)] if current_headings else []

        block = MarkdownBlock(
            block_id=self._new_block_id(),
            heading_path=heading_path,
            heading_level=max(current_headings.keys()) if current_headings else 1,
            block_type="table",
            table_headers=headers,
            table_rows=rows,
            source_url=self.source_url,
            raw_markdown="\n".join(lines[start:i]),
        )
        return (block, i)

    def _parse_ordered_list(self, lines: list[str], start: int, current_headings: dict) -> tuple:
        """Parse ordered list, return (block, next_line_index)"""
        items = []
        i = start

        while i < len(lines):
            line = lines[i]
            match = re.match(r'^(\d+)\.\s+(.*)$', line)
            if not match:
                break

            content = match.group(2).strip()
            # Check for nested lists
            nested_items = []
            if i + 1 < len(lines) and re.match(r'^\s+[-*+]\s+', lines[i + 1]):
                i += 1
                while i < len(lines) and re.match(r'^\s+[-*+]\s+', lines[i]):
                    nested_match = re.match(r'^\s+[-*+]\s+(.*)$', lines[i])
                    if nested_match:
                        nested_items.append(nested_match.group(1).strip())
                    i += 1
                # Step back one line since outer loop will i+=1
                i -= 1

            if nested_items:
                nested_text = "\n".join(f"  - {item}" for item in nested_items)
                items.append(f"{content}\n{nested_text}")
            else:
                items.append(content)
            i += 1

        heading_path = [current_headings.get(l, "") for l in range(1, max(current_headings.keys()) + 1)] if current_headings else []

        block = MarkdownBlock(
            block_id=self._new_block_id(),
            heading_path=heading_path,
            heading_level=max(current_headings.keys()) if current_headings else 1,
            block_type="ordered_list",
            items=items,
            source_url=self.source_url,
        )
        return (block, i)

    def _parse_unordered_list(self, lines: list[str], start: int, current_headings: dict) -> tuple:
        """Parse unordered list, return (block, next_line_index)"""
        items = []
        i = start

        while i < len(lines):
            line = lines[i]
            match = re.match(r'^([-*+])\s+(.*)$', line)
            if not match:
                break
            items.append(match.group(2).strip())
            i += 1

        heading_path = [current_headings.get(l, "") for l in range(1, max(current_headings.keys()) + 1)] if current_headings else []

        block = MarkdownBlock(
            block_id=self._new_block_id(),
            heading_path=heading_path,
            heading_level=max(current_headings.keys()) if current_headings else 1,
            block_type="unordered_list",
            items=items,
            source_url=self.source_url,
        )
        return (block, i)


def flatten_block(block: MarkdownBlock, depth: int = 0) -> str:
    """
    Flatten MarkdownBlock into linear text for embedding
    """
    indent = "  " * depth

    if block.block_type == "text":
        return block.content or ""

    elif block.block_type == "unordered_list":
        lines = []
        for item in (block.items or []):
            if isinstance(item, str):
                lines.append(f"{indent}- {item}")
            else:
                lines.append(flatten_block(item, depth + 1))
        return "\n".join(lines)

    elif block.block_type == "ordered_list":
        lines = []
        for i, item in enumerate(block.items or [], 1):
            if isinstance(item, str):
                lines.append(f"{indent}{i}. {item}")
            else:
                lines.append(flatten_block(item, depth))
        return "\n".join(lines)

    elif block.block_type == "table":
        lines = [
            f"{indent}Table: {', '.join(block.table_headers or [])}",
        ]
        for row in (block.table_rows or [])[:3]:
            lines.append(f"{indent}  Row: {', '.join(str(c) for c in row)}")
        if len(block.table_rows or []) > 3:
            lines.append(f"{indent}  ... and {len(block.table_rows) - 3} more rows")
        return "\n".join(lines)

    elif block.block_type == "code":
        return f"{indent}Code ({block.code_lang}):\n{indent}{block.code}"

    return ""


def block_to_embedding_text(block: MarkdownBlock) -> str:
    """Generate text for embedding"""
    heading = " > ".join([h for h in block.heading_path if h])
    body = flatten_block(block)
    if heading:
        return f"[{heading}]\n{body}"
    return body
