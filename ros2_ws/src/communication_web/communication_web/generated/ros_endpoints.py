# AUTO-GENERATED FILE. DO NOT EDIT.

class Topics:
    class Shared:
        ATTITUDE = '/processed/imu/data/aero'
        HEIGHT = '/processed/boat_height'
        BATTERY = '/battery/data'
        GPS = '/gps/data'
        ULTRASONIC_LEFT = '/ultrasonic/left'
        ULTRASONIC_RIGHT = '/ultrasonic/right'
        RECORDING_STATE = '/local_state/recording_state'
        TELEMETRY = '/web/ros/dashboard'
        POSITION = '/web/ros/map'
        MQTT_TELEMETRY = 'agir_gui/data/dashboard'
        MQTT_POSITION = 'agir_gui/data/map'
        MQTT_RECORDING_STATE = 'agir_gui/data/recording_state'
        MQTT_START_RECORDING = 'agir_gui/cmd/start_recording'
        MQTT_STOP_RECORDING = 'agir_gui/cmd/stop_recording'
        MQTT_START_RESPONSE = 'agir_gui/rsp/start_recording'
        MQTT_STOP_RESPONSE = 'agir_gui/rsp/stop_recording'
        MQTT_PING_MARK = 'agir_gui/cmd/ping_mark'
        MQTT_PING_RESPONSE = 'agir_gui/rsp/ping_mark'

    class TELEMETRY_GATEWAY_NODE:
        class SUB:
            ATTITUDE = '/processed/imu/data/aero'
            HEIGHT = '/processed/boat_height'
            BATTERY = '/battery/data'
            GPS = '/gps/data'
            ULTRASONIC_LEFT = '/ultrasonic/left'
            ULTRASONIC_RIGHT = '/ultrasonic/right'
            RECORDING_STATE = '/local_state/recording_state'

        class PUB:
            TELEMETRY = '/web/ros/dashboard'
            POSITION = '/web/ros/map'

        class MQTT:
            class SUB:
                pass

            class PUB:
                TELEMETRY = 'agir_gui/data/dashboard'
                POSITION = 'agir_gui/data/map'
                RECORDING_STATE = 'agir_gui/data/recording_state'

            class RSP:
                pass

    class COMMAND_GATEWAY_NODE:
        class MQTT:
            class SUB:
                PING_MARK = 'agir_gui/cmd/ping_mark'
                START_RECORDING = 'agir_gui/cmd/start_recording'
                STOP_RECORDING = 'agir_gui/cmd/stop_recording'

            class PUB:
                pass

            class RSP:
                PING_MARK = 'agir_gui/rsp/ping_mark'
                START_RECORDING = 'agir_gui/rsp/start_recording'
                STOP_RECORDING = 'agir_gui/rsp/stop_recording'


class Services:
    class Shared:
        PING_MARK = '/local_cmd/ping_mark'
        START_RECORDING = '/local_cmd/start_recording'
        STOP_RECORDING = '/local_cmd/stop_recording'

    class TELEMETRY_GATEWAY_NODE:
        class SRV:
            PING_MARK = '/local_cmd/ping_mark'

    class COMMAND_GATEWAY_NODE:
        class SRV:
            PING_MARK = '/local_cmd/ping_mark'
            START_RECORDING = '/local_cmd/start_recording'
            STOP_RECORDING = '/local_cmd/stop_recording'
