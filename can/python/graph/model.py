"""
Custom data models, intended to be filled by BT2 sinks, and displayed in Qt Views.
https://doc.qt.io/qt-5/model-view-programming.html
"""

from PyQt5.Qt import Qt, QAbstractTableModel, QModelIndex


class AppendableTableModel(QAbstractTableModel):
    """
    Table model with fetchMore mechanism for on-demand row loading.

    More info
      https://doc.qt.io/qt-5/qabstracttablemodel.html
      https://sateeshkumarb.wordpress.com/2012/04/01/paginated-display-of-table-data-in-pyqt/
      PyQt5-5.14.2.devX/examples/itemviews/fetchmore.py
      PyQt5-5.14.2.devX/examples/itemviews/storageview.py
      PyQt5-5.14.2.devX/examples/multimediawidgets/player.py
    """

    def __init__(self, headers, parent=None):
        super().__init__(parent)

        self._table = []

        self._data_headers = headers
        self._data_columnCount = len(self._data_headers)  # Displayed column count
        self._data_rowCount = 0  # Displayed row count

    def rowCount(self, parent=QModelIndex()):
        return self._data_rowCount

    def columnCount(self, parent):
        return self._data_columnCount

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and index.isValid() and self._table:
            # This is where we return data to be displayed
            return str(self._table[index.row()][index.column()])

        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal and section < len(self._data_headers):
                return self._data_headers[section]
            if orientation == Qt.Vertical:
                return section
        return None

    def canFetchMore(self, index):
        return self._data_rowCount < len(self._table)

    def fetchMore(self, index):
        itemsToFetch = len(self._table) - self._data_rowCount

        self.beginInsertRows(QModelIndex(), self._data_rowCount + 1, self._data_rowCount + itemsToFetch)
        self._data_rowCount += itemsToFetch
        self.endInsertRows()

    def append(self, item_data):
        """
        Append item with provided item_data to end of table.
        :param item_data: table view columns
        :return: None
        """
        self._table.append(item_data)

        # If first element, notify view so that it starts updating
        if len(self._table) == 1:
            self.modelReset.emit()
