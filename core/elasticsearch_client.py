import logging
import requests
from typing import List, Dict, Optional

from config import settings

logger = logging.getLogger(__name__)

PROXIES = settings.PROXIES

class ElasticsearchClient:

    def __init__(self):
        self.host     = settings.ES_HOST.rstrip("/")
        self.auth     = (settings.ES_USER, settings.ES_PASSWORD)
        self.index    = settings.ES_INDEX
        self.proxies  = PROXIES
        self._connect()

    def _connect(self):
        logger.info(
            "Connecting to Elasticsearch",
            extra={"host": self.host, "user": settings.ES_USER, "index": self.index}
        )
        try:
            r = requests.get(
                self.host,
                auth=self.auth,
                proxies=self.proxies,
                verify=True,
                timeout=30,
            )
            if r.status_code != 200:
                raise ConnectionError(f"Cannot connect to Elasticsearch at {self.host} — HTTP {r.status_code}")

            info         = r.json()
            cluster_name = info.get("cluster_name", "unknown")
            es_version   = info.get("version", {}).get("number", "unknown")

            logger.info(
                "Elasticsearch connected",
                extra={
                    "host":         self.host,
                    "cluster_name": cluster_name,
                    "es_version":   es_version,
                    "index":        self.index,
                }
            )
        except requests.exceptions.RequestException as exc:
            raise ConnectionError(f"Elasticsearch connection failed: {exc}")

    def check_connectivity(self):
        logger.info("Connectivity check — Elasticsearch",
                    extra={"host": self.host, "index": self.index})
        try:
            r = requests.get(
                self.host,
                auth=self.auth,
                proxies=self.proxies,
                verify=True,
                timeout=30,
            )
            if r.status_code != 200:
                raise ConnectionError("Ping failed")

            r2 = requests.head(
                f"{self.host}/{self.index}",
                auth=self.auth,
                proxies=self.proxies,
                verify=True,
                timeout=30,
            )
            index_exists = r2.status_code == 200
            if index_exists:
                logger.info(
                    "Elasticsearch connected — index confirmed",
                    extra={"host": self.host, "index": self.index,
                           "index_exists": True, "status": "connected"}
                )
            else:
                logger.warning(
                    "Elasticsearch connected but index not found",
                    extra={"host": self.host, "index": self.index}
                )
            return True
        except Exception as exc:
            logger.error("Elasticsearch connection FAILED",
                         extra={"host": self.host, "error": str(exc), "status": "failed"})
            return False

    def get_inflight_alerts(self):
        query = {"query": {"term": {"itsm.in_flight": True}}, "size": settings.BATCH_SIZE}
        logger.info("Loop 1: Querying in-flight alerts")
        return self._execute_search(query)

    def get_pending_alerts(self, last_run_timestamp=None):
        must_clauses = [

            {"bool": {"must_not": {"exists": {"field": "itsm.incident_id"}}}},

            {
                "bool": {
                    "should": [
                        {"term": {"itsm.in_flight": False}},
                        {"bool": {"must_not": {"exists": {"field": "itsm.in_flight"}}}}
                    ],
                    "minimum_should_match": 1
                }
            },

            {"range": {"alert_timestamp": {"gte": f"now-{settings.ALERT_CUTOFF_HOURS}h"}}},

        ]

        if last_run_timestamp:
            must_clauses.append({"range": {"alert_timestamp": {"gt": last_run_timestamp}}})

        query = {
            "query": {"bool": {"must": must_clauses}},
            "sort":  [{"alert_timestamp": {"order": "asc"}}],
            "size":  settings.BATCH_SIZE,
        }
        logger.info("Loop 2: Querying pending alerts",
                    extra={"last_run_timestamp": last_run_timestamp})
        return self._execute_search(query)

    def set_inflight(self, alert_id, value):
        try:
            r = requests.post(
                f"{self.host}/{self.index}/_update/{alert_id}",
                auth=self.auth,
                proxies=self.proxies,
                verify=True,
                timeout=30,
                json={"doc": {"itsm": {"in_flight": value}}},
                params={"retry_on_conflict": 3},
            )
            if r.status_code in (200, 201):
                return True
            logger.error("Failed to set itsm.in_flight",
                         extra={"alert_id": alert_id, "value": value, "status": r.status_code})
            return False
        except Exception as exc:
            logger.error("Failed to set itsm.in_flight",
                         extra={"alert_id": alert_id, "value": value, "error": str(exc)})
            return False

    def update_alert(self, alert_id, update_body):
        try:
            r = requests.post(
                f"{self.host}/{self.index}/_update/{alert_id}",
                auth=self.auth,
                proxies=self.proxies,
                verify=True,
                timeout=30,
                json=update_body,
                params={"retry_on_conflict": 3},
            )
            if r.status_code in (200, 201):
                return True
            if r.status_code == 409:
                logger.warning("Conflict updating alert", extra={"alert_id": alert_id})
                return False
            logger.error("Failed to update alert",
                         extra={"alert_id": alert_id, "status": r.status_code, "body": r.text[:200]})
            return False
        except Exception as exc:
            logger.error("Failed to update alert",
                         extra={"alert_id": alert_id, "error": str(exc)})
            return False

    def _execute_search(self, query):
        try:
            r = requests.post(
                f"{self.host}/{self.index}/_search",
                auth=self.auth,
                proxies=self.proxies,
                verify=True,
                timeout=30,
                json=query,
            )
            if r.status_code != 200:
                logger.error("Elasticsearch query failed", extra={"status": r.status_code, "body": r.text[:200]})
                return []
            hits = r.json().get("hits", {}).get("hits", [])
            logger.info("ES query returned %s alerts", len(hits))
            return hits
        except Exception as exc:
            logger.error("Elasticsearch query failed", extra={"error": str(exc)})
            return []
