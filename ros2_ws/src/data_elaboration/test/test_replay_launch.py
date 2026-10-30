"""Replay composition must never open sensor devices or start command handlers."""

import ast
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

SRC = Path(__file__).resolve().parents[2]


def launch_actions(path):
    tree = ast.parse(path.read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
              and n.name == 'generate_launch_description')
    # Execute the actual launch factory with inert actions; never initialize ROS.
    class Endpoint:
        def __getattr__(self, name):
            return self
    scope = dict(LaunchDescription=list, Topics=Endpoint(), SensorTopics=Endpoint(),
                 LaunchConfiguration=lambda name: name, FindPackageShare=lambda name: name,
                 PathJoinSubstitution=lambda parts: '/'.join(parts),
                 PythonLaunchDescriptionSource=lambda path: path,
                 IncludeLaunchDescription=lambda path: NS(include=path),
                 DeclareLaunchArgument=lambda *a, **k: NS(argument=a[0]),
                 Node=lambda **kw: NS(**kw), OpaqueFunction=lambda **kw: NS(**kw),
                 check_mqtt_config=lambda context: [])
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), 'exec'), scope)
    return scope['generate_launch_description']()


class ReplayLaunchTests(unittest.TestCase):
    def test_top_level_only_includes_processing_and_telemetry(self):
        actions = launch_actions(SRC/'orchestrator/launch/replay_system.launch.py')
        self.assertEqual([a.include.split('/')[0] for a in actions],
                         ['data_elaboration', 'communication_web'])

    def test_all_replay_nodes_use_bag_clock_and_no_command_gateway(self):
        nodes = []
        for path in ('data_elaboration/launch/replay_data_elaboration.launch.py',
                     'communication_web/launch/replay_communication.launch.py'):
            nodes.extend(a for a in launch_actions(SRC/path) if hasattr(a, 'executable'))
        self.assertEqual(len(nodes), 5)
        self.assertNotIn('command_gateway_node', [n.executable for n in nodes])
        for node in nodes:
            self.assertEqual(node.parameters[-1], {'use_sim_time': True})


if __name__ == '__main__':
    unittest.main()
