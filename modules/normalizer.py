import logging
from typing import Any, Dict

from config import settings

logger = logging.getLogger(__name__)

HOST_NAME_MAX    = 250
APP_NAME_MAX     = 50
FIELD_MAX        = 100
DESCRIPTION_MAX  = 500

def severity_to_impact_urgency(severity: Any) -> tuple:
    try:
        sev = int(str(severity).strip())
        if sev == 1:
            return settings.ITSM_IMPACT_HIGH, "1-Critical"
        elif sev == 2:
            return settings.ITSM_IMPACT_HIGH, "2-High"
        elif sev == 3:
            return settings.ITSM_IMPACT_LOW, "3-Medium"
        elif sev == 4:
            return settings.ITSM_IMPACT_LOW, "4-Low"
        elif sev == 5:
            return settings.ITSM_IMPACT_LOW, "5-Very Low"
        else:
            return settings.ITSM_IMPACT_LOW, "3-Medium"
    except (ValueError, TypeError):
        return settings.ITSM_IMPACT_LOW, "3-Medium"

def _truncate(value: str, max_len: int) -> str:
    if len(value) > max_len:
        return value[:max_len - 3] + "..."
    return value

def normalize_alert(alert_source: dict) -> Dict[str, Any]:
    normalized = {}

    message = alert_source.get("message", "")
    if message:
        normalized["Description"] = _truncate(
            str(message).replace("\n", " ").replace("\r", " ").strip(),
            DESCRIPTION_MAX
        )
    else:

        rule_id_fallback = str(alert_source.get("rule_id", "")).strip()
        normalized["Description"] = f"Alert (rule_id: {rule_id_fallback})" if rule_id_fallback else "Alert — no message provided"

    raw_assignment_group = str(alert_source.get("assignment_group", "")).strip()
    mapped_assignment_group = settings.ASSIGNMENT_GROUP_OVERRIDES.get(
        raw_assignment_group, raw_assignment_group
    )
    final_assignment_group = mapped_assignment_group or settings.DEFAULT_ASSIGNMENT_GROUP
    normalized["AssignedGroup"] = _truncate(final_assignment_group, FIELD_MAX)

    raw_severity = alert_source.get("severity", "")
    impact, urgency = severity_to_impact_urgency(raw_severity)
    normalized["Impact"]  = impact
    normalized["Urgency"] = urgency

    host_name = alert_source.get("host.name", "")
    if host_name:
        normalized["CI"] = _truncate(str(host_name).strip(), HOST_NAME_MAX)

    rule_name = alert_source.get("rule_name", "")
    if rule_name:
        normalized["WorkInfoSummary"] = _truncate(str(rule_name).strip(), FIELD_MAX)

    app_name = alert_source.get("application.name", "")
    if app_name:
        normalized["ServiceCI"] = _truncate(str(app_name).strip(), APP_NAME_MAX)

    app_env = alert_source.get("application_env", "")
    if app_env:
        normalized["AppEnv"] = _truncate(str(app_env).strip(), FIELD_MAX)

    category_1 = alert_source.get("category 1") or alert_source.get("category_1", "")
    category_2 = alert_source.get("category 2") or alert_source.get("category_2", "")
    category_1 = str(category_1).strip() or "SERVER"
    category_2 = str(category_2).strip() or "Patrol"
    normalized["Category1"] = _truncate(category_1, FIELD_MAX)
    normalized["Category2"] = _truncate(category_2, FIELD_MAX)

    link = alert_source.get("link", "")
    if link:
        normalized["Resolution"] = _truncate(str(link).strip(), 200)

    rule_id = alert_source.get("rule_id", "")
    if rule_id:
        normalized["RuleID"] = _truncate(str(rule_id).strip(), FIELD_MAX)

    return normalized
