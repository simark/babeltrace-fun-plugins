#!/usr/bin/env python3
# *_* coding: utf-8 *_*

"""
Creates and runs a graph with a can.CANSource source and in-app sink, which delegates stream info to the GUI.
A more complex example which allows for faster graph execution, while allowing for a decently responsive ui.

Thread-based implementation, with all the workaround to make it as fast as possible.

Check the event loop implementation, which is *by far* the best way of doing it and is *just as fast/faster*.
---
Please note: libbabeltrace2 python library (bt2) depends on its core C library.
---
LD_LIBRARY_PATH=[babeltrace2 build folder]/src/lib/.libs/
BABELTRACE_PLUGIN_PATH = [babeltrace2 build folder]/src/plugins/[plugin name]
LIBBABELTRACE2_PLUGIN_PROVIDER_DIR = [babeltrace2 build folder]/src/python-plugin-provider/.libs/
"""

import bt2
import time
import numpy as np

from PyQt5.Qt import *
from PyQt5.QtWidgets import *

# import local modules
from graph.event_buffer import EventBuffer, EventBufferSink, EventBufferTableModel
from graph.utils import load_plugins, cmd_parser


# Graph thread manager - or how to enter Signal / Slot / QtEvent hell
# -- Has to be instantiated in GUI thread. --
#
# The idea is that the graph thread emits a signal through a BlockingQueuedConnection, which causes it to block,
# allowing the transition back to the main (GUI) thread, which will process all current events and the
# graph thread event, allowing it to be scheduled in the future.
#
# More info
#   https://doc.qt.io/qt-5/eventsandfilters.html
#   https://doc.qt.io/qt-5/qabstracteventdispatcher.html
#   https://doc.qt.io/qt-5/qcoreapplication.html
#
#   https://doc.qt.io/qt-5/signalsandslots.html
#   https://doc.qt.io/qt-5/qt.html#ConnectionType-enum
#   https://woboq.com/blog/how-qt-signals-slots-work-part3-queuedconnection.html
#
#   PyQt5-5.xx.x.devX/qpy/QtCore/qpycore_pyqtboundsignal.cpp
#
class BT2GraphThreadManager(QObject):

    @pyqtSlot()
    def wake_graph_thread(self):
        # Invoked from the main thread event queue (presumably when other events are processed).
        #
        # Since the signal-slot connection is a BlockingQueuedConnection, the sole fact that the slot was invoked is
        # enough to reschedule the graph thread.
        pass

    def __init__(
            self,
            buffer,
            app,
            thread_time=0.025 # Time in s the graph thread can process before being blocked
    ):
        super().__init__()

        self.thread = BT2GraphThread(buffer, self.wake_graph_thread, thread_time)
        self.app = app

    def start(self):
        self.thread.start()

    def stop(self):
        # While modifying worker state (running in graph thread) from main thread is not nice,
        # it is safe, since the graph thread only reads the affected variable state
        self.thread.stop()

        # Wait for the thread cleanup to finish
        while not self.thread.wait(10):
            # This is to handle the case where the graph thread is suspended and its BlockingQueuedConnection
            # signal isn't handled yet, when the main thread starts waiting (blocking) on the graph thread to finish,
            # essentially causing a deadlock (if we would wait indefinitely).
            #
            # So we deliberately handle all queued events here, which will also handle the slot that unblocks the graph
            # thread.
            #
            # Do note that even doing processEvents() before wait does not guarantee that the slot will be handled -
            # it might arrive after processEvents invocation and before wait.
            #
            self.app.processEvents()


# Graph processing thread
#
# Check Qt multithreading gotchas at
#   https://doc.qt.io/qt-5/qthread.html
#   https://mayaposch.wordpress.com/2011/11/01/how-to-really-truly-use-qthreads-the-full-explanation/
#   https://www.kdab.com/wp-content/uploads/stories/slides/DD12/Multithreading_Presentation.pdf
#
# IDEs have limited support for QtThreads
#   https://youtrack.jetbrains.com/issue/PY-24162
#   https://intellij-support.jetbrains.com/hc/en-us/community/posts/203420404-Pycharm-debugger-not-stopping-on-QThread-breakpoints
#
class BT2GraphThread(QThread):

    _blocking_signal = pyqtSignal()

    def __init__(self, buffer, wake_slot, thread_time):
        super().__init__()
        self._buffer = buffer
        self._running = True
        self._thread_time = thread_time

        self._blocking_signal.connect(wake_slot, type=Qt.BlockingQueuedConnection)

    def run(self):
        global CANSource_data_path, CANSource_dbc_path
        global plugins

        print("Graph thread start.")

        # Load required components from plugins
        source = plugins['can'].source_component_classes['CANSource']

        # Create graph and add components
        self._graph = graph = bt2.Graph()

        graph_source = graph.add_component(source, 'source',
            params=bt2.MapValue({
                'inputs': bt2.ArrayValue([CANSource_data_path]),
                'databases': bt2.ArrayValue([CANSource_dbc_path])
            })
        )

        # Do note: event_signal is static, but it has to be accessed through instance
        # (via self.) in order to be "bound" (expose the .emit() method)
        graph_sink = graph.add_component(EventBufferSink, 'sink', obj=self._buffer)

        # Connect components together
        graph.connect_ports(
            list(graph_source.output_ports.values())[0],
            list(graph_sink.input_ports.values())[0]
        )

        # Timer that will periodically yield the graph processing thread for better UI responsiveness
        #
        # While we have QTimers and all that jazz, both python threading and Qt's event loop mechanism seem to have
        # a very hard time interrupting a fast loop that jumps into native code, so we implement it manually.
        #
        last_wait_time = time.clock_gettime(time.CLOCK_PROCESS_CPUTIME_ID)

        # Run graph
        try:
            while self._running:
                self._graph.run_once()

                if time.clock_gettime(time.CLOCK_PROCESS_CPUTIME_ID) - last_wait_time > self._thread_time:
                    # Block graph thread
                    self._blocking_signal.emit()
                    # Reset timer when we return
                    last_wait_time = time.clock_gettime(time.CLOCK_PROCESS_CPUTIME_ID)
        except bt2.Stop:
            print("Graph finished execution.")

        print("Graph thread done.")

    def stop(self):
        self._running = False


# MainWindow
#
class MainWindow(QMainWindow):

    def __init__(self, buffer, model, graph_thread):
        super().__init__()
        self._graph_thread = graph_thread
        self._buffer = buffer
        self._model = model

        self.setWindowTitle("Responsive Babeltrace2 GUI demo")

        # Table view
        self._tableView = QTableView()
        self._tableView.setWindowTitle("Sink data")
        self._tableView.setModel(model)

        self._tableView.setEditTriggers(QTableWidget.NoEditTriggers)    # read-only
        self._tableView.verticalHeader().setDefaultSectionSize(10)      # row height
        self._tableView.horizontalHeader().setStretchLastSection(True)  # last column resizes to widget width

        # Statistics label
        self._statLabel = QLabel("Events (processed/loaded): - / -")

        # Refresh checkbox
        self._followCheckbox = QCheckBox("Follow events")
        self._followCheckbox.setChecked(True)

        # Layout
        self._layout = QGridLayout()
        self._layout.addWidget(self._tableView, 0, 0, 1, 2) # See https://doc.qt.io/qt-5/qgridlayout.html#addWidget-2
        self._layout.addWidget(self._statLabel, 1, 0)
        self._layout.addWidget(self._followCheckbox, 1, 1, 1, 1, Qt.AlignRight)

        self._mainWidget = QWidget()
        self._mainWidget.setLayout(self._layout)

        self.setCentralWidget(self._mainWidget)

    # Close event handler
    #
    # We use it so that we can stop the graph thread.
    #
    # Due to the peculiar nature of the graph thread blocking itself before switching to main thread, we cannot use the
    # aboutToQuit signal, which gets emitted when the event loop (on which we depend to unblock to resume the graph thread)
    # stops.
    #
    def closeEvent(self, event):
        self._graph_thread.stop()

    # Timer handler, provided by QObject
    # https://doc.qt.io/qt-5/qtimer.html#alternatives-to-qtimer
    @pyqtSlot()
    def timerEvent(self, QTimerEvent):

        # Statistics
        self._statLabel.setText(f"Events (processed/loaded): {len(self._buffer)} / {self._model.rowCount()}")

        # Force the view to call canFetchMore / fetchMore initially
        if not self._model.rowCount():
            self._model.modelReset.emit()

        # Follow events
        if self._followCheckbox.isChecked():
            # The following could be achieved similarly with self._tableView.scrollToBottom(), but that method has
            # issues with panning - rows appear to "bounce" and it's hard to look at the output
            #
            self._tableView.scrollTo(self._model.index(self._model.rowCount()-1, 0), QAbstractItemView.PositionAtBottom)


# GUI Application
def main():
    app = QApplication([])

    # Event buffer
    buffer = EventBuffer(event_block_sz=500, event_dtype=np.dtype([('timestamp', np.int32), ('name', 'U35')]))

    # Data model
    model = EventBufferTableModel(buffer)
    model.setHorizontalHeaderLabels(buffer.dtype.names)

    # Graph thread
    graph_thread = BT2GraphThreadManager(buffer, app)
    graph_thread.start()

    # Main window
    mainWindow = MainWindow(buffer, model, graph_thread)
    mainWindow.show()
    mainWindow.startTimer(100) # Update stats & refresh interval in ms

    # Start GUI event loop
    app.exec_()
    print("Done.")


if __name__ == "__main__":
    global system_plugin_path, plugin_path
    global plugins

    # Parse command line and add parsed parameters to globals
    parser = cmd_parser(__doc__)
    globals().update(vars(parser.parse_args()))

    plugins = load_plugins(system_plugin_path, plugin_path)
    main()
