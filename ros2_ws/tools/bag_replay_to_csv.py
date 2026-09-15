import rclpy
from rclpy.node import Node
import pandas as pd
import os
import argparse
import threading
import time
import sys

# Importiamo i tipi di messaggio
from sensor_msgs.msg import Imu, NavSatFix
from std_msgs.msg import Float64
from geometry_msgs.msg import TwistWithCovarianceStamped, PoseWithCovarianceStamped
from nav_msgs.msg import Odometry

class BagListener(Node):
    def __init__(self, cartella_output):
        super().__init__('csv_exporter_node')
        self.cartella_output = cartella_output
        self.dati = {}

        os.makedirs(self.cartella_output, exist_ok=True)

        # Usiamo il tempo simulato della bag (--clock)
        self.set_parameters([rclpy.parameter.Parameter('use_sim_time', rclpy.Parameter.Type.BOOL, True)])

        # Variabili per il watchdog e sicurezza
        self.timeout_sec = 3.0
        self.primo_messaggio_ricevuto = False
        self.ultimo_tempo_bag = 0
        self.secondi_congelati = 0
        
        # NUOVA VARIABILE DI SICUREZZA (Il Lucchetto)
        self.salvataggio_in_corso = False

        # --- SOTTOSCRIZIONI ---
        self.create_subscription(Imu, '/imu_data', self.imu_cb, 10)
        self.create_subscription(Float64, '/wand_angle', lambda msg: self.float_cb(msg, '/wand_angle'), 10)
        self.create_subscription(Float64, '/flap_angle_out', lambda msg: self.float_cb(msg, '/flap_angle_out'), 10)
        self.create_subscription(NavSatFix, '/gps_data', self.gps_cb, 10)
        self.create_subscription(TwistWithCovarianceStamped, '/gps_vel_data', self.gps_vel_cb, 10)
        self.create_subscription(PoseWithCovarianceStamped, '/current_height_raw', self.height_cb, 10)
        self.create_subscription(NavSatFix, '/gps/filtered', self.gps_filt_cb, 10)

        self.get_logger().info(f"🟢 In ascolto... I CSV andranno in: '{self.cartella_output}'")
        self.get_logger().info(f"⏳ Aspetto i dati. Il nodo si spegnerà da solo quando la bag finisce!")

        # Facciamo partire il Guardiano Indipendente
        self.watchdog_thread = threading.Thread(target=self.watchdog_orologio, daemon=True)
        self.watchdog_thread.start()

    def watchdog_orologio(self):
        """Thread separato che controlla se il tempo di ROS si è congelato"""
        while True:
            time.sleep(1.0) 
            
            if not self.primo_messaggio_ricevuto or self.salvataggio_in_corso:
                continue

            tempo_attuale_bag = self.get_clock().now().nanoseconds

            if tempo_attuale_bag == self.ultimo_tempo_bag:
                self.secondi_congelati += 1
            else:
                self.secondi_congelati = 0
                self.ultimo_tempo_bag = tempo_attuale_bag

            if self.secondi_congelati >= self.timeout_sec:
                print("\n" + "="*50)
                self.get_logger().info("🛑 Tempo della bag congelato. La riproduzione è terminata!")
                
                # Chiudiamo il lucchetto PRIMA di salvare
                self.salvataggio_in_corso = True
                
                # Piccola pausa extra per far scaricare la coda dei messaggi ritardatari
                time.sleep(1.0) 
                
                self.salva_csv()
                os._exit(0)

    # --- FUNZIONI DI RICEZIONE DATI ---
    def aggiorna_stato(self):
        if not self.primo_messaggio_ricevuto:
            self.primo_messaggio_ricevuto = True
            self.ultimo_tempo_bag = self.get_clock().now().nanoseconds

    def add_row(self, topic, row):
        # Se stiamo salvando, IGNORA tutti i nuovi messaggi in arrivo
        if self.salvataggio_in_corso:
            return

        self.aggiorna_stato()
        if topic not in self.dati:
            self.dati[topic] = []
        self.dati[topic].append(row)

    # ... TUTTE LE FUNZIONI DI CALLBACK RESTANO IDENTICHE A PRIMA ...
    def imu_cb(self, msg):
        t = self.get_clock().now().nanoseconds
        self.add_row('/imu_data', {
            'timestamp_ns': t,
            'acc_x': msg.linear_acceleration.x, 'acc_y': msg.linear_acceleration.y,
            'gyro_z': msg.angular_velocity.z
        })

    def float_cb(self, msg, topic):
        t = self.get_clock().now().nanoseconds
        self.add_row(topic, {'timestamp_ns': t, 'data': msg.data})

    def gps_cb(self, msg):
        t = self.get_clock().now().nanoseconds
        self.add_row('/gps_data', {'timestamp_ns': t, 'lat': msg.latitude, 'lon': msg.longitude})

    def gps_filt_cb(self, msg):
        t = self.get_clock().now().nanoseconds
        self.add_row('/gps/filtered', {'timestamp_ns': t, 'lat': msg.latitude, 'lon': msg.longitude})

    def gps_vel_cb(self, msg):
        t = self.get_clock().now().nanoseconds
        self.add_row('/gps_vel_data', {'timestamp_ns': t, 'vel_x': msg.twist.twist.linear.x, 'vel_y': msg.twist.twist.linear.y})

    def height_cb(self, msg):
        t = self.get_clock().now().nanoseconds
        self.add_row('/current_height_raw', {'timestamp_ns': t, 'z_height': msg.pose.pose.position.z})

    # --- SALVATAGGIO ALLA FINE ---
    def salva_csv(self):
        self.get_logger().info("💾 Salvataggio dei file CSV in corso...")
        
        if not self.dati:
            self.get_logger().warn("Nessun dato ricevuto!")
            return

        for topic, righe in self.dati.items():
            nome_file = topic.strip('/').replace('/', '_') + '.csv'
            percorso = os.path.join(self.cartella_output, nome_file)
            
            try:
                # Creazione sicura del DataFrame
                df = pd.DataFrame(righe)
                df.to_csv(percorso, index=False)
                print(f" 📄 Salvato: {nome_file} ({len(righe)} messaggi)")
            except Exception as e:
                print(f" ❌ Errore nel salvataggio di {nome_file}: {e}")

        print("🎯 ESPORTAZIONE COMPLETATA CON SUCCESSO! 🎯")
        print("="*50 + "\n")


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("nome_cartella", help="Il nome della cartella in cui salvare i file")
    parsed_args, ros_args = parser.parse_known_args()

    rclpy.init(args=ros_args)
    nodo = BagListener(parsed_args.nome_cartella)

    try:
        rclpy.spin(nodo)
    except KeyboardInterrupt:
        # Se premi CTRL+C imposta il lucchetto per sicurezza
        nodo.salvataggio_in_corso = True
        nodo.salva_csv()
        os._exit(0)

if __name__ == '__main__':
    main()
