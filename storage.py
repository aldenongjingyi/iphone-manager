import logging

logger = logging.getLogger(__name__)


def get_storage_info(lockdown_client):
    """
    Get iPhone storage information.
    Tries the disk_usage domain first, falls back to lockdown all_values.
    """
    try:
        info = lockdown_client.get_value('com.apple.disk_usage')
        if info:
            total = info.get('TotalDiskCapacity', 0)
            free = info.get('TotalSystemAvailable', 0)
            media_cache = info.get('TotalCameraRollCapacity', 0)
            used = total - free

            return {
                'total': total,
                'used': used,
                'free': free,
                'media_cache': media_cache,
                'total_gb': _to_gb(total),
                'used_gb': _to_gb(used),
                'free_gb': _to_gb(free),
                'media_cache_gb': _to_gb(media_cache),
                'used_percent': round((used / total * 100) if total > 0 else 0, 1),
            }
    except Exception as e:
        logger.debug(f"disk_usage domain failed: {e}")

    # Fallback: read from all_values
    try:
        vals = lockdown_client.all_values
        total = vals.get('TotalDiskCapacity', 0)
        free = vals.get('TotalSystemAvailable', 0)
        used = total - free
        if total > 0:
            return {
                'total': total,
                'used': used,
                'free': free,
                'media_cache': 0,
                'total_gb': _to_gb(total),
                'used_gb': _to_gb(used),
                'free_gb': _to_gb(free),
                'media_cache_gb': 0.0,
                'used_percent': round(used / total * 100, 1),
            }
    except Exception as e:
        logger.debug(f"all_values storage fallback failed: {e}")

    return None


def _to_gb(value):
    if not value:
        return 0.0
    return round(value / (1024 ** 3), 2)
