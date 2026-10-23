"""Decode pyubx2 NAV-PVT values into explicitly named physical quantities."""


class InterruptibleSerialStream:
    """Keep partial reads across serial timeouts until complete or stopped.

    UBXReader expects read(n) to return n bytes; a serial timeout in the middle
    of a packet must not discard that packet. Only the worker uses this adapter.
    The underlying port must have a finite positive timeout so stop is observed.
    """

    def __init__(self, stream, stop):
        self.stream = stream
        self.stop = stop

    def read(self, size):
        data = bytearray()
        while len(data) < size and not self.stop.is_set():
            data.extend(self.stream.read(size - len(data)))
        return bytes(data)

    def readline(self):
        # UBXReader also consumes NMEA sentences on mixed-protocol receivers.
        data = bytearray()
        while not self.stop.is_set():
            byte = self.read(1)
            data.extend(byte)
            if not byte or byte == b'\n':
                break
            if len(data) >= 4096:
                raise ValueError('GPS serial line exceeds 4096 bytes')
        return bytes(data)


def nav_pvt_values(packet):
    # pyubx2 already scales headMot to degrees and pDOP to dimensionless units.
    # Speed/height/accuracy still arrive in millimetre-based units.
    return {
        'latitude_deg': float(packet.lat),
        'longitude_deg': float(packet.lon),
        'altitude_msl_m': float(packet.hMSL) / 1000.0,
        'ground_speed_mps': float(packet.gSpeed) / 1000.0,
        'course_deg': float(packet.headMot),
        'position_dop': float(packet.pDOP),
        'horizontal_accuracy_m': float(packet.hAcc) / 1000.0,
        'vertical_accuracy_m': float(packet.vAcc) / 1000.0,
        'satellites_used': int(packet.numSV),
        'fix_type': int(packet.fixType),
        'fix_valid': bool(packet.gnssFixOk) and packet.fixType in (2, 3, 4),
    }
