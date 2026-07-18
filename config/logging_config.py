import logging
import json
import os
import glob
import time
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler

LOG_DIR          = "/shared-logs"
FALLBACK_LOG_DIR = "incident_logs"
RETENTION_DAYS   = 10

class SafeLogger(logging.Logger):
    def makeRecord(self, name, level, fn, lno, msg, args, exc_info,
                   func=None, extra=None, sinfo=None):
        if extra is not None and not isinstance(extra, dict):
            extra = {"_extra": str(extra)}
        return super().makeRecord(name, level, fn, lno, msg, args, exc_info,
                                  func=func, extra=extra, sinfo=sinfo)

logging.setLoggerClass(SafeLogger)

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "level":       record.levelname,
            "logger":      record.name,
            "environment": os.getenv("ENVIRONMENT_NAME", "unknown"),
            "message":     record.getMessage(),
        }
        skip_keys = {
            "args", "asctime", "created", "exc_info", "exc_text",
            "filename", "funcName", "id", "levelname", "levelno",
            "lineno", "module", "msecs", "message", "msg", "name",
            "pathname", "process", "processName", "relativeCreated",
            "stack_info", "thread", "threadName", "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in skip_keys:
                if isinstance(value, (str, int, float, bool, type(None))):
                    log_entry[key] = value
                elif isinstance(value, (list, tuple)):
                    log_entry[key] = list(value)
                elif isinstance(value, set):
                    log_entry[key] = list(value)
                elif isinstance(value, dict):
                    log_entry[key] = value
                else:
                    log_entry[key] = str(value)
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)

def _cleanup_old_logs(log_dir: str, retention_days: int, env_short: str):
    cutoff = time.time() - (retention_days * 86400)
    pattern = os.path.join(log_dir, f"{env_short}*.log*")
    for f in glob.glob(pattern):
        if os.path.getmtime(f) < cutoff:
            try:
                os.remove(f)
            except OSError:
                pass

def _add_file_handler(log_dir: str, env_short: str, formatter, retention_days: int):
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{env_short}.log")
    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=retention_days,
        utc=True,
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setFormatter(formatter)
    _cleanup_old_logs(log_dir, retention_days, env_short)
    return file_handler, log_file

def setup_logging(level="INFO"):
    environment_name = os.getenv("ENVIRONMENT_NAME", "UNKNOWN")
    env_short = environment_name.replace("", "").replace("-", "_")

    log_level = getattr(logging, level.upper(), logging.INFO)
    formatter = JSONFormatter()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    handlers = [stream_handler]

    fallback_handler, fallback_log_path = _add_file_handler(
        FALLBACK_LOG_DIR, env_short, formatter, RETENTION_DAYS
    )
    handlers.append(fallback_handler)

    shared_log_path = None
    if os.path.exists(LOG_DIR):
        shared_handler, shared_log_path = _add_file_handler(
            LOG_DIR, env_short, formatter, RETENTION_DAYS
        )
        handlers.append(shared_handler)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    for h in handlers:
        root.addHandler(h)

    logging.getLogger("elasticsearch").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("elastic_transport").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info(
        "Logging initialised",
        extra={
            "stdout":           True,
            "incident_logs":    fallback_log_path,
            "shared_logs":      shared_log_path or "not available",
            "retention_days":   RETENTION_DAYS,
            "env_short":        env_short,
        }
    )
