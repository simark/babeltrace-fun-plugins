#!/usr/bin/env python3
# *_* coding: utf-8 *_*

"""
Creates and runs the same graph as the babeltrace-fun-plugins/can/check.sh utility.
---
Please note: libbabeltrace2 python library (bt2) depends on its core C library.
MOST ISSUES will be averted if you INSTALL the library on your system.
---
If you still want to use the library without installation, set up the loader path
LD_LIBRARY_PATH=[babeltrace2 build folder]/src/lib/.libs/

And in order for python + system plugin loading
make sure that the following environment variables are set to their respective paths:

BABELTRACE_PLUGIN_PATH = [babeltrace2 build folder]/src/plugins/[plugin name]
LIBBABELTRACE2_PLUGIN_PROVIDER_DIR = [babeltrace2 build folder]/src/python-plugin-provider/.libs/
"""

import bt2

import os
import argparse


# globals
system_plugin_path = None
plugin_path = None
CANSource_data_path = None
CANSource_dbc_path = None

system_plugins = None
user_plugins = None


# Convert from _PluginSet to dict with plugin name as key
def plugin_dict(plugin_set):
    return {plugin.name : plugin for plugin in plugin_set}

def describe_components(component):
    for component in component:
        print(f'    {"source : " + component.name:20} : {str(component.description):85} : {str(component.help)}')

def describe_plugins(plugins):
    for plugin in plugins:
        print(f'  {plugin.name:22} : {plugin.description} : {plugin.path}')

        describe_components(plugin.source_component_classes.values())
        describe_components(plugin.filter_component_classes.values())
        describe_components(plugin.sink_component_classes.values())
        print()


# BT2 graph - dumps CANSource trace to stdout
def graph_can_detail():
    # Load required components from plugins
    sink = system_plugins['text'].sink_component_classes['details']
    source = user_plugins['can'].source_component_classes['CANSource']

    # Create graph and add components
    graph = bt2.Graph()

    graph_sink = graph.add_component(sink, 'test_sink')
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

# BT2 graph - dumps CANSource trace to CTF
def graph_can_ctf():
    # Load required components from plugins
    sink = system_plugins['ctf'].sink_component_classes['fs']
    source = user_plugins['can'].source_component_classes['CANSource']

    # Create graph and add components
    graph = bt2.Graph()

    graph_sink = graph.add_component(sink, 'test_sink',
        params=bt2.MapValue({
            'path': './ctf-full'
        })
    )

    graph_source = graph.add_component(source, 'test_source',
        params=bt2.MapValue({
            'inputs': bt2.ArrayValue([CANSource_data_path]),
            'databases': bt2.ArrayValue([CANSource_dbc_path])
        })
    )

    # Connect components together
    graph.connect_ports(
        list(graph_source.output_ports.values())[0],
        list(graph_sink.input_ports.values())[0]
    )

    # Run graph
    graph.run()

# BT2 graph - trims CANSource
#
# With the repo version of bt_plugin_gui, this will fail with
#   Cannot make upstream message iterator initially seek
#
# You need to provide an implementation of
#   def _user_seek_ns_from_origin(self, ns_from_origin):
# in bt2._UserMessageIterator in order to make it work
#
def graph_can_filter_ctf():

    # Load required components from plugins
    sink = system_plugins['ctf'].sink_component_classes['fs']
    filter = system_plugins['utils'].filter_component_classes['trimmer']
    source = user_plugins['can'].source_component_classes['CANSource']

    # Create graph and add components
    graph = bt2.Graph()

    graph_sink = graph.add_component(sink, 'test_sink',
        params=bt2.MapValue({
            'path' : './ctf-filtered'
        })
    )
    graph_filter = graph.add_component(filter, 'test_filter',
        params=bt2.MapValue({
            'begin' : '0.000',
            'end' : '1000.000'
        })
    )
    graph_source = graph.add_component(source, 'test_source',
        params=bt2.MapValue({
            'inputs' : bt2.ArrayValue([CANSource_data_path]),
            'databases' : bt2.ArrayValue([CANSource_dbc_path])
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

# BT2 graph - trims existing CTF trace
#
# With the repo version of bt_plugin_gui, the utils.trimmer will fail with
#   Babeltrace 2 library postcondition not satisfied;
#   Packet message has no default clock snapshot:
#
# This seems to be a limitation of the 2.0.0. version of utils.trimmer filter.
# You can work around it by extending the CANSource to generate a packet-enabled stream.
#
def graph_ctf_filter_ctf():

    # Load required components from plugins
    sink = system_plugins['ctf'].sink_component_classes['fs']
    filter = system_plugins['utils'].filter_component_classes['trimmer']
    source = system_plugins['ctf'].source_component_classes['fs']

    # Create graph and add components
    graph = bt2.Graph()

    graph_sink = graph.add_component(sink, 'test_sink',
        params=bt2.MapValue({
            'path' : './ctf-filtered'
        })
    )
    graph_filter = graph.add_component(filter, 'test_filter',
        params=bt2.MapValue({
            'begin' : '0.000',
            'end' : '0.001'
        })
    )
    graph_source = graph.add_component(source, 'test_source',
        params=bt2.MapValue({
            # Can be provided with multiple inputs
            'inputs' : bt2.ArrayValue(['./ctf-full/trace']),
            'force-clock-class-origin-unix-epoch' : bt2.BoolValue(False)
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



def main():
    global system_plugins
    global user_plugins

    print(
        f'Current dir:          {os.getcwd()}\n'
        f'plugin_path:          {plugin_path}\n'
        f'CANSource_data_path:  {CANSource_data_path}\n'
        f'CANSource_dbc_path:   {CANSource_dbc_path}\n'
    )

    # Load plugins
    system_plugins_set = None
    if system_plugin_path:
        print('Overriding default system search method!')
        system_plugins_set = bt2.find_plugins_in_path(
            system_plugin_path, fail_on_load_error=True
        )
    else:
        system_plugins_set = bt2.find_plugins(
            find_in_std_env_var=True,
            find_in_user_dir=True,
            find_in_sys_dir=True,
            find_in_static=True,
            fail_on_load_error=True
        )
    if system_plugins_set:
        print('System plugins:')
        describe_plugins(system_plugins_set)
        system_plugins = plugin_dict(system_plugins_set)
    else:
        print('No system plugins found!')
        return

    user_plugins_set = bt2.find_plugins_in_path(plugin_path, fail_on_load_error=True)
    if user_plugins_set:
        print('User specified plugins:')
        describe_plugins(user_plugins_set)
        user_plugins = plugin_dict(user_plugins_set)
    else:
        print('No user specified plugins found!')
        return

    graph_can_filter_ctf()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument(
        '--system-plugin-path', type=str, default=None,
        help='Specify folder for system plugins (recursive!). Alternatively, set BABELTRACE_PLUGIN_PATH (non-recursive!)'
    )
    parser.add_argument(
        '--plugin-path', type=str, default='./python/',
        help='Path to "bt_user_can.(so|py)" plugin'
    )
    parser.add_argument(
        '--CANSource-data-path', type=str, default='./test.data',
        help='Path to test data required by bt_user_can'
    )
    parser.add_argument(
        '--CANSource-dbc-path', type=str, default='./database.dbc',
        help='Path to DBC (CAN Database) required by bt_user_can'
    )

    # Add parameters to globals
    globals().update(vars(parser.parse_args()))

    main()