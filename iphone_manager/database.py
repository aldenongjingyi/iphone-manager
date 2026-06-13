import sqlite3
import os
from datetime import datetime

def _default_db_path():
    data_dir = os.path.join(os.path.expanduser('~'), '.iphone_manager')
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, 'transfer_history.db')

DB_PATH = os.environ.get('IPHONE_MANAGER_DB') or _default_db_path()


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_udid TEXT NOT NULL,
                file_path TEXT NOT NULL,
                filename TEXT NOT NULL,
                destination TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                transferred_at TEXT DEFAULT (datetime('now')),
                status TEXT DEFAULT 'completed',
                deleted_from_device INTEGER DEFAULT 0
            )
        ''')
        conn.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_device_file
            ON transfers(device_udid, file_path)
        ''')
        conn.commit()


def record_transfer(device_udid, file_path, filename, destination, file_size, status='completed'):
    with get_connection() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO transfers
                (device_udid, file_path, filename, destination, file_size, transferred_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (device_udid, file_path, filename, destination, file_size,
              datetime.now().strftime('%Y-%m-%d %H:%M:%S'), status))
        conn.commit()


def mark_deleted(device_udid, file_path):
    with get_connection() as conn:
        conn.execute('''
            UPDATE transfers SET deleted_from_device = 1
            WHERE device_udid = ? AND file_path = ?
        ''', (device_udid, file_path))
        conn.commit()


def get_transferred_files(device_udid):
    """Return a set of file paths already successfully transferred for a device."""
    with get_connection() as conn:
        rows = conn.execute('''
            SELECT file_path FROM transfers
            WHERE device_udid = ? AND status = 'completed'
        ''', (device_udid,)).fetchall()
        return {row['file_path'] for row in rows}


def get_transfer_history(device_udid=None, limit=200):
    with get_connection() as conn:
        if device_udid:
            rows = conn.execute('''
                SELECT * FROM transfers WHERE device_udid = ?
                ORDER BY transferred_at DESC LIMIT ?
            ''', (device_udid, limit)).fetchall()
        else:
            rows = conn.execute('''
                SELECT * FROM transfers
                ORDER BY transferred_at DESC LIMIT ?
            ''', (limit,)).fetchall()
        return [dict(row) for row in rows]


def get_stats(device_udid=None):
    with get_connection() as conn:
        if device_udid:
            row = conn.execute('''
                SELECT COUNT(*) as total,
                       SUM(file_size) as total_bytes,
                       SUM(deleted_from_device) as deleted_count
                FROM transfers WHERE device_udid = ? AND status = 'completed'
            ''', (device_udid,)).fetchone()
        else:
            row = conn.execute('''
                SELECT COUNT(*) as total,
                       SUM(file_size) as total_bytes,
                       SUM(deleted_from_device) as deleted_count
                FROM transfers WHERE status = 'completed'
            ''').fetchone()
        return dict(row) if row else {}
