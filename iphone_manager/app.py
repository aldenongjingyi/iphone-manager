"""
iPhone Manager — Flask backend.

Installed entry point:  iphone-manager
Direct run:             python -m iphone_manager
"""

import json
import logging
import os
import queue
import random
import threading
import time
import webbrowser
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

from . import database as db
from . import device as dev
from . import storage as stor
from . import transfer as xfr

# ── config ────────────────────────────────────────────────────────────────────

DEMO_MODE = os.environ.get('DEMO_MODE', '').lower() in ('1', 'true', 'yes')
PORT      = int(os.environ.get('PORT', 5000))
IS_CLOUD  = bool(os.environ.get('RENDER') or os.environ.get('RAILWAY_ENVIRONMENT')
                 or os.environ.get('FLY_APP_NAME'))
HOST      = '0.0.0.0' if IS_CLOUD else '127.0.0.1'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-7s  %(name)s — %(message)s',
)
logger = logging.getLogger(__name__)

# Flask finds templates/static relative to this file (inside the package dir)
app = Flask(__name__)

# ── shared state ──────────────────────────────────────────────────────────────

_state = {'lockdown': None, 'device_info': None, 'afc': None}
_state_lock = threading.Lock()

_sse_queues: list[queue.Queue] = []
_sse_lock = threading.Lock()


def _broadcast(event: str, data: dict):
    msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
    with _sse_lock:
        dead = []
        for q in _sse_queues:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _sse_queues.remove(q)


def _get_afc():
    with _state_lock:
        lockdown = _state['lockdown']
        if not lockdown:
            return None
        if not _state['afc']:
            _state['afc'] = dev.get_afc_client(lockdown)
        return _state['afc']


def _reset_afc():
    with _state_lock:
        _state['afc'] = None


# ── device poller callbacks ───────────────────────────────────────────────────

def _on_connected(lockdown, info):
    with _state_lock:
        _state['lockdown'] = lockdown
        _state['device_info'] = info
        _state['afc'] = None

    try:
        s = stor.get_storage_info(lockdown)
        if s:
            info = {**info, 'storage': s}
    except Exception:
        pass

    logger.info(f"Device connected: {info.get('name')} ({info.get('udid', '')[:8]}…)")
    _broadcast('device_connected', info)


def _on_disconnected():
    with _state_lock:
        _state['lockdown'] = None
        _state['device_info'] = None
        _state['afc'] = None

    logger.info("Device disconnected")
    _broadcast('device_disconnected', {})


def _on_untrusted(info):
    logger.info("Device not trusted — waiting for user to tap Trust")
    _broadcast('device_untrusted', info)


# ── routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html', demo_mode=DEMO_MODE)


@app.route('/api/device')
def api_device():
    if DEMO_MODE:
        return jsonify({**_DEMO_DEVICE, 'connected': True, 'storage': _DEMO_STORAGE})

    with _state_lock:
        info     = _state['device_info']
        lockdown = _state['lockdown']

    if not info:
        return jsonify({'connected': False})

    result = {**info, 'connected': bool(lockdown)}
    if lockdown:
        try:
            s = stor.get_storage_info(lockdown)
            if s:
                result['storage'] = s
        except Exception:
            pass
    return jsonify(result)


@app.route('/api/files')
def api_files():
    if DEMO_MODE:
        transferred = _demo_transferred()
        files = [{**f, 'transferred': f['path'] in transferred} for f in _DEMO_FILES]
        return jsonify({'files': files, 'total': len(files),
                        'transferred_count': sum(1 for f in files if f['transferred'])})

    afc = _get_afc()
    if not afc:
        return jsonify({'error': 'No device connected'}), 400

    with _state_lock:
        udid = _state['device_info'].get('udid', '') if _state['device_info'] else ''

    try:
        files      = xfr.list_media_files(afc)
        transferred = db.get_transferred_files(udid)
        for f in files:
            f['transferred'] = f['path'] in transferred
        return jsonify({'files': files, 'total': len(files),
                        'transferred_count': sum(1 for f in files if f['transferred'])})
    except Exception as e:
        logger.error(f"List files error: {e}")
        _reset_afc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/thumbnail')
def api_thumbnail():
    file_path = request.args.get('path', '').strip()
    if not file_path:
        return ('', 404)

    if DEMO_MODE:
        svg = _demo_thumbnail_svg(file_path)
        return Response(svg, mimetype='image/svg+xml',
                        headers={'Cache-Control': 'max-age=3600'})

    afc = _get_afc()
    if not afc:
        return ('', 503)

    data = xfr.get_thumbnail_bytes(afc, file_path)
    if not data:
        return ('', 404)

    ext = Path(file_path).suffix.lower()
    mime_map = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
        '.gif': 'image/gif', '.heic': 'image/heic', '.heif': 'image/heic',
        '.bmp': 'image/bmp', '.tiff': 'image/tiff', '.tif': 'image/tiff',
    }
    mime = mime_map.get(ext, 'application/octet-stream')
    return Response(data, mimetype=mime, headers={'Cache-Control': 'max-age=3600'})


@app.route('/api/transfer', methods=['POST'])
def api_transfer():
    body       = request.json or {}
    file_paths = body.get('files', [])
    destination = body.get('destination', '').strip()

    if not file_paths:
        return jsonify({'error': 'No files selected'}), 400
    if not destination:
        return jsonify({'error': 'No destination folder specified'}), 400

    if DEMO_MODE:
        selected = [f for f in _DEMO_FILES if f['path'] in set(file_paths)]
        threading.Thread(target=_demo_simulate_transfer, args=(selected,),
                         daemon=True).start()
        return jsonify({'status': 'started', 'total': len(selected)})

    afc = _get_afc()
    if not afc:
        return jsonify({'error': 'No device connected'}), 400

    with _state_lock:
        udid = _state['device_info'].get('udid', '') if _state['device_info'] else ''

    try:
        all_files = xfr.list_media_files(afc)
    except Exception as e:
        _reset_afc()
        return jsonify({'error': f'Cannot read device: {e}'}), 500

    path_set = set(file_paths)
    selected = [f for f in all_files if f['path'] in path_set]
    if not selected:
        return jsonify({'error': 'None of the selected paths were found on device'}), 400

    total_size = sum(f['size'] for f in selected)
    has_space, free = xfr.check_disk_space(destination, total_size)
    if not has_space:
        return jsonify({'error': (f'Not enough disk space. Need {total_size/1e9:.2f} GB, '
                                  f'have {free/1e9:.2f} GB free.')}), 400

    already = db.get_transferred_files(udid)

    def run():
        def progress(done, total, filename, status):
            _broadcast('transfer_progress', {
                'done': done, 'total': total, 'filename': filename,
                'status': status,
                'percent': round(done / total * 100, 1) if total else 0,
            })

        try:
            results = xfr.transfer_files(afc, selected, destination,
                                          already_transferred=already, progress_cb=progress)
            for f in results['success']:
                db.record_transfer(udid, f['path'], f['filename'], f['dest_path'], f['size'])
            _broadcast('transfer_complete', {
                'success_count': len(results['success']),
                'skipped_count': len(results['skipped']),
                'failed_count':  len(results['failed']),
                'failed': [{'filename': f['filename'], 'reason': f.get('reason', '')}
                           for f in results['failed']],
            })
        except Exception as e:
            logger.error(f"Transfer thread error: {e}")
            _broadcast('transfer_error', {'error': str(e)})

    threading.Thread(target=run, daemon=True, name='transfer').start()
    return jsonify({'status': 'started', 'total': len(selected)})


@app.route('/api/delete', methods=['POST'])
def api_delete():
    body       = request.json or {}
    file_paths = body.get('files', [])
    confirmed  = body.get('confirmed', False)

    if not confirmed:
        return jsonify({'error': 'Explicit confirmation required (confirmed=true)'}), 400
    if not file_paths:
        return jsonify({'error': 'No files specified'}), 400

    if DEMO_MODE:
        time.sleep(0.4)
        return jsonify({'success_count': len(file_paths), 'failed_count': 0, 'failed': []})

    afc = _get_afc()
    if not afc:
        return jsonify({'error': 'No device connected'}), 400

    with _state_lock:
        udid = _state['device_info'].get('udid', '') if _state['device_info'] else ''

    results = xfr.delete_files(afc, file_paths)
    for path in results['success']:
        db.mark_deleted(udid, path)

    return jsonify({'success_count': len(results['success']),
                    'failed_count':  len(results['failed']),
                    'failed':        results['failed']})


@app.route('/api/history')
def api_history():
    if DEMO_MODE:
        return jsonify({'history': _DEMO_HISTORY, 'stats': _DEMO_HISTORY_STATS})

    with _state_lock:
        udid = _state['device_info'].get('udid') if _state['device_info'] else None

    return jsonify({'history': db.get_transfer_history(udid), 'stats': db.get_stats(udid)})


@app.route('/api/check_dependencies')
def api_check_dependencies():
    if DEMO_MODE:
        return jsonify({'ok': True, 'platform': 'Demo', 'demo': True})
    return jsonify(dev.check_dependencies())


@app.route('/api/events')
def api_events():
    q = queue.Queue(maxsize=50)
    with _sse_lock:
        _sse_queues.append(q)

    def stream():
        if DEMO_MODE:
            yield (f"event: device_connected\n"
                   f"data: {json.dumps({**_DEMO_DEVICE, 'storage': _DEMO_STORAGE})}\n\n")
        else:
            with _state_lock:
                info     = _state['device_info']
                lockdown = _state['lockdown']

            if lockdown and info:
                try:
                    s = stor.get_storage_info(lockdown)
                    if s:
                        info = {**info, 'storage': s}
                except Exception:
                    pass
                yield f"event: device_connected\ndata: {json.dumps(info)}\n\n"
            elif info and not info.get('trusted', True):
                yield f"event: device_untrusted\ndata: {json.dumps(info)}\n\n"
            else:
                yield "event: device_disconnected\ndata: {}\n\n"

        try:
            while True:
                try:
                    msg = q.get(timeout=25)
                    yield msg
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with _sse_lock:
                try:
                    _sse_queues.remove(q)
                except ValueError:
                    pass

    return Response(stream(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no',
                             'Connection': 'keep-alive'})


# ── demo data ─────────────────────────────────────────────────────────────────

_DEMO_UDID = 'DEMO00000000000000000000000000000000000'

_DEMO_DEVICE = {
    'udid': _DEMO_UDID, 'name': "Alex's iPhone 15 Pro",
    'product_type': 'iPhone16,1', 'ios_version': '17.5.1',
    'build_version': '21F90', 'serial': 'DEMO123456',
    'model': 'D83AP', 'trusted': True, 'connected': True,
}

_DEMO_STORAGE = {
    'total': 256_060_514_304, 'used': 183_500_000_000, 'free': 72_560_514_304,
    'media_cache': 13_400_000_000, 'total_gb': 238.42, 'used_gb': 170.92,
    'free_gb': 67.6, 'media_cache_gb': 12.48, 'used_percent': 71.7,
}


def _make_demo_files():
    rng = random.Random(42)
    files, n = [], 1
    for folder in ['100APPLE', '101APPLE', '102APPLE']:
        for _ in range(10 if folder == '100APPLE' else 8):
            fname = f'IMG_{n:04d}.HEIC'
            size  = rng.randint(1_800_000, 8_500_000)
            files.append({'path': f'/DCIM/{folder}/{fname}', 'filename': fname,
                          'folder': folder, 'size': size,
                          'size_mb': round(size/1_048_576, 2),
                          'mtime': int(time.time()) - rng.randint(3600, 60*86400),
                          'type': 'image', 'ext': '.heic'})
            n += 1
        for _ in range(3):
            fname = f'IMG_{n:04d}.JPG'
            size  = rng.randint(900_000, 3_200_000)
            files.append({'path': f'/DCIM/{folder}/{fname}', 'filename': fname,
                          'folder': folder, 'size': size,
                          'size_mb': round(size/1_048_576, 2),
                          'mtime': int(time.time()) - rng.randint(3600, 60*86400),
                          'type': 'image', 'ext': '.jpg'})
            n += 1
        for _ in range(3):
            fname = f'IMG_{n:04d}.MOV'
            size  = rng.randint(22_000_000, 180_000_000)
            files.append({'path': f'/DCIM/{folder}/{fname}', 'filename': fname,
                          'folder': folder, 'size': size,
                          'size_mb': round(size/1_048_576, 2),
                          'mtime': int(time.time()) - rng.randint(3600, 60*86400),
                          'type': 'video', 'ext': '.mov'})
            n += 1
    return files


_DEMO_FILES = _make_demo_files()
_DEMO_TRANSFERRED_PATHS = {f['path'] for f in _DEMO_FILES[:6]}


def _demo_transferred():
    return _DEMO_TRANSFERRED_PATHS


def _demo_simulate_transfer(selected):
    total = len(selected)
    for i, f in enumerate(selected):
        time.sleep(min(0.15 + f['size'] / 1_000_000 * 0.004, 0.6))
        _broadcast('transfer_progress', {
            'done': i+1, 'total': total, 'filename': f['filename'],
            'status': 'success', 'percent': round((i+1)/total*100, 1),
        })
    time.sleep(0.2)
    _broadcast('transfer_complete', {
        'success_count': total, 'skipped_count': 0, 'failed_count': 0, 'failed': [],
    })


_THUMB_PALETTE = [
    ('#0a84ff', '#0055cc'), ('#30d158', '#1a8a3a'), ('#ff9f0a', '#cc6d00'),
    ('#bf5af2', '#7a2ea8'), ('#ff375f', '#b0001c'), ('#64d2ff', '#0099cc'),
    ('#ffd60a', '#b38c00'), ('#ac8e68', '#6e5a3e'),
]


def _demo_thumbnail_svg(file_path: str) -> bytes:
    filename = Path(file_path).name
    ext      = Path(file_path).suffix.lower()
    c1, c2   = _THUMB_PALETTE[hash(filename) % len(_THUMB_PALETTE)]
    icon     = '▶' if ext in ('.mov', '.mp4', '.m4v', '.avi') else '✦'
    label    = filename[:14] + ('…' if len(filename) > 14 else '')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200">'
           f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
           f'<stop offset="0%" stop-color="{c1}"/><stop offset="100%" stop-color="{c2}"/>'
           f'</linearGradient></defs>'
           f'<rect width="200" height="200" fill="url(#g)"/>'
           f'<text x="100" y="105" font-size="52" text-anchor="middle" '
           f'fill="rgba(255,255,255,0.9)" font-family="system-ui,sans-serif">{icon}</text>'
           f'<text x="100" y="168" font-size="13" text-anchor="middle" '
           f'fill="rgba(255,255,255,0.6)" font-family="system-ui,sans-serif">{label}</text>'
           f'</svg>')
    return svg.encode()


_DEMO_HISTORY = [
    {'id': i+1, 'device_udid': _DEMO_UDID, 'file_path': f['path'],
     'filename': f['filename'], 'destination': '/Users/alex/Pictures/iPhone',
     'file_size': f['size'], 'transferred_at': '2025-06-10 14:32:17',
     'status': 'completed', 'deleted_from_device': 0}
    for i, f in enumerate(_DEMO_FILES[:6])
]
_DEMO_HISTORY_STATS = {
    'total': 6,
    'total_bytes': sum(f['size'] for f in _DEMO_FILES[:6]),
    'deleted_count': 0,
}


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    if not DEMO_MODE:
        db.init_db()
        logger.info("Database initialised")

        poller = dev.DevicePoller(interval=3)
        poller.on_connected    = _on_connected
        poller.on_disconnected = _on_disconnected
        poller.on_untrusted    = _on_untrusted
        poller.start()
        logger.info("Device poller started")

    url = f'http://127.0.0.1:{PORT}'
    mode = '  [DEMO — no iPhone needed]' if DEMO_MODE else ''

    if not IS_CLOUD:
        def _open():
            time.sleep(1.2)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    print(f'\n  iPhone Manager  →  {url}{mode}')
    print('  Press Ctrl+C to stop.\n')
    app.run(host=HOST, port=PORT, debug=False, threaded=True, use_reloader=False)
