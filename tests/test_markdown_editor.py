from __future__ import annotations

from PySide6.QtWidgets import QApplication

from app.core.vault import Vault
from app.ui.markdown_editor import MarkdownDocumentParser, MarkdownEditor
from app.ui.main_window import MainWindow


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_parser_finds_markdown_constructs_and_source_ranges():
    source = (
        "---\ntitle: Note\n---\n"
        "# Heading\n**bold** and *italic* and ~~strike~~ and `code`\n"
        "[[Note]] [[Note|Alias]] [[Note#Heading|Section]]\n"
        "[link](https://example.test) #tag\n- item\n> quote\n"
        "```python\nprint('x')\n```\n---\n"
    )

    spans = MarkdownDocumentParser().parse(source)
    kinds = {span.kind for span in spans}

    assert {
        "frontmatter", "heading", "bold", "italic", "strike", "inline_code",
        "wikilink", "wikilink_alias", "markdown_link", "tag", "list",
        "blockquote", "code_block", "horizontal_rule",
    } <= kinds
    for span in spans:
        assert 0 <= span.start <= span.content_start <= span.content_end <= span.end <= len(source)


def test_malformed_markdown_does_not_create_unbounded_spans():
    source = "**unfinished\n[[unfinished\n`unfinished\n"

    spans = MarkdownDocumentParser().parse(source)

    assert all(0 <= span.start <= span.end <= len(source) for span in spans)
    assert not {"bold", "wikilink", "inline_code"} & {span.kind for span in spans}


def test_inline_code_matches_only_equal_length_unescaped_backtick_runs():
    source = "`one `` embedded` and ``two ` embedded`` and \\`literal\\`"

    spans = MarkdownDocumentParser().parse(source)
    code_spans = [span for span in spans if span.kind == "inline_code"]

    assert [source[span.start:span.end] for span in code_spans] == [
        "`one `` embedded`",
        "``two ` embedded``",
    ]


def test_fenced_code_requires_matching_fence_character_and_length():
    source = "````python\ncode\n```\n~~~\n````\nafter"

    spans = MarkdownDocumentParser().parse(source)
    code_blocks = [span for span in spans if span.kind == "code_block"]

    assert len(code_blocks) == 5
    assert all(source[span.start:span.end] != "after" for span in code_blocks)


def test_nested_emphasis_spans_stay_inside_their_parent_source_range():
    source = "**very *important***"

    spans = MarkdownDocumentParser().parse(source)
    bold = next(span for span in spans if span.kind == "bold")
    italic = next(span for span in spans if span.kind == "italic")

    assert (bold.start, bold.end) == (0, len(source))
    assert bold.content_start <= italic.start < italic.end <= bold.content_end


def test_live_preview_preserves_source_for_markdown_features():
    _application()
    source = (
        "---\ntitle: Note\ntags:\n  - AI\n---\n\n"
        "# Heading\n\n**bold**, *italic*, ***both***, ~~strike~~, `code`\n"
        "[link](https://example.test) and [[Note#Heading|alias]]\n"
        "- parent\n  - child\n\n> quote\n\n"
        "```python\n    print('hello')\n```\n"
    )
    editor = MarkdownEditor()
    editor.setPlainText(source)
    QApplication.processEvents()

    assert editor.toPlainText() == source
    assert not editor.document().isModified()


def test_cursor_and_mode_changes_preserve_text_and_dirty_state():
    _application()
    source = "# Heading\n\nThis is **important** and [[Note]]."
    editor = MarkdownEditor()
    editor.setPlainText(source)
    editor.document().setModified(False)
    assert editor.font().family() == "Consolas"

    editor.setTextCursor(editor.textCursor())
    editor.moveCursor(editor.textCursor().MoveOperation.End)
    editor.set_live_preview(False)
    assert not editor.live_preview
    assert editor.toPlainText() == source
    editor.set_live_preview(True)
    QApplication.processEvents()

    assert editor.live_preview
    assert editor.font().family() == "Consolas"
    assert editor.toPlainText() == source
    assert not editor.document().isModified()


def test_preview_hides_markers_source_mode_shows_them_and_code_is_monospace():
    _application()
    source = "**bold** and `code`\n```python\nx = 1\n```"
    editor = MarkdownEditor()
    editor.setPlainText(source)
    QApplication.processEvents()

    marker_ranges = editor.document().firstBlock().layout().formats()
    expected_markers = {(0, 2), (6, 2), (13, 1), (18, 1)}
    hidden_markers = [
        item for item in marker_ranges
        if (item.start, item.length) in expected_markers
    ]
    assert len(hidden_markers) == len(expected_markers)
    assert all(
        item.format.foreground().color() == editor.palette().color(editor.palette().ColorRole.Base)
        and item.format.fontPointSize() == 1
        for item in hidden_markers
    )
    inline_code = next(
        item for item in marker_ranges if (item.start, item.length) == (14, 4)
    )
    assert inline_code.format.foreground().color() != editor.palette().color(
        editor.palette().ColorRole.Text
    )
    assert inline_code.format.background().color() != editor.palette().color(
        editor.palette().ColorRole.Base
    )

    code_block = editor.document().findBlockByNumber(2)
    code_formats = code_block.layout().formats()
    code_text = next(item for item in code_formats if item.length == len("x = 1"))
    assert "Consolas" in code_text.format.fontFamilies()
    assert code_text.format.foreground().color() == inline_code.format.foreground().color()

    editor.set_live_preview(False)
    QApplication.processEvents()

    assert editor.document().firstBlock().layout().formats() == []
    assert editor.toPlainText() == source


def test_wikilink_lookup_preserves_target_heading_and_alias_display_source():
    _application()
    editor = MarkdownEditor()
    editor.setPlainText("See [[Machine Learning#Backpropagation|this section]].")

    assert editor._wikilink_at(12) == "Machine Learning#Backpropagation"


def test_main_window_save_writes_markdown_source(tmp_path):
    _application()
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    note_path = vault_path / "Note.md"
    note_path.write_text("# Note\n", encoding="utf-8")
    window = MainWindow()
    window._vault_path = vault_path
    window.vault = Vault(vault_path)
    window.vault.refresh()
    window._open_note_file(note_path)
    source = "# Note\n\n**bold** and [[Target|alias]].\n"
    window.editor.setPlainText(source)

    window.save_current_note()

    assert note_path.read_text(encoding="utf-8") == source
    assert window.editor.toPlainText() == source