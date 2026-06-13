"""
File transfer and deletion logic for iPhone photos/videos via AFC.
All public functions are async — call them via run_async() from sync code.
"""

import os
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.gif',
              '.bmp', '.tiff', '.tif', '.raw', '.cr2', '.nef', '.arw', '.dng'}
VIDEO_EXTS = {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.3gp', '.wmv', '.mts'}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS

CHUNK_SIZE = 1024 * 512   # 512 KB read chunks


# ── file listing ──────────────────────────────────────────────────────────────

async def list_media_files(afc_client):
    """
    Walk /DCIM on the iPhone and return a list of media file dicts.
    Each dict: path, filename, folder, size, size_mb, mtime, type, ext
    """
    files = []
    dcim = '/DCIM'

    try:
        folders = sorted(await afc_client.listdir(dcim))
    except Exception as e:
        logger.error(f"Cannot list /DCIM: {e}")
        return files

    for folder in folders:
        folder_path = f'{dcim}/{folder}'
        try:
            entries = sorted(await afc_client.listdir(folder_path))
        except Exception:
            continue

        for filename in entries:
            ext = Path(filename).suffix.lower()
            if ext not in MEDIA_EXTS:
                continue

            file_path = f'{folder_path}/{filename}'
            try:
                stat = await afc_client.stat(file_path)
                size = int(stat.get('st_size', 0) or 0)
                mtime_raw = stat.get('st_mtime', 0)
                # v9+: st_mtime is a datetime; older: it's an int unix timestamp
                if hasattr(mtime_raw, 'timestamp'):
                    mtime = int(mtime_raw.timestamp())
                else:
                    mtime = int(mtime_raw or 0)
                files.append({
                    'path': file_path,
                    'filename': filename,
                    'folder': folder,
                    'size': size,
                    'size_mb': round(size / (1024 * 1024), 2),
                    'mtime': mtime,
                    'type': 'video' if ext in VIDEO_EXTS else 'image',
                    'ext': ext,
                })
            except Exception:
                pass

    return files


# ── thumbnail ─────────────────────────────────────────────────────────────────

async def get_thumbnail_bytes(afc_client, file_path, max_bytes=10 * 1024 * 1024):
    """
    Read up to *max_bytes* of an image file for thumbnail generation.
    Default 10 MB is enough for any iPhone photo/HEIC.
    Returns raw bytes or None on failure.
    """
    try:
        handle = await afc_client.fopen(file_path, 'r')
        try:
            return await afc_client.fread(handle, max_bytes)
        finally:
            await afc_client.fclose(handle)
    except Exception as e:
        logger.debug(f"Thumbnail read failed for {file_path}: {e}")
        return None


# ── transfer ──────────────────────────────────────────────────────────────────

async def transfer_files(afc_client, file_list, destination,
                         already_transferred=None, progress_cb=None):
    """
    Copy selected files from iPhone to *destination* folder.

    Parameters
    ----------
    afc_client          : open AfcService instance
    file_list           : list of file dicts (from list_media_files)
    destination         : local directory path (created if missing)
    already_transferred : set of device file paths already in the DB
    progress_cb         : callable(done, total, filename, status)
                          status ∈ {'copying', 'success', 'skipped', 'failed'}

    Returns
    -------
    dict with keys: success, skipped, failed  (each a list of file dicts)
    """
    if already_transferred is None:
        already_transferred = set()

    os.makedirs(destination, exist_ok=True)

    results = {'success': [], 'skipped': [], 'failed': []}
    total = len(file_list)

    for idx, finfo in enumerate(file_list):
        path = finfo['path']
        filename = finfo['filename']

        # ── already done ──────────────────────────────────────────────────
        if path in already_transferred:
            results['skipped'].append({**finfo, 'reason': 'already_transferred'})
            if progress_cb:
                progress_cb(idx + 1, total, filename, 'skipped')
            continue

        # ── resolve name collision ────────────────────────────────────────
        dest_path = _unique_dest(destination, filename, finfo.get('folder', ''))

        if progress_cb:
            progress_cb(idx + 1, total, filename, 'copying')

        try:
            await _copy_file(afc_client, path, dest_path)

            # ── verify ────────────────────────────────────────────────────
            local_size = os.path.getsize(dest_path)
            if finfo['size'] > 0 and local_size != finfo['size']:
                raise ValueError(
                    f"Size mismatch: expected {finfo['size']}, got {local_size}"
                )

            results['success'].append({**finfo, 'dest_path': dest_path})
            if progress_cb:
                progress_cb(idx + 1, total, filename, 'success')

        except Exception as e:
            logger.error(f"Transfer failed for {filename}: {e}")
            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                except OSError:
                    pass
            results['failed'].append({**finfo, 'reason': str(e)})
            if progress_cb:
                progress_cb(idx + 1, total, filename, 'failed')

    return results


async def _copy_file(afc_client, src_path, dest_path):
    handle = await afc_client.fopen(src_path, 'r')
    try:
        with open(dest_path, 'wb') as dst:
            while True:
                chunk = await afc_client.fread(handle, CHUNK_SIZE)
                if not chunk:
                    break
                dst.write(chunk)
    finally:
        await afc_client.fclose(handle)


def _unique_dest(directory, filename, folder_hint=''):
    dest = os.path.join(directory, filename)
    if not os.path.exists(dest):
        return dest
    base, ext = os.path.splitext(filename)
    suffix = f'_{folder_hint}' if folder_hint else '_dup'
    candidate = os.path.join(directory, f'{base}{suffix}{ext}')
    if not os.path.exists(candidate):
        return candidate
    n = 1
    while True:
        candidate = os.path.join(directory, f'{base}_{n}{ext}')
        if not os.path.exists(candidate):
            return candidate
        n += 1


# ── delete ────────────────────────────────────────────────────────────────────

async def delete_files(afc_client, file_paths):
    """
    Delete a list of file paths from the iPhone via AFC.

    Returns dict: success (list of paths), failed (list of {path, error})
    """
    results = {'success': [], 'failed': []}

    for path in file_paths:
        try:
            await afc_client.rm(path)
            results['success'].append(path)
        except Exception as e:
            logger.error(f"Delete failed for {path}: {e}")
            results['failed'].append({'path': path, 'error': str(e)})

    return results


# ── disk space check ──────────────────────────────────────────────────────────

def check_disk_space(destination, required_bytes):
    """
    Returns (has_space: bool, free_bytes: int).
    Falls back to (True, 0) if the check itself fails.
    """
    try:
        check_dir = destination
        while not os.path.exists(check_dir):
            check_dir = os.path.dirname(check_dir)
            if not check_dir:
                return True, 0

        _, _, free = shutil.disk_usage(check_dir)
        return free >= required_bytes, free
    except Exception:
        return True, 0
