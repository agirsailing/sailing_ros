"""Run in a sourced ROS environment; bags and CSVs are confined to temporary dirs."""
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    'allbags_to_csv', Path(__file__).resolve().parents[1] / 'allbags_to_csv.py')
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


class ExportTests(unittest.TestCase):
    def test_filenames_preserve_distinct_topics(self):
        used = set()
        names = [exporter._topic_filename(name, used)
                 for name in ['/a/b', '/a_b', '/A_B', '/CON']]
        self.assertEqual(len({name.casefold() for name in names}), 4)
        self.assertNotEqual(names[-1], 'CON.csv')

    def test_missing_input_returns_error(self):
        with tempfile.TemporaryDirectory() as root, self.assertRaises(SystemExit) as error:
            exporter.main([root])
        self.assertEqual(error.exception.code, 2)

    def test_failed_bag_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / 'rosbag2_broken').mkdir()
            with patch.object(exporter, 'process_single_bag', side_effect=RuntimeError('broken')):
                self.assertEqual(exporter.main([root]), 1)

    @unittest.skipUnless(importlib.util.find_spec('rosbag2_py'), 'Requires ROS')
    def test_all_topics_and_fields_round_trip_both_storage_formats(self):
        import rosbag2_py
        from rclpy.serialization import serialize_message
        from sensor_msgs.msg import Imu
        from std_msgs.msg import String
        from tf2_msgs.msg import TFMessage
        from geometry_msgs.msg import TransformStamped
        from gps_msgs.msg import GPSFix

        for storage in ('mcap', 'sqlite3'):
            with self.subTest(storage=storage), tempfile.TemporaryDirectory() as root:
                root = Path(root)
                bag = root / 'rosbag2_test'
                writer = rosbag2_py.SequentialWriter()
                writer.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id=storage),
                            rosbag2_py.ConverterOptions('cdr', 'cdr'))
                imu = Imu()
                imu.header.stamp.sec = 123
                imu.header.frame_id = 'imu_link'
                imu.orientation.w = 1.0
                imu.orientation_covariance[0] = 0.12
                gps = GPSFix(latitude=45.4, longitude=9.2, speed=3.5)
                tf = TransformStamped()
                tf.child_frame_id = 'base_link'
                topics = [('/imu/data', 'sensor_msgs/msg/Imu', imu),
                          ('/gps/data', 'gps_msgs/msg/GPSFix', gps),
                          ('/tf', 'tf2_msgs/msg/TFMessage', TFMessage(transforms=[tf])),
                          ('/new/topic', 'std_msgs/msg/String', String(data='comma,\nquote"')),
                          ('/new_topic', 'std_msgs/msg/String', String(data='second')),
                          ('/empty', 'std_msgs/msg/String', None)]
                for index, (name, type_name, message) in enumerate(topics):
                    writer.create_topic(rosbag2_py.TopicMetadata(
                        id=index, name=name, type=type_name, serialization_format='cdr'))
                    if message is not None:
                        writer.write(name, serialize_message(message), 1000000000 + index)
                writer.write('/tf', serialize_message(TFMessage()), 2000000000)
                del writer

                self.assertEqual(exporter.main([str(root), '--output-dir', str(root / 'csv')]), 0)
                output = root / 'csv/test'
                self.assertEqual(len(list(output.glob('*.csv'))), len(topics))

                def rows(filename):
                    with (output / filename).open(encoding='utf-8', newline='') as stream:
                        return list(csv.DictReader(stream))

                row = rows('imu_data.csv')[0]
                self.assertEqual(row['timestamp_ns'], '1000000000')
                self.assertEqual(row['header.stamp.sec'], '123')
                self.assertEqual(row['orientation.w'], '1.0')
                self.assertEqual(json.loads(row['orientation_covariance'])[0], 0.12)
                self.assertEqual(rows('gps_data.csv')[0]['speed'], '3.5')
                transforms = rows('tf.csv')
                self.assertEqual(json.loads(transforms[0]['transforms'])[0]['child_frame_id'], 'base_link')
                self.assertEqual(json.loads(transforms[1]['transforms']), [])
                self.assertEqual(rows('new_topic.csv')[0]['data'], 'comma,\nquote"')
                self.assertEqual(rows('new_topic__2.csv')[0]['data'], 'second')
                self.assertEqual(rows('empty.csv'), [])
                with patch('rosidl_runtime_py.utilities.get_message', side_effect=ImportError('absent')):
                    self.assertEqual(exporter.main([str(bag), '--output-dir', str(root / 'failed')]), 1)
                self.assertFalse((root / 'failed/test').exists())


if __name__ == '__main__':
    unittest.main()
