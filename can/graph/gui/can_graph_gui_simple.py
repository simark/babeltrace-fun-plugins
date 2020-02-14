#!/usr/bin/env python3
# *_* coding: utf-8 *_*

"""
Creates and runs a graph with a can.CANSource source and in-app sink, which delegates stream info to the GUI.
---
Please note: libbabeltrace2 python library (bt2) depends on its core C library.
---
LD_LIBRARY_PATH=[babeltrace2 build folder]/src/lib/.libs/
BABELTRACE_PLUGIN_PATH = [babeltrace2 build folder]/src/plugins/[plugin name]
LIBBABELTRACE2_PLUGIN_PROVIDER_DIR = [babeltrace2 build folder]/src/python-plugin-provider/.libs/
"""

import bt2

import argparse

from PyQt5.Qt import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

# Loads system & user plugins to 'plugins' global
def load_plugins():
    global system_plugin_path, plugin_path
    global plugins

    # Load plugins
    system_plugins = bt2.find_plugins_in_path(system_plugin_path) if system_plugin_path else bt2.find_plugins()
    user_plugins = bt2.find_plugins_in_path(plugin_path)

    assert system_plugins, "No system plugins found!"
    assert user_plugins, "No user plugins found!"

    # Convert _PluginSet to dict
    plugins = {
        **{plugin.name: plugin for plugin in system_plugins},
        **{plugin.name: plugin for plugin in user_plugins}
    }

# Sink component that emits signals @ event
@bt2.plugin_component_class
class SinkEmitter(bt2._UserSinkComponent):

    def __init__(self, config, params, obj):
        self._port = self._add_input_port("in")
        self._signal = obj

    def _user_graph_is_configured(self):
        self._it = self._create_message_iterator(self._port)

    def _user_consume(self):
        # Consume one message and print it.
        msg = next(self._it)

        handler = {
            bt2._StreamBeginningMessageConst :
                lambda : "Stream begin",
            bt2._PacketBeginningMessageConst :
                lambda : "Packet begin",

            bt2._EventMessageConst :
                # Do note that while passing data via signals is thread-safe, it is slow.
                #
                # For larger data, it is more sensible for threads to share memory objects,
                # and only do mutex management over signals.
                lambda : self._signal.emit(msg.event.name, str(msg.default_clock_snapshot.value)),

            bt2._PacketEndMessageConst:
                lambda : "Packet end",
            bt2._StreamEndMessageConst:
                lambda : "Stream end"
        }
        try:
            msg = handler[type(msg)]()
            if msg:
                print(msg)
        except KeyError:
            raise RuntimeError("Unhandled message type", type(msg))


# Graph processing thread
#
# We're using the QThread subclassing approach, check gotchas at
# https://doc.qt.io/qt-5/qthread.html
class BT2GraphThread(QThread):

    # Signal that will be connected to the
    # The arguments specify the types of objects passed via signal
    event_signal = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super(BT2GraphThread, self).__init__(parent)

        global CANSource_data_path, CANSource_dbc_path
        global plugins

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

    def __del__(self):
        self.wait()

    def run(self):
        # Run graph
        self._graph.run()


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
    tableView.setWindowTitle("Sink data")
    tableView.setModel(model)

    tableView.setEditTriggers(QTableWidget.NoEditTriggers)  # read-only
    tableView.verticalHeader().setDefaultSectionSize(10)    # row height

    # Provide slot that updates data model & triggers GUI update
    # https://www.riverbankcomputing.com/static/Docs/PyQt5/signals_slots.html
    @pyqtSlot(str, str)
    def update_gui(name, timestamp):
        model.appendRow( (QStandardItem(name), QStandardItem(timestamp)) )
        tableView.scrollToBottom()

    # Connect sink event signal to slot
    # Do note: event_signal is static, but it has to be accessed through instance
    # (via class instance) in order to be "bound" (expose the .connect() method)
    graph_thread.event_signal.connect(update_gui)

    # Start graph thread
    graph_thread.start(QThread.LowPriority)

    # Start GUI event loop
    tableView.show()
    app.exec_()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument(
        "--system-plugin-path", type=str, default=None,
        help="Specify folder for system plugins (recursive!). "
             "Alternatively, set BABELTRACE_PLUGIN_PATH (non-recursive!)"
    )
    parser.add_argument(
        "--plugin-path", type=str, default="./python/",
        help="Path to 'bt_user_can.(so|py)' plugin"
    )
    parser.add_argument(
        "--CANSource-data-path", type=str, default="./test.data",
        help="Path to test data required by bt_user_can"
    )
    parser.add_argument(
        "--CANSource-dbc-path", type=str, default="./database.dbc",
        help="Path to DBC (CAN Database) required by bt_user_can"
    )

    # Add parameters to globals
    globals().update(vars(parser.parse_args()))

    load_plugins()
    main()