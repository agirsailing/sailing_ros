# AUTO-GENERATED FILE. DO NOT EDIT.

class Topics:
    class Shared:
        ATTITUDE = '/processed/imu/rpy/aero'
        HEIGHT = '/processed/boat_height'
        BATTERY = '/processed/battery/low'
        GPS = '/processed/gps/summary'
        RECORDING_STATE = '/local_state/recording_state'
        TELEMETRY = '/web/telemetry'
        POSITION = '/web/position'
        MQTT_TELEMETRY = 'agir_gui/data/telemetry'
        MQTT_POSITION = 'agir_gui/data/position'
        MQTT_RECORDING_STATE = 'agir_gui/data/recording_state'
        MQTT_START_RECORDING = 'agir_gui/cmd/start_recording'
        MQTT_STOP_RECORDING = 'agir_gui/cmd/stop_recording'
        MQTT_START_RESPONSE = 'agir_gui/rsp/start_recording'
        MQTT_STOP_RESPONSE = 'agir_gui/rsp/stop_recording'

    class TELEMETRY_GATEWAY_NODE:
        class SUB:
            ATTITUDE = '/processed/imu/rpy/aero'
            HEIGHT = '/processed/boat_height'
            BATTERY = '/processed/battery/low'
            GPS = '/processed/gps/summary'
            RECORDING_STATE = '/local_state/recording_state'

        class PUB:
            TELEMETRY = '/web/telemetry'
            POSITION = '/web/position'

        class MQTT:
            class SUB:
                pass

            class PUB:
                TELEMETRY = 'agir_gui/data/telemetry'
                POSITION = 'agir_gui/data/position'
                RECORDING_STATE = 'agir_gui/data/recording_state'

            class RSP:
                pass

    class COMMAND_GATEWAY_NODE:
        class MQTT:
            class SUB:
                START_RECORDING = 'agir_gui/cmd/start_recording'
                STOP_RECORDING = 'agir_gui/cmd/stop_recording'

            class PUB:
                pass

            class RSP:
                START_RECORDING = 'agir_gui/rsp/start_recording'
                STOP_RECORDING = 'agir_gui/rsp/stop_recording'


class Services:
    class Shared:
        START_RECORDING = '/local_cmd/start_recording'
        STOP_RECORDING = '/local_cmd/stop_recording'

    class TELEMETRY_GATEWAY_NODE:
        pass

    class COMMAND_GATEWAY_NODE:
        class SRV:
            START_RECORDING = '/local_cmd/start_recording'
            STOP_RECORDING = '/local_cmd/stop_recording'
