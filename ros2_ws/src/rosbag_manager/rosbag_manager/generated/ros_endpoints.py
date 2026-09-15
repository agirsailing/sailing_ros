# AUTO-GENERATED FILE. DO NOT EDIT.

class Topics:
    class Shared:
        RECORDING_STATE = '/local_state/recording_state'

    class ROSBAG_MANAGER_NODE:
        class PUB:
            RECORDING_STATE = '/local_state/recording_state'


class Services:
    class Shared:
        START_RECORDING = '/local_cmd/start_recording'
        STOP_RECORDING = '/local_cmd/stop_recording'

    class ROSBAG_MANAGER_NODE:
        class SRV:
            START_RECORDING = '/local_cmd/start_recording'
            STOP_RECORDING = '/local_cmd/stop_recording'
