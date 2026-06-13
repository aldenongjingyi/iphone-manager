"""
iPhone detection and communication via pymobiledevice3.

Responsibilities:
  - detect_device()      – find USB-connected iPhone, return (lockdown, info)
  - get_afc_client()     – open AFC service for filesystem access
  - DevicePoller         – background thread that polls for connect/disconnect
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)

# ── dependency check ──────────────────────────────────────────────────────────

def check_dependencies():
    """Return dict describing which dependencies are present."""
    import platform
    import shutil

    result = {'platform': platform.system(), 'ok': True, 'missing': []}

    try:
        import pymobiledevice3  # noqa: F401
        result['pymobiledevice3'] = True
    except ImportError:
        result['pymobiledevice3'] = False
        result['ok'] = False
        result['missing'].append({
            'name': 'pymobiledevice3',
            'install': 'pip install pymobiledevice3',
        })

    if platform.system() == 'Darwin':
        has_idevice = bool(shutil.which('ideviceinfo'))
        result['libimobiledevice'] = has_idevice
        if not has_idevice:
            result['missing'].append({
                'name': 'libimobiledevice',
                'install': 'brew install libimobiledevice',
                'optional': True,
            })

    return result


# ── device detection ──────────────────────────────────────────────────────────

def detect_device():
    """
    Try to connect to the first USB-attached iPhone.

    Returns
    -------
    (lockdown_client, device_info_dict)  on success
    (None, {'trusted': False, ...})      if device present but not trusted
    (None, None)                         if no device found
    (None, {'error': '...'})             if dependency missing
    """
    try:
        from pymobiledevice3.usbmux import select_devices_by_connection_type
        from pymobiledevice3.lockdown import create_using_usbmux
        from pymobiledevice3.exceptions import (
            NotTrustedError, PairingError, MuxException
        )
    except ImportError:
        return None, {'error': 'pymobiledevice3 is not installed. Run the setup script.'}

    try:
        devices = select_devices_by_connection_type(connection_type='USB')
    except Exception as e:
        logger.debug(f"usbmux select error: {e}")
        devices = []

    if not devices:
        return None, None

    serial = devices[0].serial
    try:
        lockdown = create_using_usbmux(serial=serial)
        return lockdown, _build_info(lockdown)

    except (NotTrustedError, PairingError):
        # Device is visible but user hasn't tapped "Trust"
        return None, {
            'trusted': False,
            'serial': serial,
            'error': 'Please tap "Trust" on your iPhone when prompted.',
        }
    except MuxException as e:
        logger.debug(f"MuxException: {e}")
        return None, None
    except Exception as e:
        logger.error(f"Lockdown error: {e}")
        # Generic "not paired" messages from older versions
        msg = str(e).lower()
        if any(k in msg for k in ('trust', 'pair', 'passcode')):
            return None, {
                'trusted': False,
                'serial': serial,
                'error': 'Please tap "Trust" on your iPhone when prompted.',
            }
        return None, None


def _build_info(lockdown):
    """Extract a plain-dict summary from a lockdown client."""
    try:
        vals = lockdown.all_values
        return {
            'udid': lockdown.udid,
            'name': vals.get('DeviceName', 'iPhone'),
            'product_type': vals.get('ProductType', ''),
            'ios_version': vals.get('ProductVersion', ''),
            'build_version': vals.get('BuildVersion', ''),
            'serial': vals.get('SerialNumber', ''),
            'model': vals.get('HardwareModel', ''),
            'trusted': True,
        }
    except Exception as e:
        logger.error(f"_build_info error: {e}")
        return {'udid': getattr(lockdown, 'udid', ''), 'trusted': True}


# ── AFC client ────────────────────────────────────────────────────────────────

def get_afc_client(lockdown_client):
    """Open an AFC service connection (gives access to /DCIM etc.)."""
    try:
        from pymobiledevice3.services.afc import AfcService
        return AfcService(lockdown_client)
    except Exception as e:
        logger.error(f"AFC open error: {e}")
        return None


# ── background poller ─────────────────────────────────────────────────────────

class DevicePoller:
    """
    Polls USB every *interval* seconds and fires callbacks when device
    state changes (connected / disconnected / untrusted).
    """

    def __init__(self, interval=3):
        self.interval = interval
        self._stop = threading.Event()
        self._thread = None
        self.on_connected = None      # callback(lockdown, info)
        self.on_disconnected = None   # callback()
        self.on_untrusted = None      # callback(info)

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name='device-poller')
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        last_udid = None  # None = not connected

        while not self._stop.is_set():
            try:
                lockdown, info = detect_device()
                current_udid = info.get('udid') if info else None

                if current_udid != last_udid:
                    last_udid = current_udid

                    if lockdown and info:
                        if callable(self.on_connected):
                            self.on_connected(lockdown, info)
                    elif info and not info.get('trusted', True):
                        if callable(self.on_untrusted):
                            self.on_untrusted(info)
                        last_udid = None  # keep retrying
                    else:
                        if callable(self.on_disconnected):
                            self.on_disconnected()

            except Exception as e:
                logger.error(f"DevicePoller error: {e}")

            self._stop.wait(self.interval)
