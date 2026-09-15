import os
import sys
import argparse
import pandas as pd
from pathlib import Path

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

# --- MAPPA DEI TOPIC ---
TARGET_TOPICS = [
    '/imu_data',
    '/wand_angle',
    '/gps_vel_data',
    '/gps_data',
    '/gps/filtered',
    '/current_height_raw',
    '/flap_angle_out',
    '/pid_indicators'
]

# --- FUNZIONI AUTOMATICHE (Dal codice del tuo ex-capo) ---
def _is_ros_message(obj):
    return hasattr(obj, '__slots__') and hasattr(obj, '__class__')

def _flatten(obj, prefix="", out=None, array_delim=";"):
    """Appiattisce automaticamente qualsiasi messaggio ROS sconosciuto."""
    if out is None:
        out = {}
    
    def emit(key, value):
        out[key if not prefix else f"{prefix}.{key}"] = value

    if _is_ros_message(obj):
        for slot in obj.__slots__:
            try:
                value = getattr(obj, slot)
            except Exception:
                value = None
            _flatten(value, f"{prefix}.{slot}" if prefix else slot, out, array_delim)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _flatten(v, f"{prefix}.{k}" if prefix else str(k), out, array_delim)
    elif isinstance(obj, (list, tuple)):
        try:
            emit("value", array_delim.join(map(str, obj)))
        except Exception:
            emit("value", str(obj))
    else:
        emit("value" if prefix == "" else prefix.split(".")[-1], obj)
    return out


# --- LOGICA DI ELABORAZIONE DELLA SINGOLA BAG ---
def process_single_bag(bag_path_obj):
    bag_path = str(bag_path_obj)
    nome_bag_originale = bag_path_obj.name

    # Rimuovi 'rosbag2_' dal nome per creare la cartella di output pulita
    nome_cartella_out = nome_bag_originale.replace('rosbag2_', '')
    
    # Il percorso di output sarà nella directory CORRENTE in cui lanci lo script
    out_dir = Path.cwd() / nome_cartella_out
    
    print(f"\n📂 Analizzando: {nome_bag_originale}")
    
    # Setup reader
    reader = rosbag2_py.SequentialReader()
    storage_options = rosbag2_py.StorageOptions(uri=bag_path)
    converter_options = rosbag2_py.ConverterOptions(
        input_serialization_format='cdr',
        output_serialization_format='cdr'
    )
    
    try:
        reader.open(storage_options, converter_options)
    except Exception as e:
        print(f" ❌ Errore nell'apertura della bag {nome_bag_originale}: {e}")
        return

    topic_types = reader.get_all_topics_and_types()
    type_map = {t.name: t.type for t in topic_types}
    dati_estratti = {}

    while reader.has_next():
        (topic, data_raw, t) = reader.read_next()
        
        if topic not in TARGET_TOPICS:
            continue

        if topic not in dati_estratti:
            dati_estratti[topic] = []

        msg_type = get_message(type_map[topic])
        msg = deserialize_message(data_raw, msg_type)

        row = {'timestamp_ns': t}

        # --- PARSING DEI MESSAGGI (Manuale + Automatico) ---
        if topic == '/imu_data':
            row.update({
                'acc_x': msg.linear_acceleration.x, 'acc_y': msg.linear_acceleration.y, 'acc_z': msg.linear_acceleration.z,
                'gyro_x': msg.angular_velocity.x, 'gyro_y': msg.angular_velocity.y, 'gyro_z': msg.angular_velocity.z,
                'quat_x': msg.orientation.x, 'quat_y': msg.orientation.y, 'quat_z': msg.orientation.z, 'quat_w': msg.orientation.w
            })
        elif topic in ['/wand_angle', '/flap_angle_out']:
            row.update({'data': msg.data})
        elif topic == '/gps_data':
            row.update({'latitude': msg.latitude, 'longitude': msg.longitude, 'altitude': msg.altitude})
        elif topic == '/gps_vel_data':
            row.update({
                'vel_x': msg.twist.twist.linear.x, 'vel_y': msg.twist.twist.linear.y, 'vel_z': msg.twist.twist.linear.z
            })
        elif topic == '/current_height_raw':
            row.update({
                'z_height': msg.pose.pose.position.z, 'x_pos': msg.pose.pose.position.x, 'y_pos': msg.pose.pose.position.y
            })
        elif topic == '/gps/filtered':
            if 'NavSatFix' in type_map[topic]:
                row.update({'latitude': msg.latitude, 'longitude': msg.longitude, 'altitude': msg.altitude})
            elif 'Odometry' in type_map[topic]:
                row.update({
                    'x': msg.pose.pose.position.x, 'y': msg.pose.pose.position.y, 'z': msg.pose.pose.position.z,
                    'vel_x': msg.twist.twist.linear.x, 'vel_y': msg.twist.twist.linear.y
                })
        elif topic == '/pid_indicators':
            for ind in msg.indicators:
                prefisso = ind.indicator 
                row.update({
                    f'{prefisso}_value': ind.value,
                    f'{prefisso}_can_increase': ind.can_increase,
                    f'{prefisso}_can_decrease': ind.can_decrease,
                    f'{prefisso}_failed': ind.failed
                })
        else:
            # Fallback magico: se c'è un topic nuovo, lo appiattiamo in automatico!
            row.update(_flatten(msg, prefix=""))

        dati_estratti[topic].append(row)

    # Se la bag non conteneva nessuno dei nostri topic, skippiamo senza creare cartelle vuote
    if not dati_estratti:
        print(f" ⚠️ Nessun topic target trovato in {nome_bag_originale}. Salto alla prossima.")
        return

    # Creiamo la cartella di output solo se ci sono effettivamente dati
    out_dir.mkdir(exist_ok=True)

    for topic, righe in dati_estratti.items():
        nome_file = topic.strip('/').replace('/', '_') + '.csv'
        percorso_file = out_dir / nome_file
        
        df = pd.DataFrame(righe)
        df.to_csv(percorso_file, index=False)
        print(f"  -> Salvato: {nome_file} ({len(righe)} righe) in {nome_cartella_out}/")


# --- LOOP PRINCIPALE SULLE CARTELLE ---
def main():
    parser = argparse.ArgumentParser(description="Itera su una cartella e converte le rosbag in CSV.")
    parser.add_argument("parent_folder", help="Percorso della cartella genitore che contiene le varie rosbag")
    args = parser.parse_args()

    parent_dir = Path(args.parent_folder).resolve()
    
    if not parent_dir.exists() or not parent_dir.is_dir():
        print(f"Errore: La cartella '{parent_dir}' non esiste o non è valida.")
        sys.exit(1)

    # Troviamo tutte le sottocartelle che iniziano con "rosbag2_"
    bag_dirs = [d for d in parent_dir.iterdir() if d.is_dir() and d.name.startswith("rosbag2_")]

    if not bag_dirs:
        print(f"Non ho trovato nessuna sottocartella che inizia con 'rosbag2_' dentro {parent_dir}")
        sys.exit(0)

    print(f"🚀 Trovate {len(bag_dirs)} bag da processare. Inizio l'estrazione massiva...")

    # Iteriamo su ogni bag trovata mettendole in ordine alfabetico (temporale)
    for bag_dir in sorted(bag_dirs):
        process_single_bag(bag_dir)

    print("\n" + "="*50)
    print("🎯 ELABORAZIONE MASSIVA COMPLETATA CON SUCCESSO! 🎯")
    print("="*50 + "\n")

if __name__ == '__main__':
    main()