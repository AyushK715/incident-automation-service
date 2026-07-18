from datetime import datetime, timezone, timedelta

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def now_epoch_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)

def hours_ago_iso(hours: int) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return cutoff.isoformat()

def is_within_cutoff(timestamp_str: str, cutoff_hours: int) -> bool:
    if not timestamp_str:
        return True

    try:
        alert_time = datetime.fromisoformat(timestamp_str)

        if alert_time.tzinfo is None:
            alert_time = alert_time.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=cutoff_hours)
        return alert_time >= cutoff
    except (ValueError, TypeError):
        return True

def is_retry_delay_passed(ingested_str: str, delay_seconds: int) -> bool:
    if not ingested_str:
        return True

    try:
        ingested_time = datetime.fromisoformat(ingested_str)
        if ingested_time.tzinfo is None:
            ingested_time = ingested_time.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - ingested_time).total_seconds()
        return elapsed >= delay_seconds
    except (ValueError, TypeError):
        return True
