"""
Set of building blocks that store BT2 messages in a fast buffer, and display them in a Qt application with lazy loading.
"""

import bt2
import numpy as np

from PyQt5.Qt import Qt, QAbstractTableModel, QModelIndex


class EventBuffer:
    """
    Event buffer, implemented as a list of fixed size buffers.
    """

    def __init__(self, event_block_sz, event_dtype):
        self._blocksz = event_block_sz
        self._dtype = event_dtype
        self._buffer = [ np.empty(self._blocksz, dtype=self._dtype) ]
        self._fblocks = 0    # Number of fully used blocks
        self._lbufsiz = 0    # Number of saved events in the last block

    def __len__(self):
        return self._fblocks * self._blocksz + self._lbufsiz

    def __getitem__(self, idx):
        if idx > len(self):
            raise IndexError

        return self._buffer[idx // self._blocksz][idx % self._blocksz]

    @property
    def dtype(self):
        return self._dtype

    def append(self, event):
        if self._lbufsiz == self._blocksz:
            new_block = np.empty(self._blocksz, dtype=self._dtype)
            new_block[0] = event
            self._buffer.append(new_block)

            self._lbufsiz = 1
            self._fblocks += 1
        else:
            self._buffer[self._fblocks][self._lbufsiz] = event
            self._lbufsiz += 1


class EventBufferTableModel(QAbstractTableModel):
    """
    Data model that uses fetchMore mechanism for on-demand row loading.

    More info on
      https://doc.qt.io/qt-5/qabstracttablemodel.html
      https://sateeshkumarb.wordpress.com/2012/04/01/paginated-display-of-table-data-in-pyqt/
      PyQt5-5.xx.x.devX/examples/itemviews/fetchmore.py
      PyQt5-5.xx.x.devX/examples/itemviews/storageview.py
      PyQt5-5.xx.x.devX/examples/multimediawidgets/player.py
    """

    def __init__(self, data_obj=None, parent=None):
        super().__init__()

        self._data = data_obj
        self._data_headers = None

        self._data_columnCount = 0   # Displayed column count
        self._data_rowCount = 0      # Displayed row count

    def rowCount(self, parent=QModelIndex()):
        return self._data_rowCount if not parent.isValid() else 0

    def columnCount(self, parent=QModelIndex()):
        return self._data_columnCount if not parent.isValid() else 0

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and index.isValid() and self._data:
            # This is where we return data to be displayed
            return str(self._data[index.row()][index.column()])

        return None

    def setHorizontalHeaderLabels(self, headers):
        self._data_headers = headers
        self._data_columnCount = len(headers)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal and section < len(self._data_headers):
                return self._data_headers[section]
        return None

    def canFetchMore(self, index):
        return self._data_rowCount < len(self._data)

    def fetchMore(self, index):
        itemsToFetch = len(self._data) - self._data_rowCount

        self.beginInsertRows(QModelIndex(), self._data_rowCount + 1, self._data_rowCount + itemsToFetch)
        self._data_rowCount += itemsToFetch
        self.endInsertRows()
