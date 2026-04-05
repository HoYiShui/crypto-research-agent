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
        md = markdownify.markdownify(
            html,
            heading_style="ATX",
            base_url=base_url,
        )
        return md
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

    def convert(self, html: str, base_url: str = "") -> str:
        if self.use_markdownify:
            try:
                import markdownify
                return markdownify.markdownify(html, heading_style="ATX", base_url=base_url)
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
