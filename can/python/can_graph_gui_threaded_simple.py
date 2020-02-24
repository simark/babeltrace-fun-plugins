#!/usr/bin/env python3
# *_* coding: utf-8 *_*

"""
Creates and runs a graph with a can.CANSource source and in-app sink, which delegates stream info to the GUI.
Thread-based implementation, simplified variant.

Check the event loop implementation, which is *by far* the best way of doing it and is *faster*.
---
Please note: libbabeltrace2 python library (bt2) depends on its core C library.
---
LD_LIBRARY_PATH=[babeltrace2 build folder]/src/lib/.libs/
BABELTRACE_PLUGIN_PATH = [babeltrace2 build folder]/src/plugins/[plugin name]
LIBBABELTRACE2_PLUGIN_PROVIDER_DIR = [babeltrace2 build folder]/src/python-plugin-provider/.libs/
"""

import bt2
import time

from PyQt5.Qt import *
from PyQt5.QtWidgets import *

# import local modules
from graph.utils import load_plugins, cmd_parser


@bt2.plugin_component_class
class SinkEmitter(bt2._UserSinkComponent):
    """
    Sink component that emits a signal at event
    """

    def __init__(self, config, params, obj):
        self._port = self._add_input_port("in")
        self._signal = obj

    def _user_graph_is_configured(self):
        self._it = self._create_message_iterator(self._port)

    def _user_consume(self):
        msg = next(self._it)

        if type(msg) == bt2._EventMessageConst:

            # Do note that while passing data via signals is thread-safe, it is slow,
            # and loads the event loop.
            #
            # For larger data, it is more sensible for threads to share same memory objects,
            # possibly even without mutexes (if the view is allowed to lag behind the model),
            # and poll the model in intervals.
            #
            # See can_gui_responsive.py, graph/event_buffer.py on how this might be done.
            #
            self._signal.emit(str(msg.default_clock_snapshot.value), msg.event.name)


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

    # Signal that will be connected to the
    # The arguments specify the types of objects passed via signal
    event_signal = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super(BT2GraphThread, self).__init__(parent)
        self._running = True

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
        graph_sink = graph.add_component(SinkEmitter, 'sink', obj=self.event_signal)

        # Connect components together
        graph.connect_ports(
            list(graph_source.output_ports.values())[0],
            list(graph_sink.input_ports.values())[0]
        )

        # Run graph
        try:
            while self._running:
                self._graph.run_once()
                # To block the graph_thread, which allows the main thread with the gui event loop to be rescheduled
                # For a more elaborate example, see can_graph_gui_responsive.py
                time.sleep(0.001)

        except bt2.Stop:
            print("Graph finished execution.")

        print("Graph thread done.")

    def stop(self):
        self._running = False

# GUI Application
def main():
    app = QApplication([])

    # BT2 Graph thread
    graph_thread = BT2GraphThread()

    # Data model
    model = QStandardItemModel()
    model.setHorizontalHeaderLabels(['name', 'timestamp'])

    # Table window
    tableView = QTableView()
    tableView.setWindowTitle("Simple Babeltrace2 GUI demo")
    tableView.setModel(model)

    tableView.setEditTriggers(QTableWidget.NoEditTriggers)    # read-only
    tableView.verticalHeader().setDefaultSectionSize(10)      # row height
    tableView.horizontalHeader().setStretchLastSection(True)  # last column resizes to widget width

    # Provide slot that updates data model & triggers GUI update
    # https://www.riverbankcomputing.com/static/Docs/PyQt5/signals_slots.html
    @pyqtSlot(str, str)
    def update_gui(timestamp, name):
        model.appendRow( (QStandardItem(timestamp), QStandardItem(name)) )
        tableView.scrollToBottom()

    # Connect sink event signal to slot
    graph_thread.event_signal.connect(update_gui)

    # Start graph thread
    graph_thread.start()

    # Start GUI event loop
    tableView.show()
    app.exec_()
    graph_thread.stop()
    graph_thread.wait()

    print("Done.")

if __name__ == "__main__":
    global system_plugin_path, plugin_path
    global plugins

    # Parse command line and add parsed parameters to globals
    parser = cmd_parser(__doc__)
    globals().update(vars(parser.parse_args()))

    plugins = load_plugins(system_plugin_path, plugin_path)
    main()
