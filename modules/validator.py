import logging
from typing import Tuple, List, Dict, Any

from config import settings
from utils.time_utils import now_iso

logger = logging.getLogger(__name__)

def _get_nested_value(doc: dict, field_path: str) -> Any:

    if field_path in doc:
        return doc[field_path]

    keys    = field_path.split(".")
    current = doc
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current

def validate_alert(alert_source: dict) -> Tuple[bool, List[str], List[str]]:
    missing_mandatory = []
    missing_optional = []

    for field in settings.MANDATORY_FIELDS:
        value = _get_nested_value(alert_source, field)
        if value is None or str(value).strip() == "":
            missing_mandatory.append(field)

    for field in settings.OPTIONAL_FIELDS:
        value = _get_nested_value(alert_source, field)
        if value is None or str(value).strip() == "":
            missing_optional.append(field)

    is_valid = len(missing_mandatory) == 0
    return is_valid, missing_mandatory, missing_optional

def build_invalid_update(missing_mandatory: List[str], missing_optional: List[str]) -> Dict:
    error_parts = []
    if missing_mandatory:
        error_parts.append(f"Missing mandatory fields: {', '.join(missing_mandatory)}")
    if missing_optional:
        error_parts.append(f"Missing optional fields: {', '.join(missing_optional)}")

    return {
        "doc": {
            "itsm": {
                "incident_id": "invalid",
                "ingested": now_iso(),
                "in_flight": False,
            },
            "error": {
                "message": " | ".join(error_parts),
                "type": "ValidationError",
            }
        }
    }
