"""Offline callback regressions: real algorithms, simulated ROS messages.

Load only each node class from its source so these checks never initialize ROS
or open hardware.
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
sys.path.insert(0, str(PACKAGE.parent / 'sail_common'))
from sail_common.freshness import is_fresh
from data_elaboration.processing.imu_filter import ImuFilter
from data_elaboration.processing.lever_arm import LeverArmCompensator
from data_elaboration.processing.imu_frames import (
    quaternion_from_degrees, rotation_matrix,
    rotate_covariance, multiply,
)
from data_elaboration.processing.boat_height import (
    beam_direction, fuse_estimates, project_height, vertical_row,
)


class Message:
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
    scope = dict(Node=object, math=math, copy=copy, Float64Stamped=Message, is_fresh=is_fresh,
                 time=SimpleNamespace(monotonic=lambda: 100.0),
                 deque=deque, vertical_row=vertical_row, beam_direction=beam_direction,
                 project_height=project_height, fuse_estimates=fuse_estimates,
                 quaternion_from_degrees=quaternion_from_degrees, rotation_matrix=rotation_matrix,
                 rotate_covariance=rotate_covariance, multiply=multiply,
                 seconds=lambda stamp: stamp.sec + stamp.nanosec * 1e-9)
    exec(compile(ast.Module(body=[cls], type_ignores=[]), filename, 'exec'), scope)
    node = object.__new__(scope[cls.name])
    node.get_logger = Mock()
    if filename == 'imu_node.py':
        node.max_sample_age_s, node.publish_rate_hz = 0.5, 0.0
        node._last_clock_ns = node._robotic_last_stamp = node._robotic_sample = None
        node.filter = ImuFilter(0, 9.80665, 0.98, 0.2)
        node.lever_arm = LeverArmCompensator((0, 0, 0), 0.2)
        node.get_clock = Mock()
        node.get_clock().now.return_value = SimpleNamespace(nanoseconds=1_100_000_000)
        node.frame_robotic = 'sensor'
        node.cov_orient = node.cov_vel = node.cov_acc = 0.0
        node.frame_aero = 'imu_link_frd'
        node.world_quaternion = quaternion_from_degrees(180, 0, 0)
        node.world_rotation = rotation_matrix(node.world_quaternion)
        node.aero_last_stamp = None
        node.aero_imu_pub = Mock()
    return node, scope


class TopicProcessingTests(unittest.TestCase):
    def assertQuaternionEqual(self, message, rpy):
        expected = quaternion_from_degrees(*rpy)
        q = message.orientation
        dot = sum(a*b for a, b in zip((q.x, q.y, q.z, q.w), expected))
        self.assertAlmostEqual(abs(dot), 1.0)

    def height_node(self):
        node, _ = load_node('ultrasonic_filter_node.py')
        node.height_pub = Mock()
        node.publish_rate_hz = 0.0
        node.latest_height = None
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

    def test_height_mounting_requires_five_finite_values_and_valid_tilts(self):
        node = self.height_node()
        node.get_parameters = Mock()
        node.list_parameters = Mock(return_value=SimpleNamespace(names=[]))
        node.left_mounting = [2.0, 0.2, 0.6, 15.0, 0.0]
        node.right_mounting = [2.0, -0.2, 0.6, -15.0, 0.0]
        node.left_frame_id, node.right_frame_id = 'ultrasonic_left', 'ultrasonic_right'
        node.max_incidence_deg, node.qos_depth = 60.0, 10
        node._validate_parameters()
        for side in ('left', 'right'):
            original = getattr(node, side + '_mounting')
            for invalid in ([0.0] * 3, [0.0] * 6,
                            [0.0, float('nan'), 0.0, 0.0, 0.0],
                            [0.0, 0.0, 0.0, 90.0, 0.0],
                            [0.0, 0.0, 0.0, 0.0, -90.0]):
                with self.subTest(side=side, mounting=invalid):
                    setattr(node, side + '_mounting', invalid)
                    with self.assertRaises(ValueError):
                        node._validate_parameters()
            setattr(node, side + '_mounting', original)
        for invalid_rate in (-1.0, math.nan, math.inf):
            node.publish_rate_hz = invalid_rate
            with self.assertRaisesRegex(ValueError, 'publish_rate_hz'):
                node._validate_parameters()
        for valid_rate in (0.0, 20.0):
            node.publish_rate_hz = valid_rate
            node._validate_parameters()

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
        self.assertAlmostEqual(result.value, 1.4 * math.cos(math.radians(15)) - 0.4)
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
        self.assertAlmostEqual(node.height_pub.publish.call_args.args[0].value, 1.05)
        node.get_clock().now().nanoseconds = 1_020_000_000
        node.receive_right(self.range_sample('right', float('inf'), 20_000_000))
        self.assertNotIn('right', node.estimates)
        node.receive_left(self.range_sample('left', 1.4 / cosine, 20_000_000))
        self.assertAlmostEqual(node.height_pub.publish.call_args.args[0].value, 1.0)
        # A right sample older than the pairing window must not enter fusion.
        node.get_clock().now().nanoseconds = 1_300_000_000
        node.receive_attitude(self.attitude(300_000_000))
        node.receive_right(self.range_sample('right', 1.5 / cosine, 300_000_000))
        self.assertAlmostEqual(node.height_pub.publish.call_args.args[0].value, 1.1)

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
        self.assertAlmostEqual(node.height_pub.publish.call_args.args[0].value,
                               1.4 * math.cos(math.radians(15)) - 0.4)
        node.get_clock().now().nanoseconds = 500_000_000
        node._now()
        self.assertFalse(node.attitudes)
        self.assertFalse(node.estimates)
        self.assertFalse(node.last_range_stamps)

    def test_raw_filter_publishes_quaternion_and_keeps_si_units(self):
        node, _ = load_node('imu_node.py')
        node.filter = ImuFilter(0, 9.80665, 0.98, 0.2)
        node.imu_pub = Mock()
        sample = Message()
        node.publish_attitude(sample)
        sample.header.stamp.nanosec = 100_000_000
        node.publish_attitude(sample)
        imu = node.imu_pub.publish.call_args.args[0]
        self.assertAlmostEqual(imu.orientation.z, math.sin(0.1 / 2))
        self.assertAlmostEqual(imu.orientation.w, math.cos(0.1 / 2))
        self.assertAlmostEqual(imu.angular_velocity.z, 1.0)  # rad/s, not deg/s
        self.assertEqual(imu.header, sample.header)
        self.assertEqual(sample.orientation_covariance[0], -1.0)
        self.assertEqual(imu.orientation_covariance[0], 0.0)

    def test_height_periodic_output_uses_latest_result_and_original_stamp(self):
        node = self.height_node()
        node.publish_rate_hz = 20.0
        node.receive_attitude(self.attitude())
        node.receive_left(self.range_sample('left', 1.4))
        node.get_clock().now().nanoseconds = 1_020_000_000
        node.receive_left(self.range_sample('left', 1.5, 20_000_000))
        node.height_pub.publish.assert_not_called()
        node.publish_height()
        result = node.height_pub.publish.call_args.args[0]
        self.assertAlmostEqual(result.value, 1.5 * math.cos(math.radians(15)) - 0.4)
        self.assertEqual(result.header.stamp.nanosec, 20_000_000)
        node.get_clock().now().nanoseconds = 1_070_000_000
        node.publish_height()
        self.assertEqual(node.height_pub.publish.call_count, 2)
        self.assertEqual(node.height_pub.publish.call_args.args[0].header, result.header)
        node.get_clock().now().nanoseconds = 1_521_000_000
        node.publish_height()
        self.assertEqual(node.height_pub.publish.call_count, 2)
        self.assertIsNone(node.latest_height)

    def test_height_timer_expires_oldest_fusion_input_and_clears_on_clock_rewind(self):
        node = self.height_node()
        node.publish_rate_hz = 20.0
        node.receive_attitude(self.attitude())
        node.receive_left(self.range_sample('left', 1.4))
        node.get_clock().now().nanoseconds = 1_080_000_000
        node.receive_right(self.range_sample('right', 1.4, 80_000_000))
        node.publish_height()
        self.assertEqual(node.height_pub.publish.call_count, 1)
        node.get_clock().now().nanoseconds = 1_501_000_000
        node.publish_height()  # The triggering right sample alone is still fresh.
        self.assertEqual(node.height_pub.publish.call_count, 1)
        self.assertIsNone(node.latest_height)
        node.get_clock().now().nanoseconds = 2_000_000_000
        attitude, reading = self.attitude(), self.range_sample('left', 1.4)
        attitude.header.stamp.sec = reading.header.stamp.sec = 2
        node.receive_attitude(attitude)
        node.receive_left(reading)
        self.assertIsNotNone(node.latest_height)
        node.get_clock().now().nanoseconds = 1_900_000_000
        node.publish_height()
        self.assertIsNone(node.latest_height)

    def test_height_invalid_inputs_do_not_repeat_obsolete_fusion_or_starve_good_side(self):
        node = self.height_node()
        node.publish_rate_hz = 20.0
        node.receive_attitude(self.attitude())
        node.receive_left(self.range_sample('left', 1.4))
        node.receive_right(self.range_sample('right', 1.4))
        node.get_clock().now().nanoseconds = 1_020_000_000
        node.receive_right(self.range_sample('right', math.inf, 20_000_000))
        node.publish_height()
        node.height_pub.publish.assert_not_called()
        node.receive_left(self.range_sample('left', 1.4, 20_000_000))
        node.get_clock().now().nanoseconds = 1_040_000_000
        node.receive_right(self.range_sample('right', math.inf, 40_000_000))
        node.publish_height()
        node.height_pub.publish.assert_called_once()
        invalid = self.attitude(40_000_000)
        invalid.orientation.w = 0.0
        node.receive_attitude(invalid)
        node.publish_height()
        node.height_pub.publish.assert_called_once()
        self.assertIsNone(node.latest_height)

    def test_height_conflict_and_monotonic_expiry_stop_republication(self):
        node = self.height_node()
        node.publish_rate_hz = 20.0
        node.receive_attitude(self.attitude())
        node.receive_left(self.range_sample('left', 1.4))
        node.receive_right(self.range_sample('right', 2.4))
        node.publish_height()
        node.height_pub.publish.assert_not_called()
        node.get_clock().now().nanoseconds = 1_020_000_000
        node.receive_right(self.range_sample('right', 1.4, 20_000_000))
        output, stamps, _ = node.latest_height
        node.latest_height = (output, stamps, 99.4)  # Monotonic mock is 100.
        node.publish_height()
        node.height_pub.publish.assert_not_called()
        self.assertIsNone(node.latest_height)

    def fused_sample(self, roll=10, pitch=20, yaw=30, nanos=0):
        msg = Message()
        msg.header.stamp.nanosec = nanos
        q = quaternion_from_degrees(roll, pitch, yaw)
        msg.orientation = SimpleNamespace(**dict(zip(('x', 'y', 'z', 'w'), q)))
        msg.orientation_covariance = [0.1, 0, 0, 0, 0.1, 0, 0, 0, 0.2]
        return msg

    def test_bno_fusion_is_preserved_without_software_filter_or_duplicate_processing(self):
        node, _ = load_node('imu_node.py')
        node.imu_pub, node.filter = Mock(), Mock()
        sample = self.fused_sample()
        node.publish_attitude(sample)
        node.publish_attitude(sample)
        node.filter.update.assert_not_called()
        node.imu_pub.publish.assert_called_once()
        output = node.imu_pub.publish.call_args.args[0]
        self.assertEqual(output.header, sample.header)
        self.assertEqual(output.orientation_covariance, sample.orientation_covariance)
        self.assertQuaternionEqual(output, (10, 20, 30))

    def test_lever_arm_corrects_acceleration_once_before_both_output_branches(self):
        node, _ = load_node('imu_node.py')
        node.imu_pub = Mock()
        node.lever_arm = LeverArmCompensator((1, 0, 0), 0.2)
        first = self.fused_sample(nanos=0)
        first.linear_acceleration.x = -1.0  # Centripetal at omega_z=1, r_x=1.
        node.publish_attitude(first)
        node.imu_pub.publish.assert_not_called()
        second = self.fused_sample(nanos=100_000_000)
        second.angular_velocity.z = 1.2
        second.linear_acceleration.x = -1.44
        second.linear_acceleration.y = 2.0  # alpha_z=2 rad/s^2.
        second.linear_acceleration_covariance = [1.0] * 9
        node.publish_attitude(second)
        output = node.imu_pub.publish.call_args.args[0]
        self.assertAlmostEqual(output.linear_acceleration.x, 0)
        self.assertAlmostEqual(output.linear_acceleration.y, 0)
        self.assertAlmostEqual(output.linear_acceleration.z, 9.80665)
        self.assertEqual(output.linear_acceleration_covariance, [0.0] * 9)
        self.assertQuaternionEqual(output, (10, 20, 30))
        self.assertEqual(output.header.stamp, second.header.stamp)
        self.assertEqual(second.linear_acceleration.x, -1.44)  # Input untouched.
        node.publish_attitude(second)
        node.imu_pub.publish.assert_called_once()
        aero = copy.deepcopy(output)
        aero.header.frame_id = node.frame_aero
        aero.linear_acceleration.z *= -1
        node.publish_aero(aero)
        self.assertEqual(node.aero_imu_pub.publish.call_args.args[0].linear_acceleration,
                         aero.linear_acceleration)

    def test_lever_arm_reseeds_after_clock_reset_and_long_gap(self):
        node, _ = load_node('imu_node.py')
        node.imu_pub = Mock()
        node.lever_arm = LeverArmCompensator((1, 0, 0), 0.2)
        node.publish_attitude(self.fused_sample())
        node.publish_attitude(self.fused_sample(nanos=100_000_000))
        node.imu_pub.publish.assert_called_once()
        node.get_clock().now().nanoseconds = 1_400_000_000
        node.publish_attitude(self.fused_sample(nanos=400_000_000))
        self.assertIsNone(node._robotic_sample)
        node.get_clock().now().nanoseconds = 1_000_000_000
        node.publish_attitude(self.fused_sample())
        node.imu_pub.publish.assert_called_once()
        node.get_clock().now().nanoseconds = 1_100_000_000
        node.publish_attitude(self.fused_sample(nanos=100_000_000))
        self.assertEqual(node.imu_pub.publish.call_count, 2)

    def test_periodic_output_keeps_only_latest_result_and_original_stamp(self):
        node, _ = load_node('imu_node.py')
        node.imu_pub = Mock()
        node.publish_rate_hz = 20.0
        node.publish_attitude(self.fused_sample(yaw=10))
        latest = self.fused_sample(yaw=20, nanos=50_000_000)
        node.publish_attitude(latest)
        node.imu_pub.publish.assert_not_called()
        for _ in range(2):
            node.publish_latest()
        self.assertEqual(node.imu_pub.publish.call_count, 2)
        self.assertQuaternionEqual(node.imu_pub.publish.call_args.args[0], (10, 20, 20))
        self.assertEqual(node.imu_pub.publish.call_args.args[0].header.stamp, latest.header.stamp)

    def test_expiry_future_input_and_paused_clock_are_checked(self):
        node, scope = load_node('imu_node.py')
        node.imu_pub = Mock()
        node.get_clock().now().nanoseconds = 2_000_000_000
        node.publish_attitude(self.fused_sample())  # One second old.
        future = self.fused_sample()
        future.header.stamp.sec = 3
        node.publish_attitude(future)
        node.imu_pub.publish.assert_not_called()
        fresh = self.fused_sample()
        fresh.header.stamp.sec = 2
        node.publish_attitude(fresh)
        node.imu_pub.publish.assert_called_once()
        scope['time'].monotonic = lambda: 100.6
        node.publish_latest()
        node.imu_pub.publish.assert_called_once()

    def test_enu_north_converts_to_ned_north_without_zeroing_absolute_heading(self):
        node, _ = load_node('imu_node.py')
        node.world_quaternion = quaternion_from_degrees(180, 0, 90)
        node.world_rotation = rotation_matrix(node.world_quaternion)
        node.publish_aero(self.transformed_aero_sample(yaw_deg=90))
        self.assertQuaternionEqual(node.aero_imu_pub.publish.call_args.args[0], (0, 0, 0))
        node.publish_aero(self.transformed_aero_sample(yaw_deg=0, tick=1))
        self.assertQuaternionEqual(node.aero_imu_pub.publish.call_args.args[0], (0, 0, 90))

    def test_out_of_order_fused_samples_do_not_replace_newer_result(self):
        node, _ = load_node('imu_node.py')
        node.imu_pub = Mock()
        node.publish_attitude(self.fused_sample(nanos=50_000_000))
        node.publish_attitude(self.fused_sample())
        node.imu_pub.publish.assert_called_once()
        node.get_clock().now().nanoseconds = 1_000_000_000
        node.publish_attitude(self.fused_sample())  # New ROS clock epoch.
        self.assertEqual(node.imu_pub.publish.call_count, 2)

    def test_imu_does_not_publish_during_calibration_or_missing_vectors(self):
        node, _ = load_node('imu_node.py')
        node.filter = ImuFilter(2, 9.80665, 0.98, 0.2)
        node.imu_pub = Mock()
        sample = Message()
        sample.linear_acceleration_covariance[0] = -1.0
        node.publish_attitude(sample)
        self.assertEqual(node.filter.count, 0)
        sample.linear_acceleration_covariance[0] = 0.0
        node.publish_attitude(sample)
        node.imu_pub.publish.assert_not_called()

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

    def test_aero_quaternions_represent_turns_and_reset_with_backwards_time(self):
        node, _ = load_node('imu_node.py')
        for tick, yaw in enumerate((0, 90, 180, 270, 360, 400)):
            sample = self.transformed_aero_sample(yaw_deg=yaw, tick=tick)
            node.publish_aero(sample)
            self.assertQuaternionEqual(node.aero_imu_pub.publish.call_args.args[0], (0, 0, -yaw))
        node.publish_aero(sample)  # Duplicate timestamp does not publish twice.
        self.assertEqual(node.aero_imu_pub.publish.call_count, 6)
        node.get_clock().now().nanoseconds = 1_000_000_000  # Actual ROS clock reset.
        node.publish_aero(self.transformed_aero_sample())
        self.assertQuaternionEqual(node.aero_imu_pub.publish.call_args.args[0], (0, 0, 0))

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
        node.imu_pub = Mock()
        node.filter = Mock()
        node.filter.roll = node.filter.pitch = node.filter.yaw = 0.0
        node.filter.update.return_value = ((0, 0, 9.80665), (0, 0, 0), (0, 0, 0, 1))
        node.publish_attitude(Message())
        node.imu_pub.publish.assert_called_once()
        node.aero_imu_pub.publish.assert_not_called()
        node.publish_aero(self.transformed_aero_sample())
        node.imu_pub.publish.assert_called_once()
        node.aero_imu_pub.publish.assert_called_once()
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



if __name__ == '__main__':
    unittest.main()
