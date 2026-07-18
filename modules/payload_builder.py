import logging
from typing import Dict, Any

from config import settings

logger = logging.getLogger(__name__)

HOST_MAX   = 250
APP_MAX    = 50
FIELD_MAX  = 100
MSG_MAX    = 500
NOTES_MAX  = 1950
DESC_MAX   = 1950

URGENCY_TO_PRIORITY = {
    "1-Critical": "Critical",
    "2-High":     "High",
    "3-Medium":   "Medium",
    "4-Low":      "Low",
    "5-Very Low": "Low",
}

def _truncate(value: str, max_len: int) -> str:
    if len(value) > max_len:
        return value[:max_len - 3] + "..."
    return value

def _build_short_description(alert_source: Dict[str, Any]) -> str:
    message = str(alert_source.get("message", "")).replace("\n", " ").replace("\r", " ").strip()
    result = message if message else "No description"
    return _truncate(result, DESC_MAX)

def _build_incident_notes(alert_source: Dict[str, Any], normalized_fields: Dict[str, Any] = None) -> str:
    lines = []

    message = str(alert_source.get("message", "")).replace("\n", " ").replace("\r", " ").strip()
    lines.append(f"message : {_truncate(message, MSG_MAX)}")

    lines.append(f"severity : {str(alert_source.get('severity', ''))[:10]}")
    lines.append(f"host name : {_truncate(str(alert_source.get('host.name', '')), HOST_MAX)}")

    cat1 = alert_source.get("category 1") or alert_source.get("category_1", "")
    cat2 = alert_source.get("category 2") or alert_source.get("category_2", "")
    lines.append(f"Category 1 : {_truncate(str(cat1), FIELD_MAX) if cat1 else ''}")
    lines.append(f"Category 2 : {_truncate(str(cat2), FIELD_MAX) if cat2 else ''}")

    lines.append(f"rule_id : {_truncate(str(alert_source.get('rule_id', '')), FIELD_MAX)}")
    lines.append(f"application : {_truncate(str(alert_source.get('application.name', '')), APP_MAX)}")
    lines.append(f"environment : {_truncate(str(alert_source.get('application_env', '')), FIELD_MAX)}")

    raw_ag = str(alert_source.get("assignment_group", "")).strip() or "(missing)"
    used_ag = (normalized_fields or {}).get("AssignedGroup", raw_ag)
    lines.append(f"assignment_group (received) : {_truncate(raw_ag, FIELD_MAX)}")
    lines.append(f"assignment_group (used) : {_truncate(str(used_ag), FIELD_MAX)}")

    if alert_source.get("rule_name"):
        lines.append(f"rule_name : {_truncate(str(alert_source['rule_name']), FIELD_MAX)}")

    if alert_source.get("alert_timestamp"):
        lines.append(f"alert_timestamp : {str(alert_source['alert_timestamp'])[:30]}")

    if alert_source.get("link"):
        lines.append(f"link : {_truncate(str(alert_source['link']), 200)}")

    result = "\n".join(lines)
    return _truncate(result, NOTES_MAX)

def build_incident_payload(
    normalized_fields: Dict[str, Any],
    source_ticket_id:  str,
    alert_id:          str,
    environment_name:  str,
    alert_source:      Dict[str, Any] = None,
) -> Dict[str, Any]:

    if alert_source:
        short_description = _build_short_description(alert_source)
        incident_notes    = _build_incident_notes(alert_source, normalized_fields)
    else:
        short_description = normalized_fields.get("Description", "")
        incident_notes    = normalized_fields.get("Description", "")

    work_summary = normalized_fields.get("WorkInfoSummary", short_description)
    urgency      = normalized_fields.get("Urgency", settings.ITSM_URGENCY_LOW)
    priority     = URGENCY_TO_PRIORITY.get(urgency, "Medium")

    values = {
        "Operation":                 "CREATE",
        "Source":                    "Observability",
        "Description":               short_description,
        "Incident Type":             settings.ITSM_INCIDENT_TYPE,
        "Impact":                    normalized_fields.get("Impact", settings.ITSM_IMPACT_LOW),
        "Urgency":                   urgency,
        "Priority":                  priority,
        "Direct Contact First Name": settings.ITSM_DIRECT_CONTACT_FIRST,
        "Direct Contact Last Name":  settings.ITSM_DIRECT_CONTACT_LAST,
        "Incident Notes":            incident_notes,
        "Work Info Summary":         _truncate(work_summary, FIELD_MAX),
        "Work Log Type":             settings.ITSM_WORK_LOG_TYPE,
        "Worklog Notes":             _truncate(work_summary, FIELD_MAX),
        "TSM_ServiceAffectingINC":   settings.ITSM_TSM_SERVICE_AFFECTING,
        "View Access":               settings.ITSM_VIEW_ACCESS,
        "Secure Work Log":           settings.ITSM_SECURE_WORK_LOG,
    }

    if normalized_fields.get("AssignedGroup"):
        values["Assigned Group"] = normalized_fields["AssignedGroup"]

    values = {k: v for k, v in values.items() if v != "" and v is not None}

    payload = {"values": values}

    logger.debug(
        "ITSM payload built",
        extra={
            "source_ticket_id":      source_ticket_id,
            "alert_id":              alert_id,
            "environment":           environment_name,
            "impact":                values.get("Impact"),
            "urgency":               values.get("Urgency"),
            "priority":              values.get("Priority"),
            "short_description_len": len(short_description),
            "incident_notes_len":    len(incident_notes),
        }
    )

    return payload
