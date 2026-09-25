from __future__ import annotations

from dataclasses import dataclass
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPalette,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import QTextEdit, QToolTip

from app.core.markdown import HEADING_RE, TAG_RE, WIKILINK_RE


@dataclass(frozen=True)
class MarkdownSpan:
    kind: str
    start: int
    end: int
    content_start: int
    content_end: int


class MarkdownDocumentParser:
    """Find Markdown source ranges without converting or rewriting the text."""

    NORMAL = 0
    FRONTMATTER = 1
    FENCE_STATE_BASE = 10

    def parse_block(
        self, text: str, previous_state: int = NORMAL, first_block: bool = False
    ) -> tuple[list[MarkdownSpan], int]:
        stripped = text.strip()
        if previous_state == self.FRONTMATTER:
            spans = [MarkdownSpan("frontmatter", 0, len(text), 0, len(text))]
            if stripped == "---":
                spans.append(MarkdownSpan("syntax", 0, len(text), 0, len(text)))
                return spans, self.NORMAL
            return spans, self.FRONTMATTER
        if first_block and stripped == "---":
            return [
                MarkdownSpan("frontmatter", 0, len(text), 0, len(text)),
                MarkdownSpan("syntax", 0, len(text), 0, len(text)),
            ], self.FRONTMATTER
        if previous_state >= self.FENCE_STATE_BASE:
            fence_value = previous_state - self.FENCE_STATE_BASE
            fence_char = "~" if fence_value % 2 else "`"
            fence_length = fence_value // 2
            closing_match = re.match(r"^\s*(`+|~+)\s*$", text)
            closing = bool(
                closing_match
                and closing_match.group(1)[0] == fence_char
                and len(closing_match.group(1)) >= fence_length
            )
            spans = [MarkdownSpan("code_block", 0, len(text), 0, len(text))]
            if closing:
                spans.append(MarkdownSpan("syntax", 0, len(text), 0, len(text)))
            return spans, self.NORMAL if closing else previous_state
        fence_match = re.match(r"^\s*(`{3,}|~{3,})(.*)$", text)
        if fence_match:
            fence = fence_match.group(1)
            return [
                MarkdownSpan("code_block", 0, len(text), 0, len(text)),
                MarkdownSpan("syntax", 0, len(text), 0, len(text)),
            ], self.FENCE_STATE_BASE + len(fence) * 2 + (1 if fence[0] == "~" else 0)
        if not stripped:
            return [], self.NORMAL
        if self._is_horizontal_rule(stripped):
            return [
                MarkdownSpan("horizontal_rule", 0, len(text), 0, len(text)),
                MarkdownSpan("syntax", 0, len(text), 0, len(text)),
            ], self.NORMAL

        block_spans: list[MarkdownSpan] = []
        heading = HEADING_RE.match(text)
        if heading:
            content_start = len(heading.group(1))
            while content_start < len(text) and text[content_start].isspace():
                content_start += 1
            block_spans.append(MarkdownSpan("heading", 0, len(text), content_start, len(text)))
            if content_start:
                block_spans.append(MarkdownSpan("syntax", 0, content_start, 0, content_start))
            block_spans.extend(self._parse_inline(text, content_start))
            return block_spans, self.NORMAL

        quote = self._quote_prefix_length(text)
        if quote:
            block_spans.append(MarkdownSpan("blockquote", 0, len(text), quote, len(text)))
            block_spans.append(MarkdownSpan("syntax", 0, quote, 0, quote))

        list_match = self._list_match(text)
        if list_match:
            marker_start = list_match.start(2)
            marker_end = list_match.end()
            block_spans.append(MarkdownSpan("list", 0, len(text), marker_end, len(text)))
            block_spans.append(MarkdownSpan("syntax", marker_start, marker_end, marker_start, marker_end))

        inline_start = max(quote, list_match.end() if list_match else 0)
        block_spans.extend(self._parse_inline(text, inline_start))
        return block_spans, self.NORMAL

    def parse(self, text: str) -> list[MarkdownSpan]:
        spans: list[MarkdownSpan] = []
        offset = 0
        state = self.NORMAL
        for index, line in enumerate(text.splitlines(keepends=True)):
            content = line.rstrip("\r\n")
            line_spans, state = self.parse_block(content, state, index == 0)
            spans.extend(
                MarkdownSpan(
                    span.kind,
                    span.start + offset,
                    span.end + offset,
                    span.content_start + offset,
                    span.content_end + offset,
                )
                for span in line_spans
            )
            offset += len(line)
        return spans

    @staticmethod
    def _is_horizontal_rule(text: str) -> bool:
        compact = text.replace(" ", "").replace("\t", "")
        return len(compact) >= 3 and set(compact) in ({"-"}, {"*"}, {"_"})

    @staticmethod
    def _quote_prefix_length(text: str) -> int:
        index = 0
        while index < len(text) and text[index].isspace():
            index += 1
        if index < len(text) and text[index] == ">":
            index += 1
            if index < len(text) and text[index] == " ":
                index += 1
            return index
        return 0

    @staticmethod
    def _list_match(text: str):
        return re.match(r"^(\s*)([-+*]|\d+[.)])(\s+)", text)

    def _parse_inline(self, text: str, start: int = 0, end: int | None = None) -> list[MarkdownSpan]:
        spans: list[MarkdownSpan] = []
        end = len(text) if end is None else min(end, len(text))
        index = start
        while index < end:
            wiki = WIKILINK_RE.match(text, index)
            if wiki and wiki.end() <= end:
                kind = "wikilink_alias" if wiki.group(3) is not None else "wikilink"
                content_start, content_end = (
                    (wiki.start(3), wiki.end(3)) if wiki.group(3) is not None
                    else (wiki.start(1), wiki.end(1))
                )
                spans.append(MarkdownSpan(kind, index, wiki.end(), content_start, content_end))
                spans.append(MarkdownSpan("syntax", index, index + 2, index, index + 2))
                spans.append(MarkdownSpan("syntax", wiki.end() - 2, wiki.end(), wiki.end() - 2, wiki.end()))
                if wiki.group(3) is not None:
                    spans.append(MarkdownSpan("syntax", index + 2, wiki.start(3), index + 2, wiki.start(3)))
                index = wiki.end()
                continue

            if text[index] == "`" and not self._is_escaped(text, index):
                ticks = 1
                while index + ticks < len(text) and text[index + ticks] == "`":
                    ticks += 1
                closing_start, closing_end = self._find_backtick_run(text, index + ticks, ticks, end)
                if closing_start >= 0:
                    spans.append(MarkdownSpan("inline_code", index, closing_end, index + ticks, closing_start))
                    spans.append(MarkdownSpan("syntax", index, index + ticks, index, index + ticks))
                    spans.append(MarkdownSpan("syntax", closing_start, closing_end, closing_start, closing_end))
                    index = closing_end
                    continue

            if text[index] == "[" and not text.startswith("[[", index):
                label_end = text.find("](", index + 1)
                link_end = text.find(")", label_end + 2, end) if label_end >= 0 else -1
                if label_end >= 0 and link_end >= 0:
                    spans.append(MarkdownSpan("markdown_link", index, link_end + 1, index + 1, label_end))
                    spans.append(MarkdownSpan("syntax", index, index + 1, index, index + 1))
                    spans.append(MarkdownSpan("syntax", label_end, link_end + 1, label_end, link_end + 1))
                    index = link_end + 1
                    continue

            delimiter = self._emphasis_delimiter(text, index)
            if delimiter:
                closing = text.rfind(delimiter, index + len(delimiter), end)
                if closing > index + len(delimiter):
                    kind = {
                        "***": "bold_italic", "___": "bold_italic",
                        "**": "bold", "__": "bold", "~~": "strike",
                        "*": "italic", "_": "italic",
                    }[delimiter]
                    content_start = index + len(delimiter)
                    spans.append(MarkdownSpan(kind, index, closing + len(delimiter), content_start, closing))
                    spans.append(MarkdownSpan("syntax", index, content_start, index, content_start))
                    spans.append(MarkdownSpan("syntax", closing, closing + len(delimiter), closing, closing + len(delimiter)))
                    spans.extend(self._parse_inline(text, content_start, closing))
                    index = closing + len(delimiter)
                    continue
            index += 1

        for tag in TAG_RE.finditer(text, start, end):
            if not any(
                span.kind in {"inline_code", "wikilink", "wikilink_alias", "markdown_link"}
                and span.start <= tag.start() < span.end
                for span in spans
            ):
                spans.append(MarkdownSpan("tag", tag.start(), tag.end(), tag.start(), tag.end()))
                spans.append(MarkdownSpan("syntax", tag.start(), tag.start() + 1, tag.start(), tag.start() + 1))
        return spans

    @staticmethod
    def _emphasis_delimiter(text: str, index: int) -> str:
        for marker in ("***", "___", "**", "__", "~~", "*", "_"):
            if text.startswith(marker, index):
                return marker
        return ""

    @staticmethod
    def _is_escaped(text: str, position: int) -> bool:
        backslashes = 0
        position -= 1
        while position >= 0 and text[position] == "\\":
            backslashes += 1
            position -= 1
        return backslashes % 2 == 1

    @staticmethod
    def _find_backtick_run(text: str, start: int, length: int, end: int) -> tuple[int, int]:
        position = start
        while position < end:
            position = text.find("`", position, end)
            if position < 0:
                return -1, -1
            run_end = position + 1
            while run_end < end and text[run_end] == "`":
                run_end += 1
            if run_end - position == length and not MarkdownDocumentParser._is_escaped(text, position):
                return position, run_end
            position = run_end
        return -1, -1


class MarkdownHighlighter(QSyntaxHighlighter):
    def __init__(self, editor: "MarkdownEditor") -> None:
        super().__init__(editor.document())
        self.editor = editor
        self.parser = MarkdownDocumentParser()
        self.live_preview = True

    def set_live_preview(self, enabled: bool) -> None:
        self.live_preview = enabled
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt API
        if not self.live_preview:
            return
        previous_state = self.previousBlockState()
        if previous_state < 0:
            previous_state = MarkdownDocumentParser.NORMAL
        block_spans, state = self.parser.parse_block(
            text, previous_state, self.currentBlock().blockNumber() == 0
        )
        self.setCurrentBlockState(state)
        palette = self.editor.palette()
        accent = palette.color(QPalette.ColorRole.Link)
        if not accent.isValid() or accent == palette.color(QPalette.ColorRole.Text):
            accent = palette.color(QPalette.ColorRole.Highlight)
        base_size = self.editor.font().pointSizeF()

        for span in block_spans:
            if span.kind == "heading":
                level = len(text) - len(text.lstrip("#"))
                fmt = QTextCharFormat()
                fmt.setFontWeight(QFont.Weight.Bold)
                fmt.setFontPointSize(max(base_size, 21 - (level - 1) * 2))
                self.setFormat(span.content_start, span.content_end - span.content_start, fmt)
            elif span.kind in {"bold", "bold_italic", "italic", "strike", "inline_code", "wikilink", "wikilink_alias", "markdown_link", "tag", "blockquote", "code_block", "frontmatter", "horizontal_rule"}:
                fmt = self._format_for_kind(span.kind, palette, accent)
                self.setFormat(span.start, span.end - span.start, fmt)
            elif span.kind == "list":
                self.setFormat(span.start, span.end - span.start, self._format_for_kind("list", palette, accent))
            elif span.kind == "syntax":
                fmt = QTextCharFormat()
                fmt.setForeground(palette.color(QPalette.ColorRole.Base))
                fmt.setFontPointSize(1)
                fmt.setFontWeight(QFont.Weight.Normal)
                fmt.setFontItalic(False)
                fmt.setFontUnderline(False)
                fmt.setFontStrikeOut(False)
                self.setFormat(span.start, span.end - span.start, fmt)

    def _format_for_kind(self, kind: str, palette: QPalette, accent: QColor) -> QTextCharFormat:
        fmt = QTextCharFormat()
        if kind in {"bold", "bold_italic"}:
            fmt.setFontWeight(QFont.Weight.Bold)
        if kind in {"italic", "bold_italic", "blockquote"}:
            fmt.setFontItalic(True)
        if kind == "strike":
            fmt.setFontStrikeOut(True)
        if kind in {"inline_code", "code_block"}:
            fmt.setFontFamilies(["Consolas"])
            base = palette.color(QPalette.ColorRole.Base)
            background = base
            background = background.darker(112) if background.lightness() > 128 else background.lighter(165)
            fmt.setBackground(background)
            code_color = QColor("#177e75") if base.lightness() > 128 else QColor("#7dd3c7")
            fmt.setForeground(code_color)
        if kind in {"wikilink", "wikilink_alias", "markdown_link", "tag"}:
            fmt.setForeground(accent)
            fmt.setFontUnderline(True)
        if kind in {"blockquote", "frontmatter", "horizontal_rule"}:
            fmt.setForeground(palette.color(QPalette.ColorRole.Mid))
        if kind == "list":
            fmt.setForeground(palette.color(QPalette.ColorRole.Text))
        return fmt

class MarkdownEditor(QTextEdit):
    linkActivated = Signal(str)
    linkHovered = Signal(str)
    livePreviewChanged = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFont(QFont("Consolas"))
        self.parser = MarkdownDocumentParser()
        self.highlighter = MarkdownHighlighter(self)
        self.setMouseTracking(True)
        self._last_hovered_link = ""

    @property
    def live_preview(self) -> bool:
        return self.highlighter.live_preview

    def set_live_preview(self, enabled: bool) -> None:
        if self.live_preview == enabled:
            return
        self.highlighter.set_live_preview(enabled)
        self.livePreviewChanged.emit(enabled)

    def toggle_live_preview(self) -> None:
        self.set_live_preview(not self.live_preview)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        if (
            event.key() == Qt.Key.Key_M
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.toggle_live_preview()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            cursor = self.cursorForPosition(event.position().toPoint())
            target = self._wikilink_at(cursor.position())
            if target:
                self.linkActivated.emit(target)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        cursor = self.cursorForPosition(event.position().toPoint())
        target = self._wikilink_at(cursor.position())
        if target != self._last_hovered_link:
            self._last_hovered_link = target
            self.linkHovered.emit(target)
        if not target:
            QToolTip.hideText()
        super().mouseMoveEvent(event)

    def _wikilink_at(self, position: int) -> str:
        block = self.document().findBlock(position)
        if not block.isValid():
            return ""
        text = block.text()
        local_position = position - block.position()
        match = next(
            (item for item in WIKILINK_RE.finditer(text) if item.start() <= local_position <= item.end()),
            None,
        )
        if match is None:
            return ""
        target = match.group(1).strip()
        if match.group(2):
            target += f"#{match.group(2)}"
        return target

