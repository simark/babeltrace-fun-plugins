#!/usr/bin/env python3
# *_* coding: utf-8 *_*

"""
Creates and runs a graph with a can.CANSource source and in-app sink, which delegates stream info to the GUI.
Simple example.
---
Please note: libbabeltrace2 python library (bt2) depends on its core C library.
---
LD_LIBRARY_PATH=[babeltrace2 build folder]/src/lib/.libs/
BABELTRACE_PLUGIN_PATH = [babeltrace2 build folder]/src/plugins/[plugin name]
LIBBABELTRACE2_PLUGIN_PROVIDER_DIR = [babeltrace2 build folder]/src/python-plugin-provider/.libs/
"""

import bt2

from PyQt5.Qt import *
from PyQt5.QtWidgets import *

# import local modules
from graph.utils import load_plugins, cmd_parser


@bt2.plugin_component_class
class SinkEmitter(bt2._UserSinkComponent):
    """
    Sink component that adds received events to the provided QStandardItemModel.
    """

    def __init__(self, config, params, obj):
        self._port = self._add_input_port("in")
        self._tableModel, self._tableView = obj

    def _user_graph_is_configured(self):
        self._it = self._create_message_iterator(self._port)

    def _user_consume(self):
        msg = next(self._it)

        if type(msg) == bt2._EventMessageConst:

            # We are running in the gui thread, so we can freely access / modify gui objects
            self._tableModel.appendRow((QStandardItem(str(msg.default_clock_snapshot.value)), QStandardItem(msg.event.name)))
            self._tableView.scrollToBottom()


# GUI Application
def main():
    global CANSource_data_path, CANSource_dbc_path
    global plugins

    app = QApplication([])

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


    # Create graph and add components
    graph = bt2.Graph()

    source = plugins['can'].source_component_classes['CANSource']
    graph_source = graph.add_component(source, 'source',
       params=bt2.MapValue({
           'inputs': bt2.ArrayValue([CANSource_data_path]),
           'databases': bt2.ArrayValue([CANSource_dbc_path])
       })
    )

    graph_sink = graph.add_component(SinkEmitter, 'sink', obj=(model, tableView))

    # Connect components together
    graph.connect_ports(
        list(graph_source.output_ports.values())[0],
        list(graph_sink.input_ports.values())[0]
    )

    # Run graph as part of the GUI event loop
    # https://stackoverflow.com/questions/36988826/running-code-in-the-main-loop
    graph_timer = QTimer()

    def run_graph():
        try:
            graph.run_once()
        except bt2.Stop:
            print("Graph finished execution.")
            graph_timer.stop()

    graph_timer.timeout.connect(run_graph)
    graph_timer.start()


    # Start GUI event loop
    tableView.show()
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
