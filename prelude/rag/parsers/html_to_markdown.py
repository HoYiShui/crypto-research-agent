"""
HTML to Markdown Converter
"""
from pathlib import Path
from typing import Optional
from bs4 import BeautifulSoup, NavigableString, Tag
import re


def html_to_markdown(html: str, base_url: str = "") -> str:
    """
    Convert HTML to Markdown using markdownify library
    """
    try:
        import markdownify
        converter = HTMLToMarkdownConverter(use_markdownify=True)
        return converter.convert(html, base_url=base_url)
    except ImportError:
        print("Please install markdownify: pip install markdownify")
        return ""


def html_to_markdown_manual(html: str) -> str:
    """
    Manual HTML -> Markdown converter (fallback when markdownify unavailable)
    """
    soup = BeautifulSoup(html, "html.parser")
    lines = []

    def process_element(element, indent=0):
        if isinstance(element, NavigableString):
            text = str(element).strip()
            if text:
                return text
            return ""

        if not isinstance(element, Tag):
            return ""

        tag_name = element.name.lower()

        if tag_name in ["script", "style", "nav", "footer", "header"]:
            return ""  # Skip these tags

        if tag_name == "h1":
            return f"# {element.get_text().strip()}\n"
        elif tag_name == "h2":
            return f"## {element.get_text().strip()}\n"
        elif tag_name == "h3":
            return f"### {element.get_text().strip()}\n"
        elif tag_name == "h4":
            return f"#### {element.get_text().strip()}\n"
        elif tag_name == "h5":
            return f"##### {element.get_text().strip()}\n"
        elif tag_name == "h6":
            return f"###### {element.get_text().strip()}\n"

        elif tag_name == "p":
            return f"{element.get_text().strip()}\n\n"

        elif tag_name == "code":
            if element.parent and element.parent.name == "pre":
                lang = element.get("class", [""])[0].replace("language-", "") if element.get("class") else ""
                return f"```{lang}\n{element.get_text()}\n```\n"
            return f"`{element.get_text()}`"

        elif tag_name == "pre":
            code = element.find("code")
            if code:
                lang = code.get("class", [""])[0].replace("language-", "") if code.get("class") else ""
                return f"```{lang}\n{code.get_text()}\n```\n"
            return f"```\n{element.get_text()}\n```\n"

        elif tag_name == "a":
            href = element.get("href", "")
            text = element.get_text().strip()
            if href:
                return f"[{text}]({href})"
            return text

        elif tag_name == "strong" or tag_name == "b":
            return f"**{element.get_text()}**"

        elif tag_name == "em" or tag_name == "i":
            return f"*{element.get_text()}*"

        elif tag_name == "ul":
            items = []
            for li in element.find_all("li", recursive=False):
                items.append(f"- {li.get_text().strip()}")
            return "\n".join(items) + "\n\n"

        elif tag_name == "ol":
            items = []
            for i, li in enumerate(element.find_all("li", recursive=False), 1):
                items.append(f"{i}. {li.get_text().strip()}")
            return "\n".join(items) + "\n\n"

        elif tag_name == "blockquote":
            text = element.get_text().strip()
            return f"> {text}\n\n"

        elif tag_name == "table":
            return parse_table(element)

        elif tag_name == "br":
            return "\n"

        elif tag_name == "hr":
            return "---\n\n"

        elif tag_name == "div":
            # Recursively process div content
            parts = []
            for child in element.children:
                part = process_element(child, indent)
                if part:
                    parts.append(part)
            return "\n".join(parts)

        else:
            # Other tags, recursively process children
            parts = []
            for child in element.children:
                part = process_element(child, indent)
                if part:
                    parts.append(part)
            return "".join(parts)

    def parse_table(table: Tag) -> str:
        rows = table.find_all("tr")
        if not rows:
            return ""

        lines = []
        for row in rows:
            cells = row.find_all(["th", "td"])
            cell_texts = [c.get_text().strip() for c in cells]
            lines.append("| " + " | ".join(cell_texts) + " |")

            # First row is header, add separator
            if rows.index(row) == 0:
                lines.append("| " + " | ".join(["---"] * len(cell_texts)) + " |")

        return "\n".join(lines) + "\n\n"

    body = soup.find("body") or soup
    result = process_element(body)
    return result


class HTMLToMarkdownConverter:
    """HTML to Markdown converter"""

    def __init__(self, use_markdownify: bool = True):
        self.use_markdownify = use_markdownify

    @staticmethod
    def _extract_primary_content(html: str) -> BeautifulSoup:
        """
        Extract the most relevant document body before markdown conversion.

        For GitBook-like pages, prefer:
        - <main> direct <header> (page title and heading context)
        - <main> direct content container "div.whitespace-pre-wrap"
        """
        soup = BeautifulSoup(html, "html.parser")

        main = soup.select_one("main")
        if main is not None:
            header = main.find("header", recursive=False)
            content = main.select_one("div.whitespace-pre-wrap")
            if content is not None:
                merged_html_parts = []
                if header is not None:
                    merged_html_parts.append(str(header))
                merged_html_parts.append(str(content))
                return BeautifulSoup("\n".join(merged_html_parts), "html.parser")

            # Fallback: main as-is
            return BeautifulSoup(str(main), "html.parser")

        # Generic fallback selectors
        for selector in ("article", "[role='main']", ".content", "#content"):
            node = soup.select_one(selector)
            if node is not None:
                return BeautifulSoup(str(node), "html.parser")

        body = soup.find("body")
        return BeautifulSoup(str(body) if body else html, "html.parser")

    @staticmethod
    def _remove_ui_noise_nodes(soup: BeautifulSoup) -> None:
        selectors = [
            "script",
            "style",
            "noscript",
            "nav",
            "footer",
            "aside",
            "button",
            "svg",
            "[data-testid='table-of-contents']",
            "[data-testid='toc-button']",
            "[data-testid='toc-scroll-container']",
            "[data-testid='search-input']",
            "[data-testid='gb-trademark']",
            "[aria-label*='Copy']",
            "[aria-label*='copy']",
        ]
        for selector in selectors:
            for node in soup.select(selector):
                node.decompose()

    @staticmethod
    def _normalize_role_tables(soup: BeautifulSoup) -> None:
        """
        Convert ARIA table markup (<div role="table">) to semantic <table> tags.
        This allows markdownify + MarkdownParser to produce true table blocks.
        """
        for role_table in list(soup.select("[role='table']")):
            rows = role_table.select("[role='row']")
            if not rows:
                continue

            table = soup.new_tag("table")
            thead = soup.new_tag("thead")
            tbody = soup.new_tag("tbody")
            header_done = False

            for row in rows:
                cells = row.select("[role='columnheader'], [role='rowheader'], [role='cell']")
                if not cells:
                    continue

                is_header_row = (not header_done) and any(c.get("role") == "columnheader" for c in cells)
                tr = soup.new_tag("tr")
                cell_tag = "th" if is_header_row else "td"

                for cell in cells:
                    out_cell = soup.new_tag(cell_tag)
                    out_cell.string = cell.get_text(" ", strip=True)
                    tr.append(out_cell)

                if is_header_row:
                    thead.append(tr)
                    header_done = True
                else:
                    tbody.append(tr)

            # If no explicit header row exists, promote first body row as header.
            if not header_done:
                first = tbody.find("tr")
                if first is not None:
                    header_tr = soup.new_tag("tr")
                    for td in first.find_all("td", recursive=False):
                        th = soup.new_tag("th")
                        th.string = td.get_text(" ", strip=True)
                        header_tr.append(th)
                    thead.append(header_tr)
                    first.decompose()

            if thead.find("tr") is not None:
                table.append(thead)
            if tbody.find("tr") is not None:
                table.append(tbody)

            if table.find("tr") is not None:
                role_table.replace_with(table)

    @staticmethod
    def _clean_markdown_lines(markdown_text: str) -> str:
        lines = markdown_text.splitlines()

        # Trim leading UI/breadcrumb noise before first heading, if heading exists.
        first_heading_idx = None
        for i, line in enumerate(lines):
            if re.match(r"^\s*#{1,6}\s+\S", line):
                first_heading_idx = i
                break
        if first_heading_idx is not None and first_heading_idx > 0:
            lines = lines[first_heading_idx:]

        def is_ui_noise_line(raw: str) -> bool:
            s = raw.strip()
            if not s:
                return False
            low = s.lower()

            if low.startswith("last updated "):
                return True
            if low.startswith("[previous") and "][next" in low:
                return True
            if "powered by gitbook" in low:
                return True

            normalized = re.sub(r"[^a-z0-9]+", "", low)
            ui_tokens = {
                "copy",
                "copycopychevrondown",
                "search",
                "circlexmark",
                "xmark",
                "chevrondown",
                "chevronup",
                "chevronleftchevronright",
                "circleinfo",
                "blockquoteonthispagechevrondown",
            }
            return normalized in ui_tokens

        cleaned: list[str] = []
        for line in lines:
            if is_ui_noise_line(line):
                continue
            cleaned.append(line)

        return "\n".join(cleaned).strip() + "\n"

    def convert(self, html: str, base_url: str = "") -> str:
        if self.use_markdownify:
            try:
                import markdownify

                primary = self._extract_primary_content(html)
                self._remove_ui_noise_nodes(primary)
                self._normalize_role_tables(primary)

                md = markdownify.markdownify(
                    str(primary),
                    heading_style="ATX",
                    base_url=base_url,
                )
                return self._clean_markdown_lines(md)
            except ImportError:
                print("markdownify unavailable, using manual converter")
                return html_to_markdown_manual(html)
        else:
            return html_to_markdown_manual(html)

    def convert_file(self, html_path: str, output_path: str = None):
        """Convert a single HTML file"""
        html = Path(html_path).read_text()
        md = self.convert(html)
        if output_path:
            Path(output_path).write_text(md)
        return md


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        html_path = sys.argv[1]
        converter = HTMLToMarkdownConverter()
        md = converter.convert_file(html_path)
        print(md[:500])
