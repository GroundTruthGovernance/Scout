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


def test_add_pin_marker_without_group_sits_directly_under_pins(qapp):
    panel = LayersPanel()
    panel.add_pin_marker("pin-1", "Pin 1")
    item = panel._find_layer_item("pin-1")
    assert item is not None
    assert item.parent() is panel._groups["Pins"]


def test_add_pin_marker_with_group_creates_subgroup(qapp):
    panel = LayersPanel()
    panel.add_pin_marker("pin-1", "Pin 1", group_name="Fylde manifestations")

    item = panel._find_layer_item("pin-1")
    assert item is not None
    assert item.parent().text(0) == "Fylde manifestations"
    assert item.parent().parent() is panel._groups["Pins"]


def test_ensure_pin_group_reuses_existing_group(qapp):
    panel = LayersPanel()
    first = panel.ensure_pin_group("Fylde manifestations")
    second = panel.ensure_pin_group("Fylde manifestations")
    assert first is second
    assert panel._groups["Pins"].childCount() == 1


def test_move_pin_to_group_relocates_and_preserves_state(qapp):
    panel = LayersPanel()
    panel.add_pin_marker("pin-1", "Pin 1", checked=False)

    panel.move_pin_to_group("pin-1", "Seep line")

    item = panel._find_layer_item("pin-1")
    assert item.parent().text(0) == "Seep line"
    assert item.checkState(0) == Qt.Unchecked
    assert item.text(0) == "Pin 1"


def test_move_pin_to_group_none_moves_back_to_pins_root(qapp):
    panel = LayersPanel()
    panel.add_pin_marker("pin-1", "Pin 1", group_name="Seep line")
    panel.move_pin_to_group("pin-1", None)

    item = panel._find_layer_item("pin-1")
    assert item.parent() is panel._groups["Pins"]


def test_clear_pins_removes_markers_and_subgroups(qapp):
    panel = LayersPanel()
    panel.add_pin_marker("pin-1", "Pin 1")
    panel.add_pin_marker("pin-2", "Pin 2", group_name="Seep line")

    panel.clear_pins()

    assert panel._groups["Pins"].childCount() == 0
    assert panel._find_layer_item("pin-1") is None
    assert panel._find_layer_item("pin-2") is None


def test_pin_context_menu_emits_for_marker_not_for_group_header(qapp):
    panel = LayersPanel()
    panel.add_pin_marker("pin-1", "Pin 1", group_name="Seep line")
    panel.tree.expandAll()

    received = []
    panel.pin_context_menu_requested.connect(lambda pin_id, pos: received.append(pin_id))

    pin_item = panel._find_layer_item("pin-1")
    pin_rect = panel.tree.visualItemRect(pin_item)
    panel._on_context_menu(pin_rect.center())
    assert received == ["pin-1"]

    received.clear()
    group_item = pin_item.parent()
    group_rect = panel.tree.visualItemRect(group_item)
    panel._on_context_menu(group_rect.center())
    assert received == []


def test_unknown_group_raises(qapp):
    panel = LayersPanel()
    try:
        panel.add_layer("Nonexistent Group", "x", "X")
        assert False, "expected ValueError"
    except ValueError:
        pass
