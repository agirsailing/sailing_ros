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

  # The BNO085 IMU uses the Pi 4's GPIO UART at a fixed 3 Mbaud (GPIO14/15).
  # disable-bt gives GPIO14/15 the full PL011 UART (/dev/ttyAMA0) instead of
  # the mini UART, and turns Bluetooth off. The serial console must not use it.
  # Takes effect after a reboot.
  echo "Enabling the PL011 UART on GPIO14/15 for the BNO085 IMU (Bluetooth off)..."
  sudo sed -i '/^# BEGIN AGIR UART$/,/^# END AGIR UART$/d' "$BOOT_CONFIG"
  sudo tee -a "$BOOT_CONFIG" >/dev/null <<'EOF'

# BEGIN AGIR UART
[all]
enable_uart=1
dtoverlay=disable-bt
# END AGIR UART
EOF
  local boot_cmdline
  boot_cmdline="$(dirname "$BOOT_CONFIG")/cmdline.txt"
  if [[ -f "$boot_cmdline" ]]; then
    sudo sed -i -E 's/ ?console=(serial0|ttyAMA0|ttyS0),[0-9]+//g' "$boot_cmdline"
  fi
  sudo systemctl disable --now hciuart.service 2>/dev/null || true
  sudo systemctl disable --now serial-getty@ttyAMA0.service serial-getty@serial0.service 2>/dev/null || true

  # Ultrasonic sensors and GPS use USB adapters; the IMU uses the GPIO UART above.
  # The node owns multiplexer channel switching; setup must not probe/select channels.

  echo "🔌 Configuring universal permanent permissions (666) for Serial, USB, I2C..."

  # We create a rules file using wildcards (*)
  sudo tee /etc/udev/rules.d/99-sailing-hardware.rules > /dev/null <<EOF
# Permissions for the USB serial adapters used by ultrasonic sensors and GPS
KERNEL=="ttyACM[0-9]*", MODE="0666"
KERNEL=="ttyUSB[0-9]*", MODE="0666"
# Pi GPIO UART used by the BNO085 IMU
KERNEL=="ttyAMA0", MODE="0666"

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
EOF

  # Apply rules immediately and wait for device links to be created.
  sudo udevadm control --reload-rules
  sudo udevadm trigger
  sudo udevadm settle

  for sensor_device in /dev/ultrasonic_left /dev/ultrasonic_right /dev/gps; do
    if [[ -c "$sensor_device" ]]; then
      echo "USB sensor: $sensor_device -> $(readlink -f "$sensor_device")"
    else
      echo "Warning: $sensor_device is missing; check the sensor and its physical USB port before starting ROS."
    fi
  done

  if [[ -c /dev/ttyAMA0 ]]; then
    echo "IMU UART: /dev/ttyAMA0 present."
  else
    echo "Warning: /dev/ttyAMA0 is missing; reboot so the UART boot settings take effect."
  fi

  echo "✅ UDEV hardware rules successfully applied."
}