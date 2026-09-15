"""Offline callback regressions: real algorithms, simulated ROS messages.

Load only each node class from its source so these checks never initialize ROS,
open hardware or execute the battery shutdown command.
"""

import ast
from collections import deque
import copy
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE))
from data_elaboration.processing.imu_filter import ImuFilter
from data_elaboration.processing.imu_frames import (
    quaternion_from_degrees, rotation_matrix,
    rotate_covariance, multiply,
)
from data_elaboration.processing.heading import choose_navigation_direction
from data_elaboration.processing.boat_height import (
    beam_direction, fuse_estimates, project_height, vertical_row,
)


class Message:
    DIRECTION_NONE = 0
    DIRECTION_GPS_COG = 1
    DIRECTION_COMPASS = 2

    def __init__(self):
        self.header = SimpleNamespace(
            stamp=SimpleNamespace(sec=1, nanosec=0), frame_id='sensor')
        self.range, self.min_range, self.max_range = 1.25, 0.0, 4.5
        self.linear_acceleration = SimpleNamespace(x=0.0, y=0.0, z=9.80665)
        self.angular_velocity = SimpleNamespace(x=0.0, y=0.0, z=1.0)
        self.orientation = SimpleNamespace(x=0.0, y=0.0, z=0.0, w=0.0)
        self.orientation_covariance = [-1.0] + [0.0] * 8
        self.angular_velocity_covariance = [0.0] * 9
        self.linear_acceleration_covariance = [0.0] * 9


def load_node(filename):
    tree = ast.parse((PACKAGE / 'data_elaboration' / filename).read_text())
    cls = next(item for item in tree.body if isinstance(item, ast.ClassDef))
    scope = dict(Node=object, math=math, copy=copy, BoatHeight=Message,
                 RollPitchYaw=Message, Bool=Message, subprocess=Mock(),
                 deque=deque, vertical_row=vertical_row, beam_direction=beam_direction,
                 project_height=project_height, fuse_estimates=fuse_estimates,
                 quaternion_from_degrees=quaternion_from_degrees, rotation_matrix=rotation_matrix,
                 rotate_covariance=rotate_covariance, multiply=multiply,
                 choose_navigation_direction=choose_navigation_direction,
                 seconds=lambda stamp: stamp.sec + stamp.nanosec * 1e-9,
                 GpsSummary=Message, Float64=Message)
    exec(compile(ast.Module(body=[cls], type_ignores=[]), filename, 'exec'), scope)
    node = object.__new__(scope[cls.name])
    node.get_logger = Mock()
    if filename == 'imu_node.py':
        node.frame_robotic = 'sensor'
        node.cov_orient = node.cov_vel = node.cov_acc = 0.0
        node.frame_aero = 'imu_link_frd'
        node.world_quaternion = quaternion_from_degrees(180, 0, 0)
        node.world_rotation = rotation_matrix(node.world_quaternion)
        node.aero_last_stamp = node.aero_last_yaw = None
        node.aero_continuous_yaw = 0.0
        node.aero_imu_pub, node.aero_rpy_pub = Mock(), Mock()
    return node, scope


class TopicProcessingTests(unittest.TestCase):
    def height_node(self):
        node, _ = load_node('ultrasonic_filter_node.py')
        node.height_pub = Mock()
        node.attitudes = deque()
        node.estimates = {}
        node.last_range_stamps = {}
        node.last_now = None
        node.max_range_age_s, node.max_attitude_age_s, node.max_pair_dt_s = 0.5, 0.1, 0.15
        node.positions = {'left': (1.8, 0.1, 0.4), 'right': (1.8, -0.1, 0.4)}
        node.beams = {'left': beam_direction(15, 0), 'right': beam_direction(-15, 0)}
        node.frames = {'left': 'ultrasonic_left', 'right': 'ultrasonic_right'}
        node.attitude_frame_id, node.reference_frame_id = 'imu', 'boat_waterline'
        node.min_downward_cosine = 0.5
        node.incidence_weight_power, node.max_disagreement_m = 8, 0.25
        node.get_clock = Mock()
        node.get_clock().now().nanoseconds = 1_000_000_000
        return node

    @staticmethod
    def attitude(nanosec=0, roll_deg=0):
        msg = Message()
        msg.header.stamp.sec = 1
        msg.header.stamp.nanosec = nanosec
        msg.header.frame_id = 'imu'
        msg.orientation.x = math.sin(math.radians(roll_deg) / 2)
        msg.orientation.w = math.cos(math.radians(roll_deg) / 2)
        msg.orientation_covariance[0] = 0
        return msg

    @staticmethod
    def range_sample(side, distance, nanosec=0):
        msg = Message()
        msg.header.stamp.sec = 1
        msg.header.stamp.nanosec = nanosec
        msg.header.frame_id = 'ultrasonic_' + side
        msg.range = distance
        return msg

    def test_height_requires_attitude_and_publishes_reference_frame(self):
        node = self.height_node()
        node.receive_left(self.range_sample('left', 1.4))
        node.height_pub.publish.assert_not_called()
        node.receive_attitude(self.attitude())
        node.get_clock().now().nanoseconds = 1_020_000_000
        sample = self.range_sample('left', 1.4, 20_000_000)
        node.receive_left(sample)
        result = node.height_pub.publish.call_args.args[0]
        self.assertAlmostEqual(result.height_m, 1.4 * math.cos(math.radians(15)) - 0.4)
        self.assertEqual(result.header.frame_id, 'boat_waterline')
        self.assertEqual(sample.header.frame_id, 'ultrasonic_left')
        self.assertEqual(result.header.stamp, sample.header.stamp)
        node.receive_left(sample)
        node.height_pub.publish.assert_called_once()

    def test_height_fuses_close_samples_and_excludes_old_or_invalid_other_side(self):
        node = self.height_node()
        node.receive_attitude(self.attitude())
        cosine = math.cos(math.radians(15))
        node.receive_left(self.range_sample('left', 1.4 / cosine))
        node.receive_right(self.range_sample('right', 1.5 / cosine))
        self.assertAlmostEqual(node.height_pub.publish.call_args.args[0].height_m, 1.05)
        node.get_clock().now().nanoseconds = 1_020_000_000
        node.receive_right(self.range_sample('right', float('inf'), 20_000_000))
        self.assertNotIn('right', node.estimates)
        node.receive_left(self.range_sample('left', 1.4 / cosine, 20_000_000))
        self.assertAlmostEqual(node.height_pub.publish.call_args.args[0].height_m, 1.0)
        # A right sample older than the pairing window must not enter fusion.
        node.get_clock().now().nanoseconds = 1_300_000_000
        node.receive_attitude(self.attitude(300_000_000))
        node.receive_right(self.range_sample('right', 1.5 / cosine, 300_000_000))
        self.assertAlmostEqual(node.height_pub.publish.call_args.args[0].height_m, 1.1)

    def test_height_rejects_stale_attitude_range_wrong_frames_and_invalid_quaternion(self):
        node = self.height_node()
        node.receive_attitude(self.attitude())
        node.get_clock().now().nanoseconds = 1_300_000_000
        node.receive_left(self.range_sample('left', 1.4, 300_000_000))
        node.height_pub.publish.assert_not_called()  # Attitude is too old.
        node.receive_attitude(self.attitude(300_000_000))
        wrong = self.range_sample('right', 1.4, 300_000_000)
        wrong.header.frame_id = 'wrong_frame'
        node.receive_right(wrong)
        node.height_pub.publish.assert_not_called()
        node.get_clock().now().nanoseconds = 2_000_000_000
        node.receive_right(self.range_sample('right', 1.4, 400_000_000))
        node.height_pub.publish.assert_not_called()  # Range is stale too.
        invalid = self.attitude()
        invalid.header.stamp.sec = 2
        invalid.orientation.w = 0
        node.receive_attitude(invalid)
        self.assertFalse(node.attitudes)

    def test_height_uses_attitude_at_each_measurement_time_and_resets_on_clock_jump(self):
        node = self.height_node()
        node.receive_attitude(self.attitude())
        node.get_clock().now().nanoseconds = 1_080_000_000
        node.receive_attitude(self.attitude(80_000_000, roll_deg=30))
        # Delayed range predates the new attitude: it must use the level sample.
        node.receive_left(self.range_sample('left', 1.4, 20_000_000))
        self.assertAlmostEqual(node.height_pub.publish.call_args.args[0].height_m,
                               1.4 * math.cos(math.radians(15)) - 0.4)
        node.get_clock().now().nanoseconds = 500_000_000
        node._now()
        self.assertFalse(node.attitudes)
        self.assertFalse(node.estimates)
        self.assertFalse(node.last_range_stamps)

    def test_rpy_degrees_match_quaternion_while_imu_keeps_si_units(self):
        node, _ = load_node('imu_node.py')
        node.filter = ImuFilter(0, 9.80665, 0.98, 0.2)
        node.imu_pub = Mock()
        node.rpy_pub = Mock()
        sample = Message()
        node.publish_attitude(sample)
        sample.header.stamp.nanosec = 100_000_000
        node.publish_attitude(sample)
        angles = node.rpy_pub.publish.call_args.args[0]
        imu = node.imu_pub.publish.call_args.args[0]
        self.assertAlmostEqual(angles.yaw_deg, math.degrees(0.1))
        self.assertAlmostEqual(angles.roll_deg, 0.0)
        self.assertAlmostEqual(angles.pitch_deg, 0.0)
        self.assertAlmostEqual(imu.orientation.z, math.sin(math.radians(angles.yaw_deg) / 2))
        self.assertAlmostEqual(imu.orientation.w, math.cos(math.radians(angles.yaw_deg) / 2))
        self.assertAlmostEqual(imu.angular_velocity.z, 1.0)  # rad/s, not deg/s
        self.assertEqual(angles.header, imu.header)
        self.assertEqual(sample.orientation_covariance[0], -1.0)
        self.assertEqual(imu.orientation_covariance[0], 0.0)

    def test_imu_does_not_publish_during_calibration_or_missing_vectors(self):
        node, _ = load_node('imu_node.py')
        node.filter = ImuFilter(2, 9.80665, 0.98, 0.2)
        node.imu_pub = Mock()
        node.rpy_pub = Mock()
        sample = Message()
        sample.linear_acceleration_covariance[0] = -1.0
        node.publish_attitude(sample)
        self.assertEqual(node.filter.count, 0)
        sample.linear_acceleration_covariance[0] = 0.0
        node.publish_attitude(sample)
        node.imu_pub.publish.assert_not_called()
        node.rpy_pub.publish.assert_not_called()

    @staticmethod
    def transformed_aero_sample(roll_deg=0, pitch_deg=0, yaw_deg=0, tick=0):
        # Simulate the documented imu_transformer body-only result; no ROS is run.
        msg = Message()
        msg.header.frame_id = 'imu_link_frd'
        msg.header.stamp.nanosec = tick * 20_000_000
        robot = quaternion_from_degrees(roll_deg, pitch_deg, yaw_deg)
        body = multiply(robot, quaternion_from_degrees(180, 0, 0))
        msg.orientation.x, msg.orientation.y, msg.orientation.z, msg.orientation.w = body
        msg.orientation_covariance = [1, 0.1, 0.2, 0.1, 2, 0.3, 0.2, 0.3, 3]
        msg.angular_velocity = SimpleNamespace(x=1, y=-2, z=-3)
        msg.linear_acceleration = SimpleNamespace(x=4, y=-5, z=-6)
        return msg

    def test_world_adapter_completes_aero_orientation_without_rotating_body_vectors_twice(self):
        node, _ = load_node('imu_node.py')
        raw = self.transformed_aero_sample(10, -20, 30)
        node.publish_aero(raw)
        output = node.aero_imu_pub.publish.call_args.args[0]
        angles = node.aero_rpy_pub.publish.call_args.args[0]
        self.assertAlmostEqual(angles.roll_deg, 10)
        self.assertAlmostEqual(angles.pitch_deg, 20)
        self.assertAlmostEqual(angles.yaw_deg, -30)
        expected = quaternion_from_degrees(10, 20, -30)
        actual = output.orientation
        dot = sum(a*b for a, b in zip((actual.x, actual.y, actual.z, actual.w), expected))
        self.assertAlmostEqual(abs(dot), 1)
        for field in ('angular_velocity', 'linear_acceleration',
                      'angular_velocity_covariance', 'linear_acceleration_covariance'):
            self.assertEqual(getattr(output, field), getattr(raw, field))
        self.assertEqual(output.header, raw.header)
        self.assertAlmostEqual(output.orientation_covariance[1], -0.1)
        self.assertAlmostEqual(raw.orientation_covariance[1], 0.1)

    def test_aero_yaw_starts_zero_unwraps_turns_and_resets_with_backwards_time(self):
        node, _ = load_node('imu_node.py')
        for tick, yaw in enumerate((0, 90, 180, 270, 360, 400)):
            sample = self.transformed_aero_sample(yaw_deg=yaw, tick=tick)
            node.publish_aero(sample)
            angles = node.aero_rpy_pub.publish.call_args.args[0]
            self.assertAlmostEqual(angles.yaw_deg, -yaw)
            self.assertAlmostEqual(angles.roll_deg, 0)
            self.assertAlmostEqual(angles.pitch_deg, 0)
        node.publish_aero(sample)  # Duplicate timestamp does not publish twice.
        self.assertEqual(node.aero_imu_pub.publish.call_count, 6)
        node.publish_aero(self.transformed_aero_sample())
        self.assertAlmostEqual(node.aero_rpy_pub.publish.call_args.args[0].yaw_deg, 0)

    def test_world_adapter_rejects_missing_orientation_and_wrong_frame(self):
        node, _ = load_node('imu_node.py')
        sample = self.transformed_aero_sample()
        sample.header.frame_id = 'imu_link_flu'
        node.publish_aero(sample)
        sample.header.frame_id = node.frame_aero
        sample.orientation_covariance[0] = -1
        node.publish_aero(sample)
        sample.orientation_covariance[0] = 0
        sample.orientation = SimpleNamespace(x=0, y=0, z=0, w=0)
        node.publish_aero(sample)
        node.aero_imu_pub.publish.assert_not_called()

    def test_estimator_consumes_mounted_vectors_without_applying_mounting_again(self):
        node, _ = load_node('imu_node.py')
        node.filter = Mock()
        node.filter.update.return_value = None
        mounted = Message()
        mounted.linear_acceleration.x, mounted.linear_acceleration.y = -2, 1
        mounted.angular_velocity.x, mounted.angular_velocity.y = -4, 3
        node.publish_attitude(mounted)
        _, accel, gyro = node.filter.update.call_args.args
        self.assertEqual(accel, (-2, 1, 9.80665))
        self.assertEqual(gyro, (-4, 3, 1))
        mounted.header.frame_id = 'raw_sensor_frame'
        node.publish_attitude(mounted)
        node.filter.update.assert_called_once()

    def test_robotic_and_aero_callbacks_publish_independently_in_the_same_node(self):
        node, _ = load_node('imu_node.py')
        node.imu_pub, node.rpy_pub = Mock(), Mock()
        node.filter = Mock()
        node.filter.roll = node.filter.pitch = node.filter.yaw = 0.0
        node.filter.update.return_value = ((0, 0, 9.80665), (0, 0, 0), (0, 0, 0, 1))
        node.publish_attitude(Message())
        node.imu_pub.publish.assert_called_once()
        node.aero_imu_pub.publish.assert_not_called()
        node.publish_aero(self.transformed_aero_sample())
        node.imu_pub.publish.assert_called_once()
        node.rpy_pub.publish.assert_called_once()
        node.aero_imu_pub.publish.assert_called_once()
        node.aero_rpy_pub.publish.assert_called_once()
        node.filter.update.assert_called_once()
        self.assertEqual(node.aero_imu_pub.publish.call_args.args[0].header.frame_id, node.frame_aero)

    def test_covariance_basis_change_preserves_cross_terms_and_unavailable_marker(self):
        rotation = rotation_matrix(quaternion_from_degrees(180, 0, 0))
        covariance = [1, 0.1, 0.2, 0.1, 2, 0.3, 0.2, 0.3, 3]
        result = rotate_covariance(rotation, covariance)
        expected = [1, -0.1, -0.2, -0.1, 2, 0.3, -0.2, 0.3, 3]
        for actual, value in zip(result, expected):
            self.assertAlmostEqual(actual, value)
        unknown = [-1] + [0] * 8
        self.assertEqual(rotate_covariance(rotation, unknown), unknown)

    def test_gps_summary_is_structured_and_distinguishes_direction_source(self):
        node, _ = load_node('heading_node.py')
        node.max_input_age_s, node.speed_threshold = 1.0, 0.5
        node.compass_x_sign = node.compass_y_sign = 1.0
        node.compass_x_bias = node.compass_y_bias = node.heading_offset_deg = 0.0
        node.last_now = None
        node.get_clock = Mock()
        node.get_clock().now().nanoseconds = 1_100_000_000
        node.get_clock().now().to_msg.return_value = SimpleNamespace(sec=1, nanosec=100_000_000)
        node.summary_pub, node.heading_pub = Mock(), Mock()
        node.gps = SimpleNamespace(header=Message().header, fix_valid=True,
                                   latitude_deg=59.3, longitude_deg=18.1,
                                   ground_speed_mps=2.0, course_deg=270.0)
        node.compass = SimpleNamespace(header=Message().header, vector=SimpleNamespace(x=0, y=100))
        node.publish_heading()
        msg = node.summary_pub.publish.call_args.args[0]
        self.assertEqual((msg.latitude_deg, msg.longitude_deg, msg.sog_mps), (59.3, 18.1, 2.0))
        self.assertEqual((msg.direction_source, msg.direction_deg), (Message.DIRECTION_GPS_COG, 270))
        self.assertTrue(msg.fix_valid and msg.direction_valid)
        self.assertEqual(msg.gps_stamp, node.gps.header.stamp)
        node.gps.ground_speed_mps = 0.1
        node.publish_heading()
        msg = node.summary_pub.publish.call_args.args[0]
        self.assertEqual((msg.direction_source, msg.direction_deg), (Message.DIRECTION_COMPASS, 90))
        # Missing GPS may still yield a valid compass direction.
        node.gps = None
        node.publish_heading()
        msg = node.summary_pub.publish.call_args.args[0]
        self.assertFalse(msg.fix_valid)
        self.assertTrue(math.isnan(msg.latitude_deg))
        self.assertTrue(msg.direction_valid)
        node.compass = None
        node.publish_heading()
        msg = node.summary_pub.publish.call_args.args[0]
        self.assertFalse(msg.direction_valid)
        self.assertEqual(msg.direction_source, Message.DIRECTION_NONE)
        self.assertTrue(math.isnan(msg.direction_deg))

    def test_battery_confirms_alarm_without_inventing_charge_percentage(self):
        node, scope = load_node('battery_monitor_node.py')
        node.low_samples = 0
        node.low_samples_required = 2
        node.shutdown_requested = False
        node.shutdown_enabled = False
        node.battery_pub = Mock()
        for raw, expected in ((True, False), (False, False), (True, False),
                              (True, True), (False, False)):
            node.publish_battery_state(SimpleNamespace(data=raw))
            self.assertIs(node.battery_pub.publish.call_args.args[0].data, expected)
        scope['subprocess'].run.assert_not_called()

    def test_battery_shutdown_is_requested_once_while_status_keeps_publishing(self):
        node, scope = load_node('battery_monitor_node.py')
        node.low_samples = 0
        node.low_samples_required = 1
        node.shutdown_requested = False
        node.shutdown_enabled = True
        node.shutdown_command = ['simulated-shutdown']
        node.battery_pub = Mock()
        scope['subprocess'].run.return_value.returncode = 0
        for _ in range(3):
            node.publish_battery_state(SimpleNamespace(data=True))
        scope['subprocess'].run.assert_called_once_with(['simulated-shutdown'], check=False)
        self.assertEqual(node.battery_pub.publish.call_count, 3)


if __name__ == '__main__':
    unittest.main()
