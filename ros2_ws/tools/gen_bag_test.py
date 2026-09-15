#!/usr/bin/env python3
import os
import time
import math
import struct
import shutil
import random
from rclpy.serialization import serialize_message
import rosbag2_py

# Messaggi standard
from builtin_interfaces.msg import Time
from std_msgs.msg import UInt8MultiArray
from sail_msgs.msg import SerialMsg
from sensor_msgs.msg import NavSatFix
from geometry_msgs.msg import TwistWithCovarianceStamped

# ==========================================
# CONFIGURAZIONE
# ==========================================
BAG_DIR = '/home/ros/ros2_ws/tools/test_bag'
TOPIC_SERIAL = '/serial/raw_rx' 
TOPIC_GPS_DATA = '/gps_data'
TOPIC_GPS_VEL = '/gps_vel_data'

# Durata totale: 90 + 60 + 40 + 120 = 310 secondi
SIM_DURATION_SEC = 310        
FREQ_HZ = 10                  
DT = 1.0 / FREQ_HZ

# ID CAN
ID_POT = 26
ID_IMU_RPY = 145
ID_IMU_VEL = 57
ID_IMU_ACC = 41
ID_WINDEX = 47
ID_ULTRASOUND = 107
ID_KEYPAD = 94

def get_time_msg(t_sec):
    msg = Time()
    msg.sec = int(t_sec)
    msg.nanosec = int((t_sec - int(t_sec)) * 1e9)
    return msg

# ==========================================
# FUNZIONI DI PACKING
# ==========================================
def pack_pot(angle_deg):
    val = int(max(0.0, min(90.0, angle_deg)))
    return struct.pack('<bbh', 0, 0, val)

def pack_imu_rpy(yaw_deg, pitch_deg, roll_deg):
    y, p, r = int(yaw_deg * 100), int(pitch_deg * 100), int(roll_deg * 100)
    return struct.pack('<bhhh', 0, y, p, r)

def pack_imu_vel(gx, gy, gz):
    x, y, z = int(gx * 100), int(gy * 100), int(gz * 100)
    return struct.pack('<bhhh', 0, x, y, z)

def pack_imu_acc(ax, ay, az):
    x, y, z = int(ax * 100), int(ay * 100), int(az * 100)
    return struct.pack('<bhhh', 0, x, y, z)

def pack_windex(aws, awa):
    s, a = int(aws * 10), int(awa * 10)
    return struct.pack('<bhhbb', 0, s, a, 0, 0)

def pack_ultrasound(dist_m):
    d_mm = int(max(0, dist_m) * 1000)
    return struct.pack('<BH', 0, d_mm)

def pack_keypad(trim_up, trim_down, set_up, set_down, estop):
    return struct.pack('<BBBBB', trim_up, trim_down, set_up, set_down, estop)

# ==========================================
# MAIN GENERATOR
# ==========================================
def main():
    print(f"🧹 Pulizia vecchia bag se esiste in {BAG_DIR}...")
    if os.path.exists(BAG_DIR):
        shutil.rmtree(BAG_DIR)

    print(f"📦 Creazione nuova bag (Formato MCAP)...")
    writer = rosbag2_py.SequentialWriter()
    
    storage_options = rosbag2_py.StorageOptions(uri=BAG_DIR, storage_id='mcap')
    converter_options = rosbag2_py.ConverterOptions(
        input_serialization_format='cdr',
        output_serialization_format='cdr'
    )
    
    writer.open(storage_options, converter_options)
    
    writer.create_topic(rosbag2_py.TopicMetadata(
        id=0, name=TOPIC_SERIAL, type='sail_msgs/msg/SerialMsg', serialization_format='cdr'))
    writer.create_topic(rosbag2_py.TopicMetadata(
        id=0, name=TOPIC_GPS_DATA, type='sensor_msgs/msg/NavSatFix', serialization_format='cdr'))
    writer.create_topic(rosbag2_py.TopicMetadata(
        id=0, name=TOPIC_GPS_VEL, type='geometry_msgs/msg/TwistWithCovarianceStamped', serialization_format='cdr'))

    print(f"🌊 Generazione dati di simulazione (Durata: {SIM_DURATION_SEC}s a {FREQ_HZ}Hz)...")
    
    base_time = time.time()
    t_sim = 0.0
    
    # Posizione di partenza (Malcesine sul Garda)
    sim_lat = 45.7605
    sim_lon = 10.8091
    
    # Direzione iniziale: 45 gradi (Nord-Est)
    base_yaw = 45.0
    
    while t_sim < SIM_DURATION_SEC:
        
        # --- LOGICA DI NAVIGAZIONE A "RETTANGOLO" ---
        if t_sim < 90:
            target_yaw = 45.0         # Primo lato: Dritti per 90s (Nord-Est)
        elif t_sim < 150:
            target_yaw = 135.0        # Secondo lato: Giriamo di 90° e dritti per 60s (Sud-Est)
        elif t_sim < 190:
            target_yaw = 225.0        # Terzo lato: Giriamo di 90° e dritti per 40s (Sud-Ovest)
        else:
            target_yaw = 315.0        # Quarto lato: Giriamo di 90° e dritti per 120s (Nord-Ovest verso la linea)

        # Accostata progressiva (gira di max 15 gradi al secondo) per non confondere l'EKF
        diff = (target_yaw - base_yaw + 180) % 360 - 180
        turn_rate = 15.0 
        if abs(diff) > turn_rate * DT:
            base_yaw += math.copysign(turn_rate * DT, diff)
        else:
            base_yaw = target_yaw

        # Aggiungiamo rumore per simulare le onde che spostano la prua
        sim_yaw = base_yaw + random.uniform(-1.5, 1.5)
        # --------------------------------------------

        sim_roll = 15.0 * math.sin(t_sim * 0.6) + 3.0 * math.cos(t_sim * 1.8) + random.uniform(-0.5, 0.5)
        sim_pitch = 4.0 * math.cos(t_sim * 0.4) + 1.5 * math.sin(t_sim * 2.1) + random.uniform(-0.2, 0.2)
        
        sim_height = 0.5 + 0.15 * math.sin(t_sim * 0.3) + 0.05 * math.cos(t_sim * 1.2) + random.uniform(-0.02, 0.02)
        sim_wand = 45.0 + 20.0 * math.sin(t_sim * 0.2) + 5.0 * math.sin(t_sim * 1.5) + random.uniform(-1.0, 1.0)
        
        sim_aws = 14.0 + 3.0 * math.sin(t_sim * 0.1) + random.uniform(-0.5, 0.5)
        sim_awa = 30.0 + 8.0 * math.cos(t_sim * 0.15) + random.uniform(-1.5, 1.5)
        
        sim_gx, sim_gy, sim_gz = random.uniform(-2, 2), random.uniform(-2, 2), random.uniform(-2, 2)
        sim_ax, sim_ay, sim_az = random.uniform(-0.5, 0.5), random.uniform(-0.5, 0.5), 9.81 + random.uniform(-0.5, 0.5)

        # --- SIMULAZIONE CINEMATICA GPS CON VELOCITÀ VARIABILE ---
        # La velocità pulsa tra onde veloci e lente, variando circa da 3.5 a 6.5 m/s
        base_speed = 5.0 + 1.2 * math.sin(t_sim * 0.08) + 0.6 * math.cos(t_sim * 0.2) + random.uniform(-0.3, 0.3)
        
        yaw_rad = math.radians(sim_yaw)
        sim_vel_x = base_speed * math.sin(yaw_rad)
        sim_vel_y = base_speed * math.cos(yaw_rad)
        
        lat_m_per_deg = 111320.0
        lon_m_per_deg = 111320.0 * math.cos(math.radians(sim_lat))
        
        sim_lat += (sim_vel_y * DT) / lat_m_per_deg
        sim_lon += (sim_vel_x * DT) / lon_m_per_deg

        # --- PREPARAZIONE MESSAGGI ---
        t_real = base_time + t_sim
        t_nanosec = int(t_real * 1e9)
        msg_time = get_time_msg(t_real)

        messages = [
            (ID_POT, pack_pot(sim_wand)),
            (ID_IMU_RPY, pack_imu_rpy(sim_yaw, sim_pitch, sim_roll)),
            (ID_IMU_VEL, pack_imu_vel(sim_gx, sim_gy, sim_gz)),
            (ID_IMU_ACC, pack_imu_acc(sim_ax, sim_ay, sim_az)),
            (ID_WINDEX, pack_windex(sim_aws, sim_awa)),
            (ID_ULTRASOUND, pack_ultrasound(sim_height)),
        ]

        if random.random() < (1.0 / (15.0 * FREQ_HZ)):
            if random.choice([True, False]):
                messages.append((ID_KEYPAD, pack_keypad(0, 0, 1, 0, 0))) 
            else:
                messages.append((ID_KEYPAD, pack_keypad(0, 0, 0, 1, 0)))

        for can_id, payload_bytes in messages:
            msg = SerialMsg()
            msg.stamp = msg_time
            msg.id = can_id
            payload_msg = UInt8MultiArray()
            payload_msg.data = list(payload_bytes)
            msg.payload = payload_msg
            writer.write(TOPIC_SERIAL, serialize_message(msg), t_nanosec)

        gps_msg = NavSatFix()
        gps_msg.header.stamp = msg_time
        gps_msg.header.frame_id = 'gps_link'
        gps_msg.status.status = 0
        gps_msg.status.service = 1
        gps_msg.position_covariance = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        gps_msg.position_covariance_type = 2
        gps_msg.latitude = sim_lat
        gps_msg.longitude = sim_lon
        gps_msg.altitude = 0.0
        writer.write(TOPIC_GPS_DATA, serialize_message(gps_msg), t_nanosec)

        vel_msg = TwistWithCovarianceStamped()
        vel_msg.header.stamp = msg_time
        vel_msg.header.frame_id = 'gps_link'
        vel_msg.twist.twist.linear.x = sim_vel_x
        vel_msg.twist.twist.linear.y = sim_vel_y
        vel_msg.twist.twist.linear.z = 0.0
        vel_msg.twist.covariance = [0.0] * 36
        vel_msg.twist.covariance[0] = 0.1
        vel_msg.twist.covariance[7] = 0.1
        vel_msg.twist.covariance[14] = 0.1
        writer.write(TOPIC_GPS_VEL, serialize_message(vel_msg), t_nanosec)

        t_sim += DT

    del writer
    print(f"✅ Bag MCAP generata con successo in: {BAG_DIR}")

if __name__ == '__main__':
    main()