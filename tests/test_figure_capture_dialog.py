from scout.app.dialogs.figure_capture_dialog import FigureCaptureDialog


def test_accept_with_title_produces_values(qapp):
    dialog = FigureCaptureDialog()
    dialog.title_edit.setText("S01 edge pixel")
    dialog.caption_edit.setText("A note about it")

    dialog._on_accept()

    assert dialog.values() == {"title": "S01 edge pixel", "caption": "A note about it"}


def test_accept_without_title_does_not_produce_values(qapp):
    dialog = FigureCaptureDialog()
    dialog.caption_edit.setText("A note without a title")

    dialog._on_accept()

    assert dialog.values() is None


def test_caption_is_optional(qapp):
    dialog = FigureCaptureDialog()
    dialog.title_edit.setText("S01 edge pixel")

    dialog._on_accept()

    assert dialog.values()["caption"] == ""
