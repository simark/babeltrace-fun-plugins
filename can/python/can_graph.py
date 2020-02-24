#!/usr/bin/env python3
# *_* coding: utf-8 *_*

"""
Several examples of running Babeltrace2 graphs within Python.

---
Please note: libbabeltrace2 python library (bt2) depends on its core C library.
---
LD_LIBRARY_PATH=[babeltrace2 build folder]/src/lib/.libs/
BABELTRACE_PLUGIN_PATH = [babeltrace2 build folder]/src/plugins/[plugin name]
LIBBABELTRACE2_PLUGIN_PROVIDER_DIR = [babeltrace2 build folder]/src/python-plugin-provider/.libs/
"""

import bt2

# import local modules
from graph.utils import load_plugins, cmd_parser


def graph_can_detail():
    """
    BT2 graph - dumps CANSource trace to stdout
    """
    global CANSource_data_path, CANSource_dbc_path
    global plugins

    # Create graph and add components
    graph = bt2.Graph()

    source = plugins['can'].source_component_classes['CANSource']
    graph_source = graph.add_component(source, 'test_source',
        # The plugin is actually capable of reading from multiple (list)
        # input and database files
        #
        # For the sake of simplicity, this script only supplies ONE
        # input and database file.
        #
        params=bt2.MapValue({
            'inputs' : bt2.ArrayValue([CANSource_data_path]),
            'databases' : bt2.ArrayValue([CANSource_dbc_path])
        })
    )

    sink = plugins['text'].sink_component_classes['details']
    graph_sink = graph.add_component(sink, 'test_sink')

    # Connect components together

    # Do note that that input/output ports can be arbitrarily named
    # The bt_plugin_can.CANSource uses the input file path for port name
    #
    # So we will ignore the port name and connect the first available port
    # from the component
    #
    graph.connect_ports(
        list(graph_source.output_ports.values())[0],
        list(graph_sink.input_ports.values())[0]
    )

    # Run graph
    graph.run()


def graph_can_ctf():
    """
    BT2 graph - dumps CANSource trace to CTF
    """
    global CANSource_data_path, CANSource_dbc_path
    global plugins

    # Create graph and add components
    graph = bt2.Graph()

    source = plugins['can'].source_component_classes['CANSource']
    graph_source = graph.add_component(source, 'test_source',
        params=bt2.MapValue({
            'inputs': bt2.ArrayValue([CANSource_data_path]),
            'databases': bt2.ArrayValue([CANSource_dbc_path])
        })
    )

    sink = plugins['ctf'].sink_component_classes['fs']
    graph_sink = graph.add_component(sink, 'test_sink',
        params=bt2.MapValue({
            'path': './ctf-full'
        })
    )

    # Connect components together
    graph.connect_ports(
        list(graph_source.output_ports.values())[0],
        list(graph_sink.input_ports.values())[0]
    )

    # Run graph
    graph.run()


def graph_can_filter_ctf():
    """
    BT2 graph - trims CANSource

    You need to provide an implementation of
        def _user_seek_ns_from_origin(self, ns_from_origin):
    in bt2._UserMessageIterator in order to make it work

    otherwise trimmer fails with
        Cannot make upstream message iterator initially seek

    This has been worked around in the python version of bt_plugin_can,
    however the C variant does not have this fix yet!
    """
    global CANSource_data_path, CANSource_dbc_path
    global plugins

    # Create graph and add components
    graph = bt2.Graph()

    source = plugins['can'].source_component_classes['CANSource']
    graph_source = graph.add_component(source, 'test_source',
        params=bt2.MapValue({
            'inputs' : bt2.ArrayValue([CANSource_data_path]),
            'databases' : bt2.ArrayValue([CANSource_dbc_path])
        })
    )

    filter = plugins['utils'].filter_component_classes['trimmer']
    graph_filter = graph.add_component(filter, 'test_filter',
        params=bt2.MapValue({
            'begin' : '0.000',
            'end' : '1000.000'
        })
    )

    sink = plugins['ctf'].sink_component_classes['fs']
    graph_sink = graph.add_component(sink, 'test_sink',
        params=bt2.MapValue({
            'path': './ctf-filtered'
        })
    )

    # Connect components together
    graph.connect_ports(
        list(graph_source.output_ports.values())[0],
        list(graph_filter.input_ports.values())[0]
    )
    graph.connect_ports(
        list(graph_filter.output_ports.values())[0],
        list(graph_sink.input_ports.values())[0]
    )

    # Run graph
    graph.run()


def graph_ctf_filter_ctf():
    """
    BT2 graph - trims existing CTF trace

    With the repo version of bt_plugin_gui, the utils.trimmer will fail with
      Babeltrace 2 library postcondition not satisfied;
      Packet message has no default clock snapshot:

    This seems to be a limitation of the 2.0.0. version of utils.trimmer filter.
    You can work around it by extending the CANSource to generate a packet-enabled stream.

    This has been worked around in the python version of bt_plugin_can,
    however the C variant does not have this fix yet!
    """
    global CANSource_data_path, CANSource_dbc_path
    global plugins

    # Create graph and add components
    graph = bt2.Graph()

    source = plugins['ctf'].source_component_classes['fs']
    graph_source = graph.add_component(source, 'test_source',
        params=bt2.MapValue({
            # Can be provided with multiple inputs
            'inputs' : bt2.ArrayValue(['./ctf-full/trace']),
            'force-clock-class-origin-unix-epoch' : bt2.BoolValue(False)
        })
    )

    filter = plugins['utils'].filter_component_classes['trimmer']
    graph_filter = graph.add_component(filter, 'test_filter',
        params=bt2.MapValue({
            'begin' : '0.000',
            'end' : '0.001'
        })
    )

    sink = plugins['ctf'].sink_component_classes['fs']
    graph_sink = graph.add_component(sink, 'test_sink',
        params=bt2.MapValue({
            'path' : './ctf-filtered'
        })
    )

    # Connect components together
    graph.connect_ports(
        list(graph_source.output_ports.values())[0],
        list(graph_filter.input_ports.values())[0]
    )
    graph.connect_ports(
        list(graph_filter.output_ports.values())[0],
        list(graph_sink.input_ports.values())[0]
    )

    # Run graph
    graph.run()

# build list of examples that can be run from the command line
cmd_examples = {
    'can_detail' : graph_can_detail,
    'can_ctf' : graph_can_ctf,
    'can_filter_ctf' : graph_can_filter_ctf,
    'ctf_filter_ctf' : graph_ctf_filter_ctf
}

def main():
    global example

    cmd_examples[example]()

if __name__ == "__main__":
    global system_plugin_path, plugin_path
    global plugins

    # Parse command line and add parsed parameters to globals
    parser = cmd_parser(__doc__)

    # More info:
    # https://stackoverflow.com/questions/37094448/is-there-a-clean-way-to-write-a-one-line-help-per-choice-for-argparse-choices
    parser.add_argument(
        "example",
        choices=cmd_examples.keys(),
        help="\n".join([f"{example[0]}: {example[1].__doc__}" for example in cmd_examples.items()])
    )

    globals().update(vars(parser.parse_args()))

    plugins = load_plugins(system_plugin_path, plugin_path)
    main()
