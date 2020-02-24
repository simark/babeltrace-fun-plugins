#!/usr/bin/env python3
# *_* coding: utf-8 *_*

"""
Creates and runs a graph with a can.CANSource source and in-app sink, which delegates stream info to the GUI.
A more complex example with all the bells and whistles.
---
Please note: libbabeltrace2 python library (bt2) depends on its core C library.
---
LD_LIBRARY_PATH=[babeltrace2 build folder]/src/lib/.libs/
BABELTRACE_PLUGIN_PATH = [babeltrace2 build folder]/src/plugins/[plugin name]
LIBBABELTRACE2_PLUGIN_PROVIDER_DIR = [babeltrace2 build folder]/src/python-plugin-provider/.libs/
"""

import bt2
from bt2 import field_class

from PyQt5.Qt import *
from PyQt5.QtWidgets import *

# import local modules
from graph.model import AppendableTableModel
from graph.utils import load_plugins, cmd_parser


@bt2.plugin_component_class
class EventBufferSink(bt2._UserSinkComponent):
    """
    Sink component that stores event messages in provided EventBuffer.
    """

    def __init__(self, config, params, obj):
        self._port = self._add_input_port("in")
        (self._tableModel, self._treeModel) = obj

        # event id -> model update handler
        self._update = {}

    def _user_graph_is_configured(self):
        self._it = self._create_message_iterator(self._port)

    def _user_consume(self):
        msg = next(self._it)

        if type(msg) == bt2._StreamBeginningMessageConst:

            # Event class payload field parsing
            #
            # More info:
            #
            # Common Trace Format (CTF) documentation
            #   https://diamon.org/ctf/
            #
            # C documentation for Stream / Event / Field classes
            #   https://babeltrace.org/docs/v2.0/libbabeltrace2/group__api-tir-stream-cls.html
            #   https://babeltrace.org/docs/v2.0/libbabeltrace2/group__api-tir-ev-cls.html
            #   https://babeltrace.org/docs/v2.0/libbabeltrace2/group__api-tir-ev-cls.html#api-tir-ev-cls-prop-p-fc
            #   https://babeltrace.org/docs/v2.0/libbabeltrace2/group__api-tir-fc.html
            #
            # Python bindings
            #   babeltrace-2.0.0/src/bindings/python/bt2/bt2/stream_class.py
            #   babeltrace-2.0.0/src/bindings/python/bt2/bt2/field_class.py
            #   babeltrace-2.0.0/src/bindings/python/bt2/bt2/field.py
            #   babeltrace-2.0.0/tests/bindings/python/bt2/test_field.py
            #
            # text.details sink source
            #   babeltrace-2.0.0/src/plugins/text/details/write.c
            #       static void write_stream_class(struct details_write_ctx *ctx, const bt_stream_class *sc) definition
            #       static void write_event_class(struct details_write_ctx *ctx, const bt_event_class *ec) definition
            #       static void write_field_class(struct details_write_ctx *ctx, const bt_field_class *fc) definition
            #
            #
            #   if type(msg) == bt2._StreamBeginningMessageConst:
            #       list(msg.stream.cls.values())[0] ------------------------->  _EventClassConst
            #                                                                     defined @ event_class.py
            #       list(msg.stream.cls.values())[0].payload_field_class ----->  _[X]FieldClassConst
            #                                                                     defined @ field_class.py:
            #                                                                    _FIELD_CLASS_TYPE_TO_CONST_OBJ
            #   if type(msg) == bt2._EventMessageConst:
            #       list(msg.event.payload_field.values())[0] ---------------->  _[X]FieldConst
            #                                                                     defined @ field.py:
            #                                                                    _FIELD_CLASS_TYPE_TO_OBJ
            # How the tree model + view update handlers are built:
            #
            # for event_class in msg.stream.cls.values()
            #  |- calls parse_field_class(for toplevel field class, tree root node)
            #      |
            #      -> parse_field_class(current field class, parent tree node)
            #      '   |- creates the class_item tree node for current field class & appends it to parent tree node
            #      '   |- depending on the type of field class
            #      '   '   |- starts traversal of any sub-field classes by
            #      '   '   '  calling parse_field_class(sub-field class, class_item)
            #      '   '   '   |
            #      '   '   '   -> parse_field_class(...)
            #      '   '   '         - [recursive operation]
            #      '   '   |<------- - returns (tree node for sub-field class, payload handler for sub-field class)
            #      '   '   |
            #      '   '   | (the sub-field payload handlers are stored)
            #      '   '   |
            #      '   '   |- creates payload handler for current field class, which will later, at the time of call,
            #      '   '   '  be provided with the payload field which corresponds to the field class at the time of
            #      '   '   '  handler creation in parse_field_class(...)
            #      '   '   '  The payload handler
            #      '   '   '   |- updates the tree node of the current field class
            #      '   '   '   |  (+ notifies the view, done internally by QStandardItem)
            #      '   '   '   |- unpacks the current payload field into sub-fields and
            #      '   '   '   |- calls corresponding sub-field handlers for the unpacked sub-fields
            #      '   '   '
            #  |<----------|- returns the (class_item tree node, payload handler)
            #  |
            #  |- on event_class level only, augments the retrieved payload handler by defining a new handler,
            #  |  which
            #  |   |- handles event counting functionality (increments counter + updates the Count column)
            #  |   |- calls the retrieved payload handler
            #  |
            #  |- stores the new payload handler in an [event.id]-indexed dict, which will be later used to call the
            #     appropriate payload handler for a retrieved message in the _EventMessageConst stage
            #
            #
            # The following code requires a solid understanding of python closures and since people usually stop at
            # "closures in python are late binding", I want to elaborate on this:
            #
            #   When you define a function / lambda *in* a function, and the defined, *inner* function uses a variable
            #   from the *outer* function scope,
            #   that variable is a 'lexically bound free variable' from the *inner* function's perspective, which
            #   - references the variable (not the object the variable points to!) in the outer scope
            #   - uses the value of the outer scope variable at the time of the call (not at the time of definition!)
            #   - can outlive the outer scope
            #
            #   Python achieves this by storing the variable-to-object mapping (cell object) of the variable
            #   in the __closure__ property of the defined function.
            #
            #   Functions defined in the same outer scope share the *same* cell object for the same variables.
            #
            #   If the variable in the outer scope is made unavailable because the outer scope is closed or shadowed
            #   (the latter happens during a recursive call), a new, separate cell object is created.
            #
            # More info:
            #   https://stackoverflow.com/questions/12919278/how-to-define-free-variable-in-python
            #   https://www.python.org/dev/peps/pep-0227/
            #   https://gist.github.com/DmitrySoshnikov/700292

            # Parse event classes
            for event_class in msg.stream.cls.values():

                # Parse field classes + attach update handlers recursively
                def parse_field_class(parent_item, child_class, child_columns):

                    # Create QStandardItem objects for columns and make them available as attributes of first column
                    # (which is also the node of this level)
                    (class_item, class_item.type, class_item.count, class_item.last_value) = column_items = [
                        QStandardItem(column) for column in child_columns
                    ]
                    parent_item.appendRow(column_items)

                    # Set monospaced font for "last_value" column, for easier value comparison
                    class_item.last_value.setFont(QFont("Monospace"))

                    if any([type(child_class) == cls for cls in (
                        field_class._BoolFieldClassConst,
                        field_class._BitArrayFieldClassConst,
                        field_class._StringFieldClassConst
                    )]):
                        def update_scalar(payload):
                            # No need to bind item via default argument, since we go out of the outer scope
                            class_item.last_value.setText(str(payload))
                            return None  # No subelements, so no update view handler calls
                        return (class_item, update_scalar)

                    elif issubclass(type(child_class), field_class._IntegerFieldClassConst):
                        def update_integer(payload):
                            class_item.last_value.setText(f"{int(payload):6}")
                            return None
                        return (class_item, update_integer)

                    elif issubclass(type(child_class), field_class._RealFieldClassConst):
                        def update_integer(payload):
                            class_item.last_value.setText("{:9.3f}".format(float(payload)))
                            return None
                        return (class_item, update_integer)

                    elif type(child_class) == field_class._EnumerationFieldClassConst:
                        # item     -> enum current state
                        # children -> all enum states (name, value)
                        for member in child_class.values():
                            parse_field_class(
                                class_item, member.field_class,
                                # "Name",     "Type",                             "Count", "Last Value"
                                [member.name, type(member.field_class)._NAME[6:], '',      '-']
                            )

                        def update_enum(payload):
                            class_item.last_value.setText(str(payload)) # TODO
                        return (class_item, update_enum)

                    elif type(child_class) == field_class._ArrayFieldClass:
                        # item     -> length, in-line state
                        # children -> array elements
                        # In case of dynamic arrays, the number of children can change! (Tree is modified!)
                        def update_array(payload):
                            class_item.last_value.setText(str(payload)) # TODO
                        return (class_item, update_array)

                    elif type(child_class) == field_class._StructureFieldClassConst:
                        # item      -> in-line state
                        # children  -> structure elements

                        sub_handler = []

                        for member in child_class.values():
                            sub_handler.append(
                                parse_field_class(
                                    class_item, member.field_class,
                                    # "Name",     "Type",                             "Count", "Last Value"
                                    [member.name, type(member.field_class)._NAME[6:], '',      '-']
                                )[1] # handler only
                            )

                        def update_struct(payload):
                            # Update in-line info for container
                            class_item.last_value.setText(str(payload))
                            # Update members
                            for shp in zip(sub_handler, payload.values()):
                                shp[0](shp[1]) # sub handler for payload member ( payload member instance )
                        return (class_item, update_struct)

                    elif type(child_class) == field_class._OptionFieldClassConst:
                        # item   -> option enabled flag, in-line state
                        # child  -> option data struct, with values displayed if enabled
                        def update_option(payload):
                            class_item.last_value.setText(str(payload)) # TODO
                        return (class_item, update_option)

                    elif type(child_class) == field_class._VariantFieldClassConst:
                        # item      -> selector, selected data struct, in-line state
                        # children  -> all possible data structs, selected one has values displayed
                        def update_variant(payload):
                            class_item.last_value.setText(str(payload)) # TODO
                        return (class_item, update_variant)

                    else:
                        print(f"{type(child_class)} not handled!")

                (item, update_handler) = parse_field_class(
                    self._treeModel.invisibleRootItem(), event_class.payload_field_class,
                    # "Name",                                  "Type",                                          "Count", "Last Value"
                    [f"{event_class.id} : {event_class.name}", type(event_class.payload_field_class)._NAME[6:], '0',     '-']
                    # Do note that for "Type", we actually strip the "Const" prefix off _NAME to keep the column short
                )

                # Augment the payload handler with counting functionality
                # Toplevel field class (event_class.payload_field_class) is in the same row as event class
                #
                # We need to bind the current iteration's item / update_handler objects via default arguments,
                # since we remain in the same outer scope during for loop iterations.
                item.count_value = 0
                def update_event_class(payload, item=item, update_handler=update_handler):
                    item.count_value += 1
                    item.count.setText(str(item.count_value))

                    update_handler(payload)

                self._update[event_class.id] = update_event_class

            # Notify view that the _treeModel changed
            self._treeModel.modelReset.emit()

        if type(msg) == bt2._EventMessageConst:
            # Save event to buffer
            self._tableModel.append((msg.default_clock_snapshot.value, msg.event.name, str(msg.event.payload_field)))
            self._update[msg.event.id](msg.event.payload_field)

# MainWindow
#
class MainWindow(QMainWindow):

    def __init__(self, tableModel, treeModel):
        super().__init__()
        self._tableModel = tableModel
        self._treeModel = treeModel

        self.setWindowTitle("Advanced Babeltrace2 GUI demo")

        # Table view
        self._tableView = QTableView()
        self._tableView.setModel(tableModel)

        self._tableView.setEditTriggers(QTableWidget.NoEditTriggers)    # read-only
        self._tableView.verticalHeader().setDefaultSectionSize(10)      # row height
        self._tableView.horizontalHeader().setStretchLastSection(True)  # last column resizes to widget width

        # Tree view
        self._treeView = QTreeView()
        self._treeView.setModel(self._treeModel)
        self._treeModel.modelReset.connect(self._treeViewModelReset)
        self._treeView.header().setSectionsMovable(False)
        self._treeView.header().setSectionResizeMode(QHeaderView.ResizeToContents) # Resize automatically (used @ init)

        # Statistics label
        self._statLabel = QLabel("Events (processed/loaded): - / -")

        # Refresh checkbox
        self._followCheckbox = QCheckBox("Follow events")
        self._followCheckbox.setChecked(True)

        # Layout
        self._layout = QGridLayout()
        self._splitter = QSplitter()

        # See https://doc.qt.io/qt-5/qgridlayout.html#addWidget-2
        #
        #   0               1
        # 0 [ QSplitter                        ]
        #   [ [< treeView ] [< tableView     ] ]
        #
        # 1 [< statLabel  ] [followCheckbox   >]
        #
        self._splitter.addWidget(self._treeView)
        self._splitter.addWidget(self._tableView)
        self._layout.addWidget(self._splitter, 0, 0, 1, 2)

        self._layout.addWidget(self._statLabel, 1, 0)
        self._layout.addWidget(self._followCheckbox, 1, 1, 1, 1, Qt.AlignRight)

        self._mainWidget = QWidget()
        self._mainWidget.setLayout(self._layout)

        self.setCentralWidget(self._mainWidget)

        # Widget sizes
        self._splitter.setStretchFactor(0, 55)
        self._splitter.setStretchFactor(1, 45)
        self.resize(850, 450)

    @pyqtSlot()
    def _treeViewModelReset(self):
        # Pre-set up column width to fit all sub-item content + prevent the user from moving/resizing columns
        self._treeView.expandAll()
        self._treeView.header().setSectionResizeMode(QHeaderView.Fixed)
        self._treeView.collapseAll()

    # Timer handler, provided by QObject
    # https://doc.qt.io/qt-5/qtimer.html#alternatives-to-qtimer
    @pyqtSlot()
    def timerEvent(self, QTimerEvent):

        # Statistics
        self._statLabel.setText(f"Events (processed/loaded): {len(self._tableModel._table)} / {self._tableModel.rowCount()}")

        # Follow events
        if self._followCheckbox.isChecked():
            # QTableView also provides scrollToBottom(), but that method seems to have issues
            # with skipping multiple rows - rows appear to "bounce"
            self._tableView.scrollTo(self._tableModel.index(self._tableModel.rowCount() - 1, 0), QAbstractItemView.PositionAtBottom)


# GUI Application
def main():
    global CANSource_data_path, CANSource_dbc_path
    global plugins

    app = QApplication([])

    # Data models
    tableModel = AppendableTableModel(('Timestamp', 'Event', 'Payload'))

    treeModel = QStandardItemModel()
    treeModel.setHorizontalHeaderLabels(("Name", "Type", "Count", "Last Value"))

    # Create graph and add components
    graph = bt2.Graph()

    source = plugins['can'].source_component_classes['CANSource']
    graph_source = graph.add_component(source, 'source',
       params=bt2.MapValue({
           'inputs': bt2.ArrayValue([CANSource_data_path]),
           'databases': bt2.ArrayValue([CANSource_dbc_path])
       })
    )

    graph_sink = graph.add_component(EventBufferSink, 'sink', obj=(tableModel, treeModel))

    # Connect components together
    graph.connect_ports(
        list(graph_source.output_ports.values())[0],
        list(graph_sink.input_ports.values())[0]
    )

    # Main window
    mainWindow = MainWindow(tableModel, treeModel)

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
    mainWindow.show()
    mainWindow.startTimer(100)  # Update stats & table refresh interval in ms

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
