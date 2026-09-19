"""The Layers dock: a QGIS-style grouped tree.

Groups are fixed top-level nodes (Responses / HSV Masks / Historic AOIs /
Sentinel-Latent / Pins / Search Extent); layers are added/removed under
them as the user works. Each layer item is checkable (visibility) and
carries its layer_id in Qt.UserRole so MainWindow can route a checkbox
toggle to MapPanel.set_layer_visible().

Pins additionally support one level of named subgroup under "Pins" —
matching pin_groups in the project database — created on demand via
ensure_pin_group(). A pin with no group sits directly under "Pins".
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

GROUP_NAMES = [
    "Responses",
    "HSV Masks",
    "Historic AOIs",
    "Sentinel / Latent",
    "Pins",
    "Search Extent",
]

PIN_GROUP_ROLE = Qt.UserRole + 2   # marks a QTreeWidgetItem as a pin subgroup header


class LayersPanel(QWidget):
    layer_visibility_changed = Signal(str, bool, str)   # layer_id, visible, kind ("raster"|"marker")
    pin_context_menu_requested = Signal(str, object)     # pin_id, QPoint (global)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree)

        self._groups: dict[str, QTreeWidgetItem] = {}
        for name in GROUP_NAMES:
            group_item = QTreeWidgetItem([name])
            group_item.setFlags(group_item.flags() & ~Qt.ItemIsUserCheckable)
            font = group_item.font(0)
            font.setBold(True)
            group_item.setFont(0, font)
            self.tree.addTopLevelItem(group_item)
            self._groups[name] = group_item

        self.tree.expandAll()
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)

    # -- Generic layers (raster responses/masks/etc.) --------------------

    def add_layer(
        self, group_name: str, layer_id: str, label: str, checked: bool = True, kind: str = "raster"
    ) -> None:
        """kind distinguishes a MapLibre raster layer from a point marker
        (pins) since they're toggled through different map_panel calls —
        see MainWindow._on_layer_visibility_changed."""
        group_item = self._groups.get(group_name)
        if group_item is None:
            raise ValueError(f"Unknown layer group: {group_name!r}")
        self._add_leaf(group_item, layer_id, label, checked, kind)

    def remove_layer(self, layer_id: str) -> None:
        item = self._find_layer_item(layer_id)
        if item is not None:
            item.parent().removeChild(item)

    def _add_leaf(
        self, parent_item: QTreeWidgetItem, layer_id: str, label: str, checked: bool, kind: str
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem([label])
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
        item.setData(0, Qt.UserRole, layer_id)
        item.setData(0, Qt.UserRole + 1, kind)
        parent_item.addChild(item)
        parent_item.setExpanded(True)
        return item

    def _find_layer_item(self, layer_id: str) -> QTreeWidgetItem | None:
        """Walks the whole tree (not just one level) since pins can now
        sit two levels deep, under a named subgroup."""
        def walk(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            for i in range(item.childCount()):
                child = item.child(i)
                if child.data(0, Qt.UserRole) == layer_id:
                    return child
                found = walk(child)
                if found is not None:
                    return found
            return None

        for i in range(self.tree.topLevelItemCount()):
            found = walk(self.tree.topLevelItem(i))
            if found is not None:
                return found
        return None

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        layer_id = item.data(0, Qt.UserRole)
        if layer_id is None:
            return  # a group/subgroup header, not a layer
        kind = item.data(0, Qt.UserRole + 1) or "raster"
        self.layer_visibility_changed.emit(layer_id, item.checkState(0) == Qt.Checked, kind)

    # -- Pins: subgroups + markers ----------------------------------------

    def ensure_pin_group(self, group_name: str) -> QTreeWidgetItem:
        pins_root = self._groups["Pins"]
        for i in range(pins_root.childCount()):
            child = pins_root.child(i)
            if child.data(0, PIN_GROUP_ROLE) and child.text(0) == group_name:
                return child

        group_item = QTreeWidgetItem([group_name])
        group_item.setFlags(group_item.flags() & ~Qt.ItemIsUserCheckable)
        group_item.setData(0, PIN_GROUP_ROLE, True)
        pins_root.addChild(group_item)
        pins_root.setExpanded(True)
        return group_item

    def add_pin_marker(self, pin_id: str, label: str, group_name: str | None = None,
                        checked: bool = True) -> None:
        parent_item = self.ensure_pin_group(group_name) if group_name else self._groups["Pins"]
        self._add_leaf(parent_item, pin_id, label, checked, "marker")

    def move_pin_to_group(self, pin_id: str, group_name: str | None) -> None:
        item = self._find_layer_item(pin_id)
        if item is None:
            return
        label = item.text(0)
        checked = item.checkState(0) == Qt.Checked
        item.parent().removeChild(item)
        self.add_pin_marker(pin_id, label, group_name, checked)

    def clear_pins(self) -> None:
        """Removes every pin item and subgroup under "Pins" — used before
        a full reload from the database (e.g. on project open)."""
        pins_root = self._groups["Pins"]
        while pins_root.childCount() > 0:
            pins_root.removeChild(pins_root.child(0))

    def _on_context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if item is None:
            return
        layer_id = item.data(0, Qt.UserRole)
        kind = item.data(0, Qt.UserRole + 1)
        if layer_id is None or kind != "marker":
            return
        self.pin_context_menu_requested.emit(layer_id, self.tree.viewport().mapToGlobal(pos))
