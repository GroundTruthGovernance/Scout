from PySide6.QtCore import Qt

from scout.app.panels.layers_panel import LayersPanel


def test_add_layer_defaults_to_raster_kind(qapp):
    panel = LayersPanel()
    panel.add_layer("Responses", "resp-1", "Response 1")

    received = []
    panel.layer_visibility_changed.connect(lambda *args: received.append(args))

    item = panel._find_layer_item("resp-1")
    item.setCheckState(0, Qt.Unchecked)

    assert received == [("resp-1", False, "raster")]


def test_add_layer_marker_kind_round_trips(qapp):
    panel = LayersPanel()
    panel.add_layer("Pins", "pin-1", "Pin 1", kind="marker")

    received = []
    panel.layer_visibility_changed.connect(lambda *args: received.append(args))

    item = panel._find_layer_item("pin-1")
    item.setCheckState(0, Qt.Unchecked)

    assert received == [("pin-1", False, "marker")]


def test_group_header_toggle_does_not_emit(qapp):
    panel = LayersPanel()
    received = []
    panel.layer_visibility_changed.connect(lambda *args: received.append(args))

    group_item = panel._groups["Pins"]
    group_item.setText(0, "Pins (renamed)")  # any itemChanged on a header, not a checkbox flip

    assert received == []


def test_remove_layer(qapp):
    panel = LayersPanel()
    panel.add_layer("Responses", "resp-1", "Response 1")
    assert panel._find_layer_item("resp-1") is not None
    panel.remove_layer("resp-1")
    assert panel._find_layer_item("resp-1") is None


def test_unknown_group_raises(qapp):
    panel = LayersPanel()
    try:
        panel.add_layer("Nonexistent Group", "x", "X")
        assert False, "expected ValueError"
    except ValueError:
        pass
