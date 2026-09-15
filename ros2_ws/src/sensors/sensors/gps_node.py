"""Publish the receiver solution without compass access or heading fusion."""

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from serial import Serial
from pyubx2 import UBXReader
from sail_msgs.msg import GpsData

from sensors.drivers.gps_driver import nav_pvt_values
from sensors.generated.ros_endpoints import Topics


class GPSNode(Node):
    def __init__(self):
        super().__init__('gps_node')

        # 1. Declare and read ROS parameters (values come from params.yaml).
        self.port = self.declare_parameter('port', Parameter.Type.STRING).value
        self.baudrate = self.declare_parameter('baudrate', Parameter.Type.INTEGER).value
        self.timeout_s = self.declare_parameter('timeout_s', Parameter.Type.DOUBLE).value
        self.rate_hz = self.declare_parameter('rate_hz', Parameter.Type.DOUBLE).value
        self.frame_id = self.declare_parameter('frame_id', Parameter.Type.STRING).value
        self.qos_depth = self.declare_parameter('qos_depth', Parameter.Type.INTEGER).value

        # 2. Validate configuration before opening the serial port.
        self._validate_parameters()

        # 3. GPS data publisher.
        self.gps_pub = self.create_publisher(
            GpsData,
            Topics.GPS_NODE.PUB.GPS_RAW,
            self.qos_depth
        )

        # 4. Open the receiver serial connection and UBX parser.
        self.stream = Serial(
            self.port,
            self.baudrate,
            timeout=self.timeout_s
        )
        try:
            self.reader = UBXReader(self.stream)

            # 5. Timer for reading and publishing receiver measurements.
            self.gps_timer = self.create_timer(
                1.0 / self.rate_hz,
                self.publish_gps
            )
        except Exception:
            self.stream.close()
            raise

        self.get_logger().info(
            f'GPS node initialized on {self.port}, reading at {self.rate_hz} Hz'
        )

    # -----------------------
    #   Validate ROS parameters
    # -----------------------
    def _validate_parameters(self):
        # Reject missing YAML values before accessing hardware.
        self.get_parameters(self.list_parameters([], depth=0).names)

        if self.timeout_s <= 0:
            raise ValueError('timeout_s must be positive')
        if self.rate_hz <= 0:
            raise ValueError('rate_hz must be positive')
        if self.qos_depth <= 0:
            raise ValueError('qos_depth must be positive')

    # -----------------------
    #   Read and publish GPS measurements
    # -----------------------
    def publish_gps(self):
        try:
            _, packet = self.reader.read()
            if packet is None or packet.identity != 'NAV-PVT':
                return
            values = nav_pvt_values(packet)
        except Exception as error:
            self.get_logger().warning(f'GPS read failed: {error}')
            return

        msg = GpsData()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id

        # The driver decodes the receiver fields and converts physical units.
        msg.latitude_deg = values['latitude_deg']
        msg.longitude_deg = values['longitude_deg']
        msg.altitude_msl_m = values['altitude_msl_m']
        msg.ground_speed_mps = values['ground_speed_mps']
        msg.course_deg = values['course_deg']
        msg.position_dop = values['position_dop']
        msg.horizontal_accuracy_m = values['horizontal_accuracy_m']
        msg.vertical_accuracy_m = values['vertical_accuracy_m']
        msg.satellites_used = values['satellites_used']
        msg.fix_type = values['fix_type']
        msg.fix_valid = values['fix_valid']

        self.gps_pub.publish(msg)

    # -----------------------
    #   Release the serial connection
    # -----------------------
    def destroy_node(self):
        self.stream.close()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = GPSNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
