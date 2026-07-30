"""
biometric.py
Integration with ZKTeco (and compatible eSSL/Realtime clone) biometric
fingerprint devices over LAN/Wi-Fi, using the standard ZK network
protocol via the `pyzk` library.

The device must be:
  - On the same Wi-Fi/LAN network as the computer running this app
  - Given a static/fixed IP address (set this on the device itself,
    under Comm. / Ethernet settings, or reserve it in your router)
  - Have "Comm Key" / device password left as 0 (default) unless you
    have set one on the device - if you have, enter it in Settings.

This module never enrols fingerprints - enrolment (registering a
person's finger against a Device User ID) is done on the device itself
using its own menu, as usual. This module only:
  1. Reads the list of users already enrolled on the device
     (device_user_id + name), so you can map each one to a student.
  2. Reads punch/attendance logs from the device for a given date.
"""
from datetime import datetime

try:
    from zk import ZK
    from zk.exception import ZKErrorConnection, ZKErrorResponse
    PYZK_AVAILABLE = True
except ImportError:
    PYZK_AVAILABLE = False


class BiometricError(Exception):
    pass


def _connect(ip, port=4370, password=0, timeout=8):
    if not PYZK_AVAILABLE:
        raise BiometricError(
            "The 'pyzk' package is not installed. Run: pip install pyzk "
            "(then restart the app)."
        )
    zk = ZK(ip, port=int(port), timeout=timeout, password=int(password or 0),
             force_udp=False, ommit_ping=False)
    try:
        conn = zk.connect()
    except Exception as e:
        # Retry once over UDP - some cheaper/older ZK-protocol clones
        # (common eSSL/Realtime rebrands) only respond over UDP.
        try:
            zk = ZK(ip, port=int(port), timeout=timeout, password=int(password or 0),
                     force_udp=True, ommit_ping=True)
            conn = zk.connect()
        except Exception:
            raise BiometricError(
                f"Could not connect to the device at {ip}:{port}. "
                f"Check that the device is powered on, connected to the "
                f"same network, and the IP address/port are correct. "
                f"({e})"
            )
    return conn


def test_connection(ip, port=4370, password=0, timeout=8):
    """Returns a dict with basic device info if reachable, else raises BiometricError."""
    conn = _connect(ip, port, password, timeout)
    try:
        info = {
            "firmware_version": conn.get_firmware_version(),
            "serial_number": conn.get_serialnumber(),
            "device_name": conn.get_device_name(),
            "user_count": len(conn.get_users()),
        }
        return info
    finally:
        conn.disconnect()


def fetch_device_users(ip, port=4370, password=0, timeout=8):
    """Returns a list of {device_user_id, name} enrolled on the device."""
    conn = _connect(ip, port, password, timeout)
    try:
        users = conn.get_users()
        return [{"device_user_id": u.user_id, "name": u.name} for u in users]
    finally:
        conn.disconnect()


def fetch_attendance_for_date(ip, target_date, port=4370, password=0, timeout=8):
    """
    target_date: a datetime.date
    Returns a list of {device_user_id, timestamp, punch} for punches
    that fall on that calendar date (device is queried for its full log;
    this function filters to the requested day).
    """
    conn = _connect(ip, port, password, timeout)
    try:
        conn.disable_device()
        logs = conn.get_attendance()
    finally:
        try:
            conn.enable_device()
        except Exception:
            pass
        conn.disconnect()

    results = []
    for rec in logs:
        ts = rec.timestamp
        if isinstance(ts, datetime) and ts.date() == target_date:
            results.append({
                "device_user_id": str(rec.user_id),
                "timestamp": ts,
                "punch": getattr(rec, "punch", None),
            })
    return results
