#!/usr/bin/env bash
# Loaded by lib/common.sh before Git changes the checkout.

hardware_configure() {
  echo "Enabling the primary I2C bus for the compass multiplexer..."
  # Append an explicit [all] section so this setting is not trapped under a model filter.
  # Re-running setup replaces only our block; other boot settings remain intact.
  sudo sed -i '/^# BEGIN AGIR I2C$/,/^# END AGIR I2C$/d' "$BOOT_CONFIG"
  sudo tee -a "$BOOT_CONFIG" >/dev/null <<'EOF'

# BEGIN AGIR I2C
[all]
dtparam=i2c_arm=on
# END AGIR I2C
EOF
  printf 'i2c-dev\n' | sudo tee /etc/modules-load.d/agir-i2c.conf >/dev/null
  sudo modprobe i2c-dev

  # Both ultrasonic sensors, GPS and the BNO085 IMU currently use USB adapters. No STM32 UART,
  # fixed 115200 baud rate, Bluetooth disable or Pi 5 overlay is needed here.
  # The node owns multiplexer channel switching; setup must not probe/select channels.

  echo "🔌 Configuring universal permanent permissions (666) for Serial, USB, I2C..."

  # We create a rules file using wildcards (*)
  sudo tee /etc/udev/rules.d/99-sailing-hardware.rules > /dev/null <<EOF
# Permissions for the USB serial adapters used by ultrasonic sensors and GPS
KERNEL=="ttyACM[0-9]*", MODE="0666"
KERNEL=="ttyUSB[0-9]*", MODE="0666"

# Permissions for ALL I2C buses
KERNEL=="i2c-[0-9]*", MODE="0666"

# Permissions for ALL GPIO pins
KERNEL=="gpiochip[0-9]*", MODE="0666"
EOF

  # Stable names follow the physical USB ports on this Raspberry Pi 4.
  # Keep each sensor connected to its assigned port; USB enumeration may change.
  # Replace the same file on every setup run so rules are never duplicated.
  sudo tee /etc/udev/rules.d/99-boat-serial.rules >/dev/null <<'EOF'
# Ultrasonic left - port 1.4
SUBSYSTEM=="tty", KERNELS=="1-1.4:1.0", SYMLINK+="ultrasonic_left", MODE="0666"
# Ultrasonic right - port 1.3
SUBSYSTEM=="tty", KERNELS=="1-1.3:1.0", SYMLINK+="ultrasonic_right", MODE="0666"
# GPS - port 1.2
SUBSYSTEM=="tty", KERNELS=="1-1.2:1.0", SYMLINK+="gps", MODE="0666"
# IMU (BNO085, SHTP UART at 3 Mbaud) - port 1.1
SUBSYSTEM=="tty", KERNELS=="1-1.1:1.0", SYMLINK+="imu", MODE="0666"
# FTDI converters buffer 16 ms by default; 1 ms keeps IMU latency low.
ACTION=="add", SUBSYSTEM=="usb-serial", DRIVERS=="ftdi_sio", ATTR{latency_timer}="1"
EOF

  # Apply rules immediately and wait for device links to be created.
  sudo udevadm control --reload-rules
  sudo udevadm trigger
  sudo udevadm settle

  for sensor_device in /dev/ultrasonic_left /dev/ultrasonic_right /dev/gps /dev/imu; do
    if [[ -c "$sensor_device" ]]; then
      echo "USB sensor: $sensor_device -> $(readlink -f "$sensor_device")"
    else
      echo "Warning: $sensor_device is missing; check the sensor and its physical USB port before starting ROS."
    fi
  done

  echo "✅ UDEV hardware rules successfully applied."
}