"""
Android device detection and file transfer via ADB.

Requires `adb` to be in PATH (Android SDK Platform Tools).
Optional: pip install adbutils

The interface mirrors device.py so app.py can handle both uniformly.
"""

import logging
import os
import subprocess
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Use bundled adb if provided via ADB_PATH env var (set by Electron main.js)
_ADB_BIN = os.environ.get('ADB_PATH', 'adb')

# ── ADB helpers ───────────────────────────────────────────────────────────────

def _adb(*args, timeout=15):
    """Run an adb command, return (stdout, returncode)."""
    try:
        result = subprocess.run(
            [_ADB_BIN, *args],
            capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip(), result.returncode
    except FileNotFoundError:
        return '', -1   # adb not in PATH
    except subprocess.TimeoutExpired:
        return '', -2


def adb_available():
    """Return True if adb is available in PATH."""
    out, rc = _adb('version')
    return rc == 0


def detect_android_device():
    """
    Detect a USB-attached Android device.

    Returns
    -------
    dict   device info (same shape as iOS _build_info)  if found
    None                                                  if not found
    """
    out, rc = _adb('devices')
    if rc != 0:
        return None

    # Parse `adb devices` output — skip header line
    lines = [l for l in out.splitlines()[1:] if l.strip()]
    # Find a device in 'device' state (not 'offline', 'unauthorized', 'recovery')
    connected = [l for l in lines if '\tdevice' in l]
    if not connected:
        unauthorized = [l for l in lines if 'unauthorized' in l]
        if unauthorized:
            logger.info("Android device connected but unauthorized — enable USB debugging")
        return None

    serial = connected[0].split('\t')[0].strip()

    def prop(key):
        out, _ = _adb('-s', serial, 'shell', 'getprop', key)
        return out.strip()

    model   = prop('ro.product.model') or prop('ro.product.name') or 'Android Device'
    brand   = prop('ro.product.brand') or ''
    device  = prop('ro.product.device') or serial
    android = prop('ro.build.version.release') or '?'

    name = f"{brand} {model}".strip() if brand else model

    return {
        'serial': serial,
        'udid': serial,
        'name': name,
        'product_type': device,
        'ios_version': android,       # reuse key for version string
        'build_version': prop('ro.build.version.incremental'),
        'model': model,
        'trusted': True,
        'device_type': 'android',
    }


def get_android_storage(serial):
    """Return storage dict matching iOS storage keys."""
    out, rc = _adb('-s', serial, 'shell', 'df', '/sdcard')
    if rc != 0:
        return None
    try:
        lines = [l for l in out.splitlines() if '/sdcard' in l or '/storage/emulated' in l]
        if not lines:
            return None
        parts = lines[0].split()
        # df output: Filesystem 1K-blocks Used Available Use% Mounted
        total_kb = int(parts[1])
        used_kb  = int(parts[2])
        free_kb  = int(parts[3])
        total = total_kb * 1024
        used  = used_kb  * 1024
        free  = free_kb  * 1024
        return {
            'total': total, 'used': used, 'free': free,
            'media_cache': 0,
            'total_gb': round(total / 1e9, 2),
            'used_gb':  round(used  / 1e9, 2),
            'free_gb':  round(free  / 1e9, 2),
            'media_cache_gb': 0,
            'used_percent': round(used / total * 100, 1) if total else 0,
        }
    except Exception as e:
        logger.debug(f"Android storage parse error: {e}")
        return None


MEDIA_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.gif',
                    '.bmp', '.webp', '.mp4', '.mov', '.avi', '.mkv',
                    '.m4v', '.3gp', '.wmv'}

VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.m4v', '.3gp', '.wmv'}


def list_android_media(serial):
    """List all media files from device in one batched ADB call."""
    # One shell invocation: find files + stat them all in one round-trip
    search = '/sdcard/DCIM /sdcard/Pictures /sdcard/Movies /sdcard/WhatsApp/Media'
    cmd = (
        f'find {search} -type f 2>/dev/null | '
        'while IFS= read -r f; do stat -c "%n	%s	%Y" "" 2>/dev/null; done'
    )
    out, rc = _adb('-s', serial, 'shell', cmd, timeout=120)

    files = []
    for line in out.splitlines():
        line = line.strip()
        if not line or '	' not in line:
            continue
        parts = line.split('	')
        if len(parts) < 3:
            continue
        path = parts[0]
        try:
            size  = int(parts[1])
            mtime = int(float(parts[2]))
        except (ValueError, IndexError):
            size, mtime = 0, 0

        ext = Path(path).suffix.lower()
        if ext not in MEDIA_EXTENSIONS:
            continue

        files.append({
            'path':     path,
            'filename': Path(path).name,
            'folder':   Path(path).parent.name,
            'size':     size,
            'size_mb':  round(size / 1_048_576, 2),
            'mtime':    mtime,
            'type':     'video' if ext in VIDEO_EXTENSIONS else 'image',
            'ext':      ext,
            'device_type': 'android',
        })

    return files

def get_android_thumbnail(serial, file_path, size=300):
    """Pull file from device and return JPEG thumbnail bytes."""
    import io
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(suffix=Path(file_path).suffix, delete=False) as tmp:
            tmp_path = tmp.name

        _, rc = _adb('-s', serial, 'pull', file_path, tmp_path, timeout=30)
        if rc != 0:
            return None

        from PIL import Image
        img = Image.open(tmp_path)
        img.thumbnail((size, size))
        out = io.BytesIO()
        img.convert('RGB').save(out, format='JPEG', quality=75)
        return out.getvalue()
    except Exception as e:
        logger.debug(f"Android thumbnail error: {e}")
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def transfer_android_files(serial, files, destination, already_transferred=None, progress_cb=None):
    """Pull files from Android device to destination directory."""
    import shutil
    already = set(already_transferred or [])
    dest_dir = Path(destination)
    dest_dir.mkdir(parents=True, exist_ok=True)

    success, skipped, failed = [], [], []
    total = len(files)

    for i, f in enumerate(files):
        path = f['path']
        fname = f['filename']

        if path in already:
            skipped.append(f)
            if progress_cb:
                progress_cb(i + 1, total, fname, 'skipped')
            continue

        dest_path = dest_dir / fname
        # Avoid overwrite
        if dest_path.exists():
            stem = dest_path.stem
            ext = dest_path.suffix
            dest_path = dest_dir / f"{stem}_{int(time.time())}{ext}"

        _, rc = _adb('-s', serial, 'pull', path, str(dest_path), timeout=120)
        if rc == 0:
            success.append({**f, 'dest_path': str(dest_path)})
            if progress_cb:
                progress_cb(i + 1, total, fname, 'success')
        else:
            failed.append({**f, 'reason': 'adb pull failed'})
            if progress_cb:
                progress_cb(i + 1, total, fname, 'failed')

    return {'success': success, 'skipped': skipped, 'failed': failed,
            'total_bytes': sum(f.get('size', 0) for f in success)}


def delete_android_files(serial, file_paths):
    """Delete files from Android device via adb shell rm."""
    success, failed = [], []
    for path in file_paths:
        _, rc = _adb('-s', serial, 'shell', 'rm', '-f', path, timeout=30)
        if rc == 0:
            success.append(path)
        else:
            failed.append({'path': path, 'reason': 'adb rm failed'})
    return {'success': success, 'failed': failed}


# ── Android device poller ─────────────────────────────────────────────────────

class AndroidDevicePoller:
    """
    Polls for USB-attached Android devices every *interval* seconds.
    Fires same callbacks as DevicePoller (on_connected, on_disconnected).
    """

    def __init__(self, interval=3):
        self.interval = interval
        self._stop = threading.Event()
        self._thread = None
        self.on_connected = None    # callback(info_dict)
        self.on_disconnected = None # callback()

    def start(self):
        if not adb_available():
            logger.info("adb not found in PATH — Android support disabled")
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name='android-poller')
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        last_serial = None
        while not self._stop.is_set():
            try:
                info = detect_android_device()
                current_serial = info['serial'] if info else None

                if current_serial != last_serial:
                    last_serial = current_serial
                    if info and callable(self.on_connected):
                        self.on_connected(info)
                    elif not info and callable(self.on_disconnected):
                        self.on_disconnected()
            except Exception as e:
                logger.error(f"AndroidDevicePoller error: {e}")
            self._stop.wait(self.interval)
