# /ros2_ws/src/sensors/sensors/ultrasonic_node.py
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from sensor_msgs.msg import Range

from sensors.drivers.ultrasonic_driver import DFRobot_A02_Distance
from sensors.generated.ros_endpoints import Topics


class UltrasonicNode(Node):
    def __init__(self):
        super().__init__('ultrasonic_node')

        # 1. Declare and read ROS parameters (values come from params.yaml).
        self.enabled = self.declare_parameter('enabled', Parameter.Type.BOOL).value
        self.endpoint_group = self.declare_parameter('endpoint_group', Parameter.Type.STRING).value
        self.port = self.declare_parameter('port', Parameter.Type.STRING).value
        self.baudrate = self.declare_parameter('baudrate', Parameter.Type.INTEGER).value
        self.timeout_s = self.declare_parameter('timeout_s', Parameter.Type.DOUBLE).value
        self.rate_hz = self.declare_parameter('rate_hz', Parameter.Type.DOUBLE).value
        self.frame_id = self.declare_parameter('frame_id', Parameter.Type.STRING).value
        self.min_range_m = self.declare_parameter('min_range_m', Parameter.Type.DOUBLE).value
        self.max_range_m = self.declare_parameter('max_range_m', Parameter.Type.DOUBLE).value
        self.field_of_view_rad = self.declare_parameter('field_of_view_rad', Parameter.Type.DOUBLE).value
        self.qos_depth = self.declare_parameter('qos_depth', Parameter.Type.INTEGER).value

        # 2. Validate configuration and select the generated topic constant.
        self._validate_parameters()

        if self.endpoint_group == 'ULTRASONIC_FRONT_NODE':
            self.range_topic = Topics.ULTRASONIC_FRONT_NODE.PUB.RANGE
        else:
            self.range_topic = Topics.ULTRASONIC_BACK_NODE.PUB.RANGE

        # A disabled sensor does not open a serial port or publish messages.
        self.sensor = None
        if not self.enabled:
            self.get_logger().info(
                f'Ultrasonic sensor disabled: {self.frame_id}'
            )
            return

        # 3. Distance publisher.
        self.range_pub = self.create_publisher(
            Range,
            self.range_topic,
            self.qos_depth
        )

        # 4. Open the sensor driver and set software measurement limits.
        self.sensor = DFRobot_A02_Distance(
            self.port,
            self.baudrate,
            self.timeout_s
        )
        self.sensor.set_dis_range(
            self.min_range_m * 1000,
            self.max_range_m * 1000
        )

        # 5. Timer for reading and publishing the distance.
        self.distance_timer = self.create_timer(
            1.0 / self.rate_hz,
            self.publish_distance
        )

        self.get_logger().info(
            f'Ultrasonic node initialized: {self.port} -> {self.range_topic}, '
            f'reading at {self.rate_hz} Hz'
        )

    # -----------------------
    #   Validate ROS parameters
    # -----------------------
    def _validate_parameters(self):
        # Typed declarations can return None if a YAML entry is missing.
        # Reading all declared parameters raises a clear ROS error in that case.
        self.get_parameters(self.list_parameters([], depth=0).names)

        if self.endpoint_group not in ('ULTRASONIC_FRONT_NODE', 'ULTRASONIC_BACK_NODE'):
            raise ValueError(f'Unknown endpoint_group: {self.endpoint_group}')
        if self.timeout_s <= 0:
            raise ValueError('timeout_s must be positive')
        if self.rate_hz <= 0:
            raise ValueError('rate_hz must be positive')
        if self.field_of_view_rad <= 0:
            raise ValueError('field_of_view_rad must be positive')
        if self.qos_depth <= 0:
            raise ValueError('qos_depth must be positive')
        if not 0 <= self.min_range_m < self.max_range_m:
            raise ValueError('Invalid ultrasonic measurement range')

    # -----------------------
    #   Read and publish distance
    # -----------------------
    def publish_distance(self):
        try:
            distance_mm = self.sensor.getDistance()
        except OSError as error:
            self.get_logger().warning(f'Ultrasonic read failed: {error}')
            return

        if self.sensor.last_operate_status != self.sensor.STA_OK:
            self.get_logger().warning(
                'Ultrasonic measurement rejected: '
                f'{self.sensor.last_operate_status}'
            )
            return

        msg = Range()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        msg.radiation_type = Range.ULTRASOUND
        msg.min_range = self.min_range_m
        msg.max_range = self.max_range_m
        msg.field_of_view = self.field_of_view_rad
        msg.range = distance_mm / 1000.0

        self.range_pub.publish(msg)

    # -----------------------
    #   Release the serial connection
    # -----------------------
    def destroy_node(self):
        if self.sensor is not None:
            self.sensor.close()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = UltrasonicNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
