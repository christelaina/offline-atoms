from __future__ import annotations

import html
import json
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
            parsed_values: list[str] = []
            for value in list_buffer:
                if value.startswith('"'):
                    try:
                        value = str(json.loads(value))
                    except json.JSONDecodeError:
                        pass
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1].replace("''", "'")
                parsed_values.append(value)
            metadata[current_key] = ", ".join(parsed_values)
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
                if value.startswith('"'):
                    try:
                        value = str(json.loads(value))
                    except json.JSONDecodeError:
                        pass
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1].replace("''", "'")
                elif value.startswith("[") and value.endswith("]"):
                    try:
                        parsed_list = json.loads(value)
                        if isinstance(parsed_list, list):
                            value = ", ".join(str(item) for item in parsed_list)
                    except json.JSONDecodeError:
                        pass
                metadata[key] = value
            else:
                current_key = key
                list_buffer = []

    flush_list()
    return metadata, body


def set_frontmatter(text: str, metadata: dict[str, str]) -> str:
    _, body = extract_frontmatter(text)
    if not metadata:
        return body

    lines = ["---"]
    list_properties = {"tags", "aliases", "cssclasses"}
    for raw_key, raw_value in metadata.items():
        key = raw_key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key):
            raise ValueError(f"Invalid frontmatter property name: {raw_key}")
        value = str(raw_value)
        if key.lower() in list_properties:
            values = [item.strip() for item in value.split(",") if item.strip()]
            if values:
                lines.append(f"{key}:")
                lines.extend(f"  - {json.dumps(item, ensure_ascii=False)}" for item in values)
            else:
                lines.append(f"{key}: []")
        elif re.fullmatch(
            r"(?:true|false|null|[-+]?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][-+]?\d+)?|\d{4}-\d{2}-\d{2})",
            value,
            flags=re.IGNORECASE,
        ):
            lines.append(f"{key}: {value}")
        else:
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body


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
