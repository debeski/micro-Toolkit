from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


class DataFrameTableModel(QAbstractTableModel):
    def __init__(self, dataframe):
        super().__init__()
        self._dataframe = dataframe

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return 0 if self._dataframe is None else len(self._dataframe.index)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return 0 if self._dataframe is None else len(self._dataframe.columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or self._dataframe is None:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            value = self._dataframe.iat[index.row(), index.column()]
            return "" if value is None else str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole or self._dataframe is None:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(self._dataframe.columns[section])
        return str(section + 1)
