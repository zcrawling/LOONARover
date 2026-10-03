"""Wire-v2 IMU decode, shared layout for BNO055 UART and legacy BNO08x."""
import math
import struct

NAMES = {1: 'accel_mps2', 2: 'gyro_radps', 3: 'mag_uT',
         4: 'linear_mps2', 5: 'quaternion_xyzw', 6: 'gravity_mps2'}


def decode_imu(payload):
    if len(payload) != 36:
        raise ValueError('IMU payload must be 36 bytes')
    sensor, calibration, seq, lost, stamp, *tail = struct.unpack('<4BQ5fI', payload)
    if sensor not in NAMES or not all(math.isfinite(v) for v in tail[:5]):
        raise ValueError('invalid IMU report')
    return dict(sensor=NAMES[sensor], calibration=calibration & 3,
                sequence=seq, lost=lost, sensor_or_receipt_us=stamp,
                values=tail[:4 if sensor == 5 else 3], reinitializations=tail[5])
