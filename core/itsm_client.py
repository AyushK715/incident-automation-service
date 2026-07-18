import base64
import json
import logging
import time
from typing import Dict, Any, Optional, Tuple

import requests
from requests.exceptions import ConnectionError, Timeout, RequestException

from config import settings
from utils.retry import retry_on_exception

logger = logging.getLogger(__name__)

class ITSMClient:

    def __init__(self):
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def _get_access_token(self) -> str:
        now = time.time()

        if self._access_token and now < (self._token_expiry - 60):
            return self._access_token

        logger.info("Fetching new OAuth2 token from IAM")

        try:
            credentials = base64.b64encode(
                f"{settings.APIGW_CLIENT_ID}:{settings.APIGW_CLIENT_SECRET}".encode("utf-8")
            ).decode("utf-8")

            response = self.session.post(
                url=settings.APIGW_TOKEN_URL,
                data="grant_type=client_credentials",
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type":  "application/x-www-form-urlencoded",
                },
                timeout=15,
                verify=True,
                proxies=settings.PROXIES,
            )
            response.raise_for_status()
            token_data = response.json()

            self._access_token = token_data["access_token"]
            expires_in         = token_data.get("expires_in", 3600)
            self._token_expiry = now + expires_in

            logger.info(
                "OAuth2 token acquired successfully",
                extra={
                    "expires_in": expires_in,
                    "scope":      token_data.get("scope", ""),
                    "token_url":  settings.APIGW_TOKEN_URL,
                    "client_id":  settings.APIGW_CLIENT_ID,
                }
            )
            return self._access_token

        except Exception as exc:
            logger.error(
                "Failed to acquire OAuth2 token",
                extra={
                    "error":     str(exc),
                    "token_url": settings.APIGW_TOKEN_URL,
                    "client_id": settings.APIGW_CLIENT_ID,
                }
            )
            raise

    def _get_auth_headers(self) -> Dict[str, str]:
        token = self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
        }

    def check_connectivity(self) -> bool:
        all_ok = True

        logger.info(
            "Connectivity check — IAM token endpoint",
            extra={"token_url": settings.APIGW_TOKEN_URL, "client_id": settings.APIGW_CLIENT_ID}
        )
        try:
            token = self._get_access_token()
            if token:
                logger.info(
                    "✅ IAM connected — OAuth2 token acquired",
                    extra={
                        "token_url": settings.APIGW_TOKEN_URL,
                        "client_id": settings.APIGW_CLIENT_ID,
                        "status":    "connected",
                    }
                )
            else:
                raise ValueError("Empty token returned")

        except Exception as exc:
            logger.error(
                "❌ IAM connection FAILED — cannot acquire token",
                extra={
                    "token_url": settings.APIGW_TOKEN_URL,
                    "client_id": settings.APIGW_CLIENT_ID,
                    "error":     str(exc),
                    "status":    "failed",
                }
            )
            all_ok = False

        logger.info(
            "Connectivity check — API Gateway",
            extra={"apigw_url": settings.APIGW_URL}
        )
        try:

            from urllib.parse import urlparse
            parsed   = urlparse(settings.APIGW_URL)
            base_url = f"{parsed.scheme}://{parsed.netloc}"

            resp = self.session.get(
                url=base_url,
                timeout=10,
                proxies=settings.PROXIES,
                verify=True,
            )

            logger.info(
                "✅ API Gateway connected",
                extra={
                    "apigw_host":  parsed.netloc,
                    "http_status": resp.status_code,
                    "status":      "connected",
                }
            )
        except Exception as exc:
            logger.error(
                "❌ API Gateway connection FAILED",
                extra={
                    "apigw_url": settings.APIGW_URL,
                    "error":     str(exc),
                    "status":    "failed",
                }
            )
            all_ok = False

        return all_ok

    @retry_on_exception(
        max_attempts=3,
        delay_seconds=2.0,
        backoff_factor=2.0,
        exceptions=(ConnectionError, Timeout),
    )
    def create_incident(
        self, payload: Dict[str, Any]
    ) -> Tuple[int, str, Optional[str], Optional[str]]:
        try:
            headers = self._get_auth_headers()

            response = self.session.post(
                url=settings.APIGW_URL,
                json=payload,
                headers=headers,
                timeout=30,
                proxies=settings.PROXIES,
            )

            status_code      = response.status_code
            body_raw         = response.text
            incident_id      = self._extract_incident_id(response)
            apigw_error_code = self._extract_apigw_error_code(body_raw)
            activity_id      = response.headers.get("activityId", "")

            logger.info(
                "APIGW response received",
                extra={
                    "http_status":      status_code,
                    "incident_id":      incident_id,
                    "apigw_error_code": apigw_error_code,
                    "activity_id":      activity_id,
                    "location":         response.headers.get("Location", ""),
                }
            )

            return status_code, body_raw, incident_id, apigw_error_code

        except (ConnectionError, Timeout) as exc:
            logger.warning("Network error calling APIGW (will retry)", extra={"error": str(exc)})
            raise
        except RequestException as exc:
            logger.error("Non-retriable request error", extra={"error": str(exc)})
            return 503, str(exc), None, None
        except Exception as exc:
            logger.error("Unexpected error", extra={"error": str(exc)})
            return 500, str(exc), None, None

    def query_incident_by_source_ticket_id(
        self, source_ticket_id: str
    ) -> Optional[str]:
        try:
            headers = self._get_auth_headers()
            response = self.session.get(
                url=settings.APIGW_QUERY_URL,
                params={"q": f"'SourceTicketID'=\"{source_ticket_id}\""},
                headers=headers,
                timeout=15,
                proxies=settings.PROXIES,
            )

            if response.status_code == 403:
                apigw_code = self._extract_apigw_error_code(response.text)
                logger.warning(
                    "Loop 1: Query endpoint not yet subscribed in DevPortal (403) — "
                    "skipping query, Loop 2 will retry alert",
                    extra={
                        "source_ticket_id": source_ticket_id,
                        "apigw_error_code": apigw_code,
                        "query_url":        settings.APIGW_QUERY_URL,
                        "action":           "Subscribe TSM_INI_Details API in DevPortal to enable Loop 1",
                    }
                )
                return None

            if response.status_code == 200:
                incident_id = self._extract_incident_id(response)
                if incident_id:
                    logger.info(
                        "Loop 1: Existing incident found in ITSM",
                        extra={"source_ticket_id": source_ticket_id, "incident_id": incident_id}
                    )
                    return str(incident_id)

            logger.warning(
                "Loop 1: Query returned no incident",
                extra={
                    "source_ticket_id": source_ticket_id,
                    "http_status":      response.status_code,
                }
            )
            return None

        except Exception as exc:
            logger.error(
                "Loop 1: Error querying ITSM — returning None safely",
                extra={"source_ticket_id": source_ticket_id, "error": str(exc)}
            )
            return None

    def _extract_incident_id(self, response: requests.Response) -> Optional[str]:

        try:
            content_type = response.headers.get("Content-Type", "")
            if "json" in content_type.lower():
                data = response.json()
                if isinstance(data, list):
                    data = data[0] if data else {}
                if isinstance(data.get("values"), dict):
                    vals = data["values"]
                    incident_id = (
                        vals.get("Incident_Number")
                        or vals.get("Incident Number")
                        or vals.get("Request ID")
                    )
                    if incident_id:
                        return str(incident_id)
        except Exception:
            pass

        location = response.headers.get("Location", "")
        if location:
            incident_id = location.rstrip("/").split("/")[-1]
            if incident_id and (incident_id.startswith("INC") or incident_id.startswith("GI")):
                return incident_id

        logger.warning(
            "Could not extract incident ID",
            extra={
                "location_header": location,
                "content_type":    response.headers.get("Content-Type", ""),
                "status_code":     response.status_code,
            }
        )
        return None

    def _extract_apigw_error_code(self, body_raw: str) -> Optional[str]:
        if not body_raw:
            return None
        try:
            data = json.loads(body_raw)
            code = data.get("code") or data.get("fault", {}).get("code")
            return str(code) if code else None
        except (json.JSONDecodeError, AttributeError):
            return None
