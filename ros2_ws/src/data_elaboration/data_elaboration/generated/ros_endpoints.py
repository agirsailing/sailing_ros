# AUTO-GENERATED FILE. DO NOT EDIT.

class Topics:
    class Shared:
        IMU_MOUNTED = '/internal/imu/mounted'
        IMU_AERO_BODY = '/internal/imu/aero_body'
        TRANSFORMER_MAG_IN = '~/mag_in'
        TRANSFORMER_MAG_OUT = '~/mag_out'
        BOAT_HEIGHT = '/processed/boat_height'
        IMU_DATA = '/processed/imu/data'
        IMU_DATA_AERO = '/processed/imu/data/aero'

    class ULTRASONIC_FILTER_NODE:
        class PUB:
            HEIGHT = '/processed/boat_height'

    class IMU_NODE:
        class SUB:
            IMU = '/internal/imu/mounted'
            IMU_AERO = '/internal/imu/aero_body'

        class PUB:
            IMU = '/processed/imu/data'
            IMU_AERO = '/processed/imu/data/aero'

    class IMU_MOUNT_TRANSFORMER_NODE:
        class PUB:
            IMU_OUT = '/internal/imu/mounted'

    class IMU_AERO_TRANSFORMER_NODE:
        class SUB:
            IMU_IN = '/processed/imu/data'

        class PUB:
            IMU_OUT = '/internal/imu/aero_body'
