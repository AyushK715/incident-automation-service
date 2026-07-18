import logging
from typing import Any, Optional
import json

from core.elasticsearch_client import ElasticsearchClient
from core.itsm_client import ITSMClient
from modules.validator import validate_alert, build_invalid_update
from modules.normalizer import normalize_alert
from modules.payload_builder import build_incident_payload
from utils.source_ticket_id import generate_source_ticket_id
from utils.time_utils import now_iso, is_retry_delay_passed
from config import settings

logger = logging.getLogger(__name__)

TSM_SUCCESS_CODES = {
    "100300",
    "10312",
    "100400",
    "100402",
    "100318",
    "100",
}

TSM_WARNING_CODES = {
    "100306",
    "100307",

}

TSM_PERMANENT_CODES = {
    "10313",
    "10314",
    "10315",
    "10316",
    "1631235",
    "1291205",
    "1291220",
    "100403",
    "100500",
    "101502",
    "101500",
    "102511",
    "1291053",
}

TSM_RETRY_CODES = {
    "10310",
    "100302",
    "100301",
    "10311",
    "100501",
}

APIGW_CONNECTIVITY_CODES = {
    "900900",
    "900907",
    "900800", "900801", "900802", "900803",
    "900804", "900805", "900806", "900807",
    "700700",
}

class AlertProcessor:

    def __init__(
        self,
        es_client:    ElasticsearchClient,
        itsm_client: ITSMClient,
    ):
        self.es    = es_client
        self.itsm = itsm_client

        self.stats = {
            "alerts_processed":    0,
            "incidents_created":   0,
            "validation_errors":   0,
            "connection_errors":   0,
            "retry_attempts":      0,
            "permanent_failures":  0,
            "max_retries_reached": 0,
        }

    def run_once(self) -> dict:
        self.stats = {k: 0 for k in self.stats}
        logger.info(
            "=== Processing cycle started ===",
            extra={"cycle_stats_keys": list(self.stats.keys())}
        )

        self._run_loop1_inflight_recovery()
        self._run_loop2_main_processing()

        logger.info(
            "=== Processing cycle complete ===",
            extra={"stats": self.stats}
        )
        return self.stats

    def _run_loop1_inflight_recovery(self) -> None:
        inflight_alerts = self.es.get_inflight_alerts()

        if not inflight_alerts:
            logger.info("Loop 1: No in-flight alerts found")
            return

        logger.info(f"Loop 1: Found {len(inflight_alerts)} in-flight alert(s)")

        for alert in inflight_alerts:
            alert_id         = alert["_id"]
            document_id      = alert_id
            source_ticket_id = generate_source_ticket_id(alert_id)

            logger.info(
                "Loop 1: Checking ITSM for in-flight alert",
                extra={"alert_id": alert_id, "document_id": document_id, "source_ticket_id": source_ticket_id}
            )

            try:
                existing_incident_id = self.itsm.query_incident_by_source_ticket_id(
                    source_ticket_id
                )

                if existing_incident_id:
                    logger.info(
                        "Loop 1: Incident found — updating alert",
                        extra={"alert_id": alert_id, "document_id": document_id, "incident_id": existing_incident_id}
                    )
                    self.es.update_alert(
                        alert_id,
                        {
                            "doc": {
                                "itsm": {
                                    "incident_id": existing_incident_id,
                                    "in_flight":   False,
                                    "ingested":    now_iso(),
                                },
                                "error": {"message": "", "type": ""}
                            }
                        }
                    )
                    self.stats["incidents_created"] += 1
                else:
                    logger.info(
                        "Loop 1: No incident in ITSM — clearing in_flight for retry",
                        extra={"alert_id": alert_id, "document_id": document_id}
                    )
                    self.es.set_inflight(alert_id, False)

            except Exception as exc:
                logger.error(
                    "Loop 1: Unexpected error — clearing in_flight",
                    extra={"alert_id": alert_id, "document_id": document_id, "error": str(exc)}
                )
                self.es.update_alert(
                    alert_id,
                    {
                        "doc": {
                            "itsm": {"in_flight": False, "ingested": now_iso()},
                            "error": {"message": str(exc), "type": type(exc).__name__}
                        }
                    }
                )

    def _run_loop2_main_processing(self) -> None:
        pending_alerts = self.es.get_pending_alerts()

        if not pending_alerts:
            logger.info("Loop 2: No pending alerts")
            return

        logger.info(
            f"Loop 2: Processing {len(pending_alerts)} pending alert(s)",
            extra={"alert_ids": [a["_id"] for a in pending_alerts]}
        )

        for alert in pending_alerts:
            alert_id = alert["_id"]
            document_id = alert_id
            source   = alert["_source"]
            self.stats["alerts_processed"] += 1

            logger.info(
                "Loop 2: Now processing alert",
                extra={
                    "alert_id":         alert_id,
                    "document_id":      document_id,
                    "rule_id":          source.get("rule_id", "(missing)"),
                    "assignment_group_received": source.get("assignment_group", "(missing)"),
                }
            )

            current_retry = source.get("itsm", {}).get("retry", 0) or 0
            if current_retry >= settings.MAX_RETRIES:
                logger.warning(
                    "Loop 2: Max retries reached — marking as maxretriesreached",
                    extra={
                        "alert_id":    alert_id,
                        "document_id": document_id,
                        "retry_count": current_retry,
                        "max_retries": settings.MAX_RETRIES,
                    }
                )
                self.stats["permanent_failures"] += 1
                self.stats["max_retries_reached"] += 1
                self.es.update_alert(
                    alert_id,
                    {
                        "doc": {
                            "itsm": {
                                "incident_id": "maxretriesreached",
                                "in_flight":   False,
                                "ingested":    now_iso(),
                            },
                            "error": {
                                "message": f"Max retries ({settings.MAX_RETRIES}) reached",
                                "type":    "MaxRetriesReached",
                            }
                        }
                    }
                )
                continue

            ingested_ts  = source.get("itsm", {}).get("ingested")
            last_err     = str(source.get("itsm", {}).get("error_code", "") or "")

            if last_err and last_err in TSM_RETRY_CODES:
                delay_s = settings.RETRY_DELAY_TSM_SECONDS
            else:
                delay_s = settings.RETRY_DELAY_SECONDS
            if ingested_ts and not is_retry_delay_passed(ingested_ts, delay_s):
                logger.info(
                    "Loop 2: Skipping — retry delay not yet passed",
                    extra={
                        "alert_id":   alert_id,
                        "document_id": document_id,
                        "ingested":   ingested_ts,
                        "delay_s":    delay_s,
                        "error_code": last_err,
                    }
                )
                continue

            if not self.es.set_inflight(alert_id, True):
                logger.warning(
                    "Loop 2: Could not set in_flight — skipping",
                    extra={"alert_id": alert_id, "document_id": document_id}
                )
                continue

            is_valid, missing_mandatory, missing_optional = validate_alert(source)
            if not is_valid:
                logger.warning(
                    "Loop 2: Validation failed — marking invalid",
                    extra={
                        "alert_id": alert_id,
                        "document_id": document_id,
                        "missing": missing_mandatory,
                        "rule_id": source.get("rule_id", "(missing)"),
                    }
                )
                self.stats["validation_errors"] += 1
                self.es.update_alert(
                    alert_id,
                    build_invalid_update(missing_mandatory, missing_optional)
                )
                continue

            source_ticket_id = generate_source_ticket_id(alert_id)
            normalized       = normalize_alert(source)
            payload          = build_incident_payload(
                normalized, source_ticket_id, alert_id, settings.ENVIRONMENT_NAME,
                alert_source=source
            )

            self._call_itsm_and_update(
                alert_id=alert_id,
                source=source,
                payload=payload,
                missing_optional=missing_optional,
                normalized=normalized,
            )

    def _call_itsm_and_update(
        self,
        alert_id:         str,
        source:           dict,
        payload:          dict,
        missing_optional: list,
        normalized:       dict = None,
    ) -> None:
        current_retry = source.get("itsm", {}).get("retry", 0) or 0
        document_id = alert_id
        normalized = normalized or {}

        try:
            http_status, body_raw, incident_id, apigw_error_code =\
                self.itsm.create_incident(payload)

        except Exception as exc:

            self.stats["connection_errors"] += 1
            logger.warning(
                "Connection error during APIGW call — will retry next cycle",
                extra={
                    "alert_id":   alert_id,
                    "document_id": document_id,
                    "error":      str(exc),
                    "error_type": type(exc).__name__,
                    "action":     "retry_next_cycle — retry counter NOT incremented",
                }
            )
            self.es.update_alert(
                alert_id,
                {
                    "doc": {
                        "itsm": {
                            "in_flight": False,
                            "ingested":  now_iso(),
                        },
                        "error": {
                            "message": str(exc),
                            "type":    type(exc).__name__,
                        }
                    }
                }
            )
            return

        tsm_body_code = self._extract_tsm_body_code(body_raw)

        outcome = self._classify_outcome(http_status, apigw_error_code, tsm_body_code, incident_id)

        if outcome == "success":
            logger.info(
                "Incident created successfully",
                extra={
                    "alert_id":                   alert_id,
                    "document_id":                document_id,
                    "incident_id":                incident_id,
                    "http_status":                http_status,
                    "tsm_body_code":               tsm_body_code,
                    "assignment_group_received":  source.get("assignment_group", "(missing)"),
                    "assignment_group_used":       normalized.get("AssignedGroup", ""),
                    "rule_id":                     source.get("rule_id", "(missing)"),
                    "severity":                    source.get("severity", ""),
                    "alert_message":               str(source.get("message", ""))[:100],
                    "host_name":                   source.get("host.name", ""),
                }
            )
            self.stats["incidents_created"] += 1

            optional_note = (
                f"Missing optional fields: {', '.join(missing_optional)}"
                if missing_optional else ""
            )

            self.es.update_alert(
                alert_id,
                {
                    "doc": {
                        "http": {
                            "response": {
                                "status_code": http_status,
                                "body":        {"content": body_raw}
                            }
                        },
                        "itsm": {
                            "incident_id": incident_id,
                            "error_code":  apigw_error_code or tsm_body_code or "",
                            "ingested":    now_iso(),
                        },
                        "error": {"message": optional_note, "type": ""}
                    }
                }
            )

            self.es.update_alert(
                alert_id,
                {"doc": {"itsm": {"in_flight": False}}}
            )

        elif outcome == "permanent":
            logger.error(
                "Permanent failure — TSM rejected alert field values — marking as rejected",
                extra={
                    "alert_id":                   alert_id,
                    "document_id":                document_id,
                    "http_status":                http_status,
                    "apigw_error_code":            apigw_error_code,
                    "tsm_body_code":               tsm_body_code,
                    "assignment_group_received":  source.get("assignment_group", "(missing)"),
                    "assignment_group_used":       normalized.get("AssignedGroup", ""),
                    "body_preview":                body_raw[:200],
                    "note":                        "Alert field values must be fixed to retry",
                }
            )
            self.stats["permanent_failures"] += 1

            self.es.update_alert(
                alert_id,
                {
                    "doc": {
                        "http": {
                            "response": {
                                "status_code": http_status,
                                "body":        {"content": body_raw}
                            }
                        },
                        "itsm": {
                            "incident_id": "rejected",
                            "error_code":  apigw_error_code or tsm_body_code or "",
                            "in_flight":   False,
                            "ingested":    now_iso(),
                        },
                        "error": {"message": "", "type": ""}
                    }
                }
            )

        else:
            new_retry_count = current_retry + 1
            self.stats["retry_attempts"] += 1

            err_code = apigw_error_code or tsm_body_code or ""
            if err_code and err_code in TSM_RETRY_CODES:
                retry_delay = settings.RETRY_DELAY_TSM_SECONDS
                delay_reason = "TSM business error"
            else:
                retry_delay = settings.RETRY_DELAY_SECONDS
                delay_reason = "connectivity/unknown error"

            logger.warning(
                "Transient failure — will retry after delay",
                extra={
                    "alert_id":         alert_id,
                    "document_id":      document_id,
                    "http_status":      http_status,
                    "apigw_error_code": apigw_error_code,
                    "tsm_body_code":    tsm_body_code,
                    "retry_count":      new_retry_count,
                    "retry_delay_s":    retry_delay,
                    "delay_reason":     delay_reason,
                }
            )

            self.es.update_alert(
                alert_id,
                {
                    "doc": {
                        "http": {
                            "response": {
                                "status_code": http_status,
                                "body":        {"content": body_raw}
                            }
                        },
                        "itsm": {
                            "retry":      new_retry_count,
                            "error_code": apigw_error_code or tsm_body_code or "",
                            "in_flight":  False,
                            "ingested":   now_iso(),
                        },
                        "error": {"type": ""}
                    }
                }
            )

    def _classify_outcome(
        self,
        http_status:      int,
        apigw_error_code: Optional[str],
        tsm_body_code:    Optional[str],
        incident_id:      Optional[str],
    ) -> str:

        if tsm_body_code:
            if tsm_body_code in TSM_SUCCESS_CODES or tsm_body_code in TSM_WARNING_CODES:
                if incident_id:
                    return "success"

                logger.warning(
                    f"TSM success code {tsm_body_code} but no incident_id extracted — retrying"
                )
                return "retry"
            if tsm_body_code in TSM_PERMANENT_CODES:
                return "permanent"
            if tsm_body_code in TSM_RETRY_CODES:
                return "retry"

        if http_status in settings.SUCCESS_HTTP_CODES and incident_id:
            return "success"

        if apigw_error_code:
            if apigw_error_code in settings.PERMANENT_APIGW_CODES:
                return "permanent"
            if apigw_error_code in settings.RETRY_APIGW_CODES:
                return "retry"

        if http_status in settings.SUCCESS_HTTP_CODES:

            return "retry"
        if http_status in settings.PERMANENT_HTTP_CODES:
            return "permanent"
        if http_status in settings.RETRY_HTTP_CODES:
            return "retry"

        if http_status in {401, 403}:
            return "retry"

        logger.warning(
            f"Unknown outcome: HTTP {http_status} / APIGW {apigw_error_code} / "
            f"TSM {tsm_body_code} — treating as transient"
        )
        return "retry"

    def _extract_tsm_body_code(self, body_raw: str) -> Optional[str]:
        if not body_raw:
            return None
        try:
            data = json.loads(body_raw)
            if isinstance(data, list):
                data = data[0] if data else {}
            values = data.get("values", {})
            if isinstance(values, dict):
                code = values.get("Error_Code")
                if code is not None:
                    return str(int(code))
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
        return None
