# AUTO-GENERATED FILE. DO NOT EDIT.

class Topics:
    class Shared:
        IMU_MOUNTED = '/internal/imu/mounted'
        IMU_AERO_BODY = '/internal/imu/aero_body'
        TRANSFORMER_MAG_IN = '~/mag_in'
        TRANSFORMER_MAG_OUT = '~/mag_out'
        BOAT_HEIGHT = '/processed/boat_height'
        IMU_DATA = '/processed/imu/data'
        IMU_RPY = '/processed/imu/rpy'
        IMU_DATA_AERO = '/processed/imu/data/aero'
        IMU_RPY_AERO = '/processed/imu/rpy/aero'
        HEADING_DEG = '/processed/heading_deg'
        GPS_SUMMARY = '/processed/gps/summary'
        BATTERY_LOW = '/processed/battery/low'

    class ULTRASONIC_FILTER_NODE:
        class PUB:
            HEIGHT = '/processed/boat_height'

    class IMU_NODE:
        class SUB:
            IMU = '/internal/imu/mounted'
            IMU_AERO = '/internal/imu/aero_body'

        class PUB:
            IMU = '/processed/imu/data'
            RPY = '/processed/imu/rpy'
            IMU_AERO = '/processed/imu/data/aero'
            RPY_AERO = '/processed/imu/rpy/aero'

    class IMU_MOUNT_TRANSFORMER_NODE:
        class PUB:
            IMU_OUT = '/internal/imu/mounted'

    class IMU_AERO_TRANSFORMER_NODE:
        class SUB:
            IMU_IN = '/processed/imu/data'

        class PUB:
            IMU_OUT = '/internal/imu/aero_body'

    class HEADING_NODE:
        class PUB:
            HEADING_DEG = '/processed/heading_deg'
            GPS_SUMMARY = '/processed/gps/summary'

    class BATTERY_MONITOR_NODE:
        class PUB:
            BATTERY_LOW = '/processed/battery/low'
