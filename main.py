import time
import logging

from config.logging_config import setup_logging
from config import settings
from core.elasticsearch_client import ElasticsearchClient
from core.itsm_client import ITSMClient
from core.alert_processor import AlertProcessor

setup_logging(level="INFO")
logger = logging.getLogger(__name__)

def run_startup_checks(es_client, itsm_client):
    logger.info("=" * 60)
    logger.info("ITSM INTEGRATION SERVICE — STARTUP CONNECTIVITY CHECKS")
    logger.info("=" * 60)
    logger.info(
        "Service configuration",
        extra={
            "environment":   settings.ENVIRONMENT_NAME,
            "es_host":       settings.ES_HOST,
            "es_index":      settings.ES_INDEX,
            "token_url":     settings.APIGW_TOKEN_URL,
            "apigw_url":     settings.APIGW_URL,
            "poll_interval": settings.POLL_INTERVAL_SECONDS,
            "cutoff_hours":  settings.ALERT_CUTOFF_HOURS,
            "batch_size":    settings.BATCH_SIZE,
        }
    )

    es_ok     = es_client.check_connectivity()
    itsm_ok  = itsm_client.check_connectivity()

    logger.info("=" * 60)
    if es_ok and itsm_ok:
        logger.info(
            "All connectivity checks passed — service is ready",
            extra={"elasticsearch": "connected", "iam": "connected", "apigw": "connected"}
        )
    else:
        logger.warning(
            "Some connectivity checks failed — service starting anyway",
            extra={
                "elasticsearch": "connected" if es_ok    else "FAILED",
                "itsm_apigw":   "connected" if itsm_ok else "FAILED",
            }
        )
    logger.info("=" * 60)

def main():
    logger.info(
        "ITSM Integration Service starting",
        extra={
            "environment":   settings.ENVIRONMENT_NAME,
            "poll_interval": settings.POLL_INTERVAL_SECONDS,
            "cutoff_hours":  settings.ALERT_CUTOFF_HOURS,
            "es_index":      settings.ES_INDEX,
        }
    )

    es_client = None
    while es_client is None:
        try:
            es_client = ElasticsearchClient()
        except Exception as exc:
            logger.warning(
                "Elasticsearch not reachable — retrying in 30 seconds",
                extra={"error": str(exc)}
            )
            time.sleep(30)

    itsm_client = ITSMClient()
    run_startup_checks(es_client, itsm_client)

    processor = AlertProcessor(
        es_client=es_client,
        itsm_client=itsm_client,
    )

    logger.info("Entering main polling loop")

    while True:
        try:
            stats = processor.run_once()
            logger.info(
                "Polling cycle complete",
                extra={
                    "alerts_processed":    stats["alerts_processed"],
                    "incidents_created":   stats["incidents_created"],
                    "validation_errors":   stats["validation_errors"],
                    "retry_attempts":      stats["retry_attempts"],
                    "permanent_failures":  stats["permanent_failures"],
                    "max_retries_reached": stats.get("max_retries_reached", 0),
                }
            )

        except KeyboardInterrupt:
            logger.info("Shutdown signal received — exiting cleanly")
            break

        except Exception as exc:
            logger.error(
                "Unhandled exception in polling cycle — continuing",
                extra={"error": str(exc), "error_type": type(exc).__name__}
            )

        logger.info("Sleeping %ss before next cycle", settings.POLL_INTERVAL_SECONDS)
        time.sleep(settings.POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
