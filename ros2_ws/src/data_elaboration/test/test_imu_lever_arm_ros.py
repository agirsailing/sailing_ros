"""Exercise real DDS and imu_transformer with a rotated, displaced synthetic IMU."""

import math
from pathlib import Path
import subprocess
import sys
import time
import unittest

SRC = Path(__file__).resolve().parents[2]
for package in ('data_elaboration', 'sensors', 'sail_common'):
    sys.path.insert(0, str(SRC/package))

try:
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from sensor_msgs.msg import Imu
    from tf2_ros import Buffer, TransformListener
    from data_elaboration.imu_node import ImuNode
except ImportError:
    rclpy = None

TRANSFORMER = Path('/opt/ros/jazzy/lib/imu_transformer/imu_transformer_node')


@unittest.skipUnless(rclpy is not None and TRANSFORMER.exists(), 'Requires ROS Jazzy/imu_transformer')
class LeverArmRosTests(unittest.TestCase):
    def test_real_mount_rotation_then_com_compensation(self):
        rclpy.init(args=['--ros-args', '--params-file',
                        str(SRC/'data_elaboration/config/params.yaml'),
                        '-p', 'tf_offset:=[1.0,0.0,0.0,0.0,0.0,90.0]',
                        '-p', 'publish_rate_hz:=0.0'])
        node = observer = executor = process = None
        try:
            node = ImuNode()
            observer = rclpy.create_node('lever_arm_test', use_global_arguments=False)
            received = []
            observer.create_subscription(Imu, '/processed/imu/data', received.append, 10)
            publisher = observer.create_publisher(Imu, '/test/lever_arm/raw', 10)
            buffer = Buffer()
            listener = TransformListener(buffer, observer)
            executor = SingleThreadedExecutor()
            executor.add_node(node)
            executor.add_node(observer)
            process = subprocess.Popen([
                str(TRANSFORMER), '--ros-args', '-r', '__node:=lever_arm_mount_test',
                '-p', 'target_frame:=imu_link_flu',
                '-r', 'imu_in:=/test/lever_arm/raw', '-r', 'imu_out:=/internal/imu/mounted',
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + 10
            sent = set()
            while time.monotonic() < deadline and not received:
                msg = Imu()
                msg.header.stamp = observer.get_clock().now().to_msg()
                msg.header.frame_id = 'imu'
                msg.orientation.z = math.sqrt(0.5)
                msg.orientation.w = math.sqrt(0.5)
                msg.angular_velocity.z = 1.0
                # Sensor yaw=90 degrees: body centripetal (-1,0,0) is sensor (0,1,0).
                msg.linear_acceleration.y = 1.0
                msg.linear_acceleration.z = 9.80665
                publisher.publish(msg)
                sent.add((msg.header.stamp.sec, msg.header.stamp.nanosec))
                until = time.monotonic() + 0.02
                while time.monotonic() < until:
                    executor.spin_once(timeout_sec=0.005)
            self.assertTrue(received, 'No compensated sample received through real imu_transformer')
            output = received[-1]
            self.assertEqual(output.header.frame_id, 'imu_link_flu')
            self.assertIn((output.header.stamp.sec, output.header.stamp.nanosec), sent)
            self.assertAlmostEqual(output.linear_acceleration.x, 0, places=6)
            self.assertAlmostEqual(output.linear_acceleration.y, 0, places=6)
            self.assertAlmostEqual(output.linear_acceleration.z, 9.80665, places=6)
            self.assertAlmostEqual(abs(output.orientation.w), 1, places=6)
            transform = buffer.lookup_transform('base_link', 'imu_link_flu', rclpy.time.Time())
            self.assertEqual(transform.transform.translation.x, 0)
            transform = buffer.lookup_transform('base_link', 'imu', rclpy.time.Time())
            self.assertEqual(transform.transform.translation.x, 1)
        finally:
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            if executor is not None:
                executor.shutdown()
            if observer is not None:
                observer.destroy_node()
            if node is not None:
                node.destroy_node()
            rclpy.shutdown()


if __name__ == '__main__':
    unittest.main()
