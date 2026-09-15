# AUTO-GENERATED FILE. DO NOT EDIT.

class Topics:
    class Shared:
        ULTRASONIC_FRONT = '/ultrasonic/front'
        ULTRASONIC_BACK = '/ultrasonic/back'
        GPS_DATA = '/gps/data'
        IMU_DATA = '/imu/data'
        COMPASS_DATA = '/compass/data'
        BATTERY_DATA = '/battery/data'

    class ULTRASONIC_FRONT_NODE:
        class PUB:
            RANGE = '/ultrasonic/front'

    class ULTRASONIC_BACK_NODE:
        class PUB:
            RANGE = '/ultrasonic/back'

    class GPS_NODE:
        class PUB:
            GPS_RAW = '/gps/data'

    class I2C_SENSORS_NODE:
        class PUB:
            IMU_RAW = '/imu/data'
            COMPASS_RAW = '/compass/data'

    class BATTERY_NODE:
        class PUB:
            BATTERY_LOW = '/battery/data'
