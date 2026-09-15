# Legacy configuration retained for reference; rosbag_manager_node does not import it.
# Active parameters are declared by the node and configured in config/params.yaml.
import os

class RosbagConfig:
    # === RECORDING DIRECTORY ===
    # Resolve the current user's home dynamically.
    # Default: ~/ros2_ws/rosbags/raw_recordings
    DEFAULT_RECORD_DIR = os.path.join(os.path.expanduser('~'), 'ros2_ws', 'rosbags', 'raw_recordings')

    # === LEGACY POLIMI TOPIC LIST ===
    # Not used by the current node, which records all discovered ROS topics.
    DEFAULT_TOPICS = [
        '/serial/raw_rx',      # Raw serial input for Polimi replay.
        '/local_cmd/set_mark', # Mark placement events.
        '/gps_data',
        '/gps_vel_data'
    ]

    # === PROCESS SETTINGS ===
    # Rosbag directory name prefix.
    BAG_NAME_PREFIX = "rosbag2_"
    
    # Graceful stop timeout before terminating the recorder forcibly.
    SIGINT_TIMEOUT_SEC = 5.0
