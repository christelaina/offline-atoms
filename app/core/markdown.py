from __future__ import annotations

import html
import re
from pathlib import Path


TAG_RE = re.compile(r"(?<!\w)#([A-Za-z0-9_/-]+)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]")


def render_markdown_to_html(markdown: str) -> str:
    text = html.escape(markdown)
    text = re.sub(r"^### (.*)$", r"<h3>\1</h3>", text, flags=re.MULTILINE)
    text = re.sub(r"^## (.*)$", r"<h2>\1</h2>", text, flags=re.MULTILINE)
    text = re.sub(r"^# (.*)$", r"<h1>\1</h1>", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\[\[([^\]|#]+?)(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]", r"<a href='\1'>\3\1</a>", text)

    blocks: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        if not paragraph.strip():
            continue
        if paragraph.lstrip().startswith("<h") or paragraph.lstrip().startswith("<ul>") or paragraph.lstrip().startswith("<ol>") or paragraph.lstrip().startswith("<pre>"):
            blocks.append(paragraph)
            continue
        if paragraph.strip().startswith("- "):
            items = "\n".join(f"<li>{item.strip()}</li>" for item in paragraph.splitlines() if item.strip())
            blocks.append(f"<ul>{items}</ul>")
            continue
        blocks.append(f"<p>{paragraph.strip()}</p>")

    return "\n".join(blocks)


def extract_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}, text

    lines = text.splitlines(keepends=True)
    if len(lines) < 2:
        return {}, text

    if lines[0].strip() != "---":
        return {}, text

    end_index = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_index = idx
            break
    if end_index is None:
        return {}, text

    frontmatter_block = "".join(lines[1:end_index])
    body = "".join(lines[end_index + 1 :])

    metadata: dict[str, str] = {}
    current_key: str | None = None
    list_buffer: list[str] = []

    def flush_list() -> None:
        nonlocal current_key, list_buffer
        if current_key is not None:
            metadata[current_key] = ", ".join(list_buffer)
            current_key = None
            list_buffer = []

    for raw_line in frontmatter_block.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue

        if stripped.startswith("-"):
            if current_key is None:
                continue
            value = stripped[1:].strip()
            if value:
                list_buffer.append(value)
            continue

        if ":" in stripped:
            flush_list()
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value:
                metadata[key] = value
            else:
                current_key = key
                list_buffer = []

    flush_list()
    return metadata, body


def extract_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        match = re.match(r"^#\s+(.*)$", line.strip())
        if match:
            return match.group(1).strip()
    return fallback


def extract_headings(text: str) -> list[str]:
    headings: list[str] = []
    for line in text.splitlines():
        match = HEADING_RE.match(line.strip())
        if match:
            headings.append(match.group(2).strip())
    return headings


def extract_tags(text: str) -> list[str]:
    return [match.group(1) for match in TAG_RE.finditer(text)]


def extract_wikilinks(text: str) -> list[str]:
    links: list[str] = []
    for match in WIKILINK_RE.finditer(text):
        target = match.group(1).strip()
        heading = match.group(2)
        if heading:
            target = f"{target}#{heading}"
        if target:
            links.append(target)
    return links


def read_note(path: Path) -> tuple[str, dict[str, str], str, list[str], list[str], list[str]]:
    content = path.read_text(encoding="utf-8", errors="replace")
    frontmatter, body = extract_frontmatter(content)
    title = extract_title(body, path.stem)
    headings = extract_headings(body)
    tags = extract_tags(body)
    wikilinks = extract_wikilinks(body)
    return title, frontmatter, body, headings, tags, wikilinks
