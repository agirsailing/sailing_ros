"""Check launch configuration without importing or starting ROS."""

import ast
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LaunchConfiguration:
    def __init__(self, name):
        self.name = name

    def perform(self, context):
        return context[self.name]


def launch_functions(name):
    path = ROOT / 'launch' / name
    tree = ast.parse(path.read_text(encoding='utf-8'))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    scope = {
        'Path': Path, 'LaunchConfiguration': LaunchConfiguration,
        'LaunchDescription': list,
        'DeclareLaunchArgument': lambda name, **kwargs: ('argument', name, kwargs),
        'PathJoinSubstitution': lambda items: items,
        'FindPackageShare': lambda name: name,
        'OpaqueFunction': lambda **kwargs: ('check', kwargs),
        'Node': lambda **kwargs: ('node', kwargs),
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), scope)
    return scope


class LaunchConfigTests(unittest.TestCase):
    def test_missing_secret_file_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'mqtt_config.yaml'
            for name in ['live_communication.launch.py', 'replay_communication.launch.py']:
                check = launch_functions(name)['check_mqtt_config']
                context = {'communication_web_mqtt_config_file': str(path)}
                with self.assertRaisesRegex(RuntimeError, 'mqtt_config.example.yaml'):
                    check(context)
            path.write_text('# Test placeholder only', encoding='utf-8')
            self.assertEqual(check(context), [])

    def test_live_and_replay_merge_both_files_without_enabling_replay_commands(self):
        for mode in ['live', 'replay']:
            actions = launch_functions(mode + '_communication.launch.py')['generate_launch_description']()
            nodes = [action[1] for action in actions if action[0] == 'node']
            self.assertEqual(len(nodes), 2 if mode == 'live' else 1)
            self.assertEqual(nodes[0]['executable'], 'telemetry_gateway_node')
            for node in nodes:
                self.assertEqual([p.name for p in node['parameters']], [
                    'communication_web_params_file', 'communication_web_mqtt_config_file'])
            self.assertLess(
                next(i for i, a in enumerate(actions) if a[0] == 'check'),
                next(i for i, a in enumerate(actions) if a[0] == 'node'))


if __name__ == '__main__':
    unittest.main()

