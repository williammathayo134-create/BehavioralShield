#!/usr/bin/env python3
"""
Read accelerometer and gyroscope data from an MPU‑6050 (or compatible) sensor
via I²C and print the values in physical units (g and °/s).

Requirements:
    pip install smbus2
"""
import os
import time
from smbus2 import SMBus

# ----------------------------------------------------------------------
# MPU‑6050 register map (only the registers we need)
# ----------------------------------------------------------------------
MPU6050_ADDR = 0x68          # I²C address when AD0 pin is low
PWR_MGMT_1   = 0x6B
ACCEL_XOUT_H = 0x3B
GYRO_XOUT_H  = 0x43
ACCEL_CONFIG = 0x1C
GYRO_CONFIG  = 0x1B

# ----------------------------------------------------------------------
# Sensitivity settings (default = ±2 g for accel, ±250 °/s for gyro)
# ----------------------------------------------------------------------
ACCEL_SENS = 16384.0   # LSB/g  (2 g range)
GYRO_SENS  = 131.0     # LSB/(°/s) (250 °/s range)

# ----------------------------------------------------------------------
class MPU6050:
    """Simple driver for the MPU‑6050 accelerometer + gyroscope."""

    def __init__(self, bus_id: int = 1, address: int = MPU6050_ADDR):
        self.bus = SMBus(bus_id)
        self.addr = address
        self._wake_up()
        self._set_accel_range(0)   # 0 → ±2 g
        self._set_gyro_range(0)    # 0 → ±250 °/s

    # ------------------------------------------------------------------
    def _write_byte(self, reg: int, value: int) -> None:
        self.bus.write_byte_data(self.addr, reg, value)

    def _read_bytes(self, reg: int, length: int) -> bytes:
        return self.bus.read_i2c_block_data(self.addr, reg, length)

    # ------------------------------------------------------------------
    def _wake_up(self) -> None:
        """Take the sensor out of sleep mode."""
        self._write_byte(PWR_MGMT_1, 0x00)
        time.sleep(0.1)

    def _set_accel_range(self, range_sel: int) -> None:
        """range_sel: 0=±2g, 1=±4g, 2=±8g, 3=±16g."""
        self._write_byte(ACCEL_CONFIG, range_sel << 3)

    def _set_gyro_range(self, range_sel: int) -> None:
        """range_sel: 0=±250°/s, 1=±500°/s, 2=±1000°/s, 3=±2000°/s."""
        self._write_byte(GYRO_CONFIG, range_sel << 3)

    # ------------------------------------------------------------------
    @staticmethod
    def _twos_complement(high: int, low: int) -> int:
        """Combine two bytes and interpret as signed 16‑bit."""
        value = (high << 8) | low
        if value & 0x8000:          # negative number
            value = -((65535 - value) + 1)
        return value

    # ------------------------------------------------------------------
    def read_accel(self) -> tuple[float, float, float]:
        """Return (ax, ay, az) in g."""
        raw = self._read_bytes(ACCEL_XOUT_H, 6)
        ax = self._twos_complement(raw[0], raw[1]) / ACCEL_SENS
        ay = self._twos_complement(raw[2], raw[3]) / ACCEL_SENS
        az = self._twos_complement(raw[4], raw[5]) / ACCEL_SENS
        return ax, ay, az

    def read_gyro(self) -> tuple[float, float, float]:
        """Return (gx, gy, gz) in °/s."""
        raw = self._read_bytes(GYRO_XOUT_H, 6)
        gx = self._twos_complement(raw[0], raw[1]) / GYRO_SENS
        gy = self._twos_complement(raw[2], raw[3]) / GYRO_SENS
        gz = self._twos_complement(raw[4], raw[5]) / GYRO_SENS
        return gx, gy, gz

    # ------------------------------------------------------------------
    def close(self) -> None:
        self.bus.close()


# ----------------------------------------------------------------------
def main() -> None:
    sensor = MPU6050()
    print("Press Ctrl‑C to stop.\n")
    try:
 while True:
            if os.getenv("SYSTEM_ENABLED", "false").lower() != "true":                time.sleep(1)
                continue

            ax, ay, az = sensor.read_accel()
            gx, gy, gz = sensor.read_gyro()
            print(
                f"Accel [g] : X={ax:6.3f} Y={ay:6.3f} Z={az:6.3f} | "
                f"Gyro [°/s]: X={gx:6.2f} Y={gy:6.2f} Z={gz:6.2f}"
            )
            time.sleep(0.1)  # 10 Hz update rate
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        sensor.close()



if __name__ == "__main__":
    main()
