# ros2_ws/src/rosbag_manager/rosbag_manager/rosbag_manager_node.py
import os
import signal
import subprocess
from datetime import datetime

import rclpy
from rclpy.node import Node

from sail_msgs.msg import RecordingState
from sail_msgs.srv import StartRecording, StopRecording

# Endpoints are generated from config/endpoints.yaml.
from rosbag_manager.generated.ros_endpoints import Topics, Services

class RosbagManagerNode(Node):
    def __init__(self):
        super().__init__('rosbag_manager_node')

        # ROS parameters; default to the workspace bag directory under the user's home.
        default_record_dir = os.path.join(os.path.expanduser('~'), 'ros2_ws', 'rosbags', 'raw_recordings')

        self.declare_parameter('record_dir', default_record_dir)
        self.declare_parameter('bag_prefix', 'rosbag2_')
        self.declare_parameter('sigint_timeout', 5.0)

        # Read parameters.
        self.record_dir = self.get_parameter('record_dir').value
        self.bag_prefix = self.get_parameter('bag_prefix').value
        self.sigint_timeout = self.get_parameter('sigint_timeout').value

        # Create the recording directory if needed.
        try:
            os.makedirs(self.record_dir, exist_ok=True)
            self.get_logger().info(f'Save directory verified: {self.record_dir}')
        except Exception as e:
            self.get_logger().error(f'Failed to create directory {self.record_dir}: {e}')

        # Internal recording state.
        self.recording = False
        self.current_bag_name = ''
        self.last_error = ''
        self.rosbag_proc: subprocess.Popen | None = None

        # Recording state publisher.
        self.state_pub = self.create_publisher(
            RecordingState,
            Topics.ROSBAG_MANAGER_NODE.PUB.RECORDING_STATE,
            10
        )

        # Services
        self.start_srv = self.create_service(
            StartRecording,
            Services.ROSBAG_MANAGER_NODE.SRV.START_RECORDING,
            self.handle_start_recording
        )

        self.stop_srv = self.create_service(
            StopRecording,
            Services.ROSBAG_MANAGER_NODE.SRV.STOP_RECORDING,
            self.handle_stop_recording
        )

        # Timer publishing
        self.state_timer = self.create_timer(0.5, self.publish_state)

        self.get_logger().info(f'RosbagManager Initialized. Ready to record to {self.record_dir}')

    # -----------------------
    #   Recording state publisher
    # -----------------------
    def publish_state(self):
        # Report recorder exits even when no further service request arrives.
        if self.recording and self.rosbag_proc is not None:
            return_code = self.rosbag_proc.poll()
            if return_code is not None:
                self.recording = False
                self.last_error = f'Recorder exited unexpectedly with code {return_code}'
                self.get_logger().error(self.last_error)
                self.rosbag_proc = None

        msg = RecordingState()
        msg.recording = self.recording
        msg.bag_name = self.current_bag_name
        msg.last_error = self.last_error
        self.state_pub.publish(msg)

    # -----------------------
    #   Service: Start
    # -----------------------
    def handle_start_recording(self, request, response):
        response.effective_bag_name = ''
        if self.recording:
            if self.rosbag_proc is not None and self.rosbag_proc.poll() is not None:
                self.recording = False
                self.rosbag_proc = None
            else:
                response.success = False
                response.error_message = 'Already recording'
                return response

        try:
            now_str = datetime.now().strftime('%Y_%m_%d-%H_%M_%S_%f')
            self.current_bag_name = f'{self.bag_prefix}{now_str}'
            full_path = os.path.join(self.record_dir, self.current_bag_name)

            # Record every discovered topic using MCAP storage.
            cmd = ['ros2', 'bag', 'record', '-a', '-s', 'mcap', '-o', full_path]

            self.get_logger().info(f'Starting recording: {self.current_bag_name}')
            
            self.rosbag_proc = subprocess.Popen(cmd, start_new_session=True)

            self.recording = True
            self.last_error = ''

            response.success = True
            response.error_message = ''
            response.effective_bag_name = self.current_bag_name

        except Exception as e:
            self.last_error = str(e)
            self.get_logger().error(f'Error starting recording: {self.last_error}')
            self.recording = False
            self.rosbag_proc = None
            response.success = False
            response.error_message = self.last_error

        self.publish_state()
        if response.success and not self.recording:
            response.success = False
            response.error_message = self.last_error
            response.effective_bag_name = ''
        return response

    # -----------------------
    #   Service: Stop
    # -----------------------
    def handle_stop_recording(self, request, response):
        response.last_bag_name = ''
        if not self.recording:
            response.success = False
            response.error_message = 'Not currently recording'
            return response

        try:
            if self.rosbag_proc is not None:
                self.get_logger().info('Stopping recording (Sending SIGINT)...')
                self.rosbag_proc.send_signal(signal.SIGINT)
                
                try:
                    self.rosbag_proc.wait(timeout=self.sigint_timeout)
                except subprocess.TimeoutExpired:
                    self.get_logger().warn('Rosbag process hung, forcing KILL...')
                    self.rosbag_proc.kill()
                    self.rosbag_proc.wait()
                
                self.rosbag_proc = None
            
            self.recording = False
            self.last_error = ''
            response.success = True
            response.error_message = ''
            response.last_bag_name = self.current_bag_name
            
            self.get_logger().info(f'Recording saved: {self.current_bag_name}')
            self.current_bag_name = '' 

        except Exception as e:
            self.last_error = str(e)
            self.get_logger().error(f'Error stopping recording: {self.last_error}')
            response.success = False
            response.error_message = self.last_error

        self.publish_state()
        return response

    def destroy_node(self):
        if self.rosbag_proc is not None:
            self.get_logger().info('Node shutdown: stopping rosbag process...')
            self.rosbag_proc.send_signal(signal.SIGINT)
            try:
                self.rosbag_proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self.get_logger().warn('Rosbag process hung during shutdown, forcing KILL...')
                self.rosbag_proc.kill()
                self.rosbag_proc.wait()
        super().destroy_node()

def main():
    rclpy.init()
    node = RosbagManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
