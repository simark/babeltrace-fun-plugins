"""
Common functionality shared between can_graph examples.
"""

import bt2
import argparse


def load_plugins(system_plugin_path, plugin_path, verbose=True):
    """
    Loads system & user plugins and returns them as a unified dict

    :param system_plugin_path: path to system plugins (searched recursively)
        - if None, uses default system paths and BABELTRACE_PLUGIN_PATH (non-recursive search)

    :param plugin_path: path to user plugins

    :return: dict with all found plugins
    """

    # Load plugins
    system_plugins = bt2.find_plugins_in_path(system_plugin_path) if system_plugin_path else bt2.find_plugins()
    user_plugins = bt2.find_plugins_in_path(plugin_path)

    assert system_plugins, "No system plugins found!"
    assert user_plugins, "No user plugins found!"

    if verbose:
        def describe_plugins(plugins):

            def describe_components(desc, component):
                for component in component:
                    print(
                        f'    {desc + " : " + component.name:20} : {str(component.description):85} : {str(component.help)}')

            for plugin in plugins:
                print(f'  {plugin.name:22} : {plugin.description} : {plugin.path}')

                describe_components("source", plugin.source_component_classes.values())
                describe_components("filter", plugin.filter_component_classes.values())
                describe_components("sink  ", plugin.sink_component_classes.values())
                print()

        print('System plugins:')
        describe_plugins(system_plugins)

        print('User specified plugins:')
        describe_plugins(user_plugins)

    # Convert _PluginSet to dict
    plugins = {
        **{plugin.name: plugin for plugin in system_plugins},
        **{plugin.name: plugin for plugin in user_plugins}
    }

    return plugins


def cmd_parser(description):
    """
    Argument parser used by all can_graph examples.
    The examples might additionally extend the parser.
    """
    parser = argparse.ArgumentParser(description=description, formatter_class=argparse.RawTextHelpFormatter)
    # More info: https://mkaz.blog/code/python-argparse-cookbook/
    parser.add_argument(
        "--system-plugin-path", type=str, default=None,
        help="Specify folder for system plugins (recursive!). "
             "Alternatively, set BABELTRACE_PLUGIN_PATH (non-recursive!)"
    )
    parser.add_argument(
        "--plugin-path", type=str, default="./",
        help="Path to 'bt_user_can.(so|py)' plugin"
    )
    parser.add_argument(
        "--CANSource-data-path", type=str, default="../test.data",
        help="Path to test data required by bt_user_can"
    )
    parser.add_argument(
        "--CANSource-dbc-path", type=str, default="../database.dbc",
        help="Path to DBC (CAN Database) required by bt_user_can"
    )

    return parser
