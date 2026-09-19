"""The Layers dock: a QGIS-style grouped tree.

Groups are fixed top-level nodes (Responses / HSV Masks / Historic AOIs /
Sentinel-Latent / Pins / Search Extent); layers are added/removed under
them as the user works. Each layer item is checkable (visibility) and
carries its layer_id in Qt.UserRole so MainWindow can route a checkbox
toggle to MapPanel.set_layer_visible().
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


class LayersPanel(QWidget):
    layer_visibility_changed = Signal(str, bool)   # layer_id, visible

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)

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

    def add_layer(self, group_name: str, layer_id: str, label: str, checked: bool = True) -> None:
        group_item = self._groups.get(group_name)
        if group_item is None:
            raise ValueError(f"Unknown layer group: {group_name!r}")

        item = QTreeWidgetItem([label])
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
        item.setData(0, Qt.UserRole, layer_id)
        group_item.addChild(item)
        group_item.setExpanded(True)

    def remove_layer(self, layer_id: str) -> None:
        item = self._find_layer_item(layer_id)
        if item is not None:
            item.parent().removeChild(item)

    def _find_layer_item(self, layer_id: str) -> QTreeWidgetItem | None:
        for group_item in self._groups.values():
            for i in range(group_item.childCount()):
                child = group_item.child(i)
                if child.data(0, Qt.UserRole) == layer_id:
                    return child
        return None

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        layer_id = item.data(0, Qt.UserRole)
        if layer_id is None:
            return  # a group header, not a layer
        self.layer_visibility_changed.emit(layer_id, item.checkState(0) == Qt.Checked)
