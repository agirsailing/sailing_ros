"""Decode pyubx2 NAV-PVT values into explicitly named physical quantities."""


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
