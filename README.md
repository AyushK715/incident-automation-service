# Incident Automation Service

A fault-tolerant **Python service that monitors Elasticsearch alerts and automatically creates ITSM incidents** through an OAuth2-secured API gateway. Built for high-availability, multi-cloud observability pipelines where every valid alert must reliably become a tracked incident.

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![Elasticsearch](https://img.shields.io/badge/Elasticsearch-alerts-005571?logo=elasticsearch&logoColor=white)
![OAuth2](https://img.shields.io/badge/Auth-OAuth2%2FOIDC-green)
![Docker](https://img.shields.io/badge/Docker-ECS%20ready-2496ED?logo=docker&logoColor=white)

> This is a **generalized, portfolio version** of a production incident-automation platform I built. All organization-specific names, endpoints, credentials, and internal identifiers have been replaced with generic placeholders.

## What it does

```
 ┌──────────────┐    poll     ┌────────────────────┐   OAuth2 + REST   ┌──────────────┐
 │ Elasticsearch│ ──────────► │  Alert Processor   │ ────────────────► │  ITSM API    │
 │   (alerts)   │             │  (2-loop engine)   │                   │   Gateway    │
 └──────────────┘ ◄────────── └────────────────────┘                   └──────────────┘
        write-back: incident_id, in_flight, retry_count, status
```

The service continuously polls an Elasticsearch index for alerts, validates and normalizes them, builds an incident payload, and submits it to an ITSM API gateway over an OAuth2 client-credentials flow. It writes the resulting incident ID back to the alert so work is never duplicated.

## Key features

- **Two-loop processing engine**
  - *Loop 1 — in-flight recovery:* reclaims alerts left mid-processing by a crashed cycle, guaranteeing no alert is lost.
  - *Loop 2 — main processing:* picks up new alerts within a configurable time window and drives them to incident creation.
- **Idempotent incident creation** — a deterministic `SourceTicketID` lets the gateway detect duplicate submissions, so retries never create double incidents.
- **Fault-tolerant retry strategy** — distinguishes connectivity errors, transient gateway errors, and permanent data-rejection errors, applying different backoff delays to each. Valid alerts are retried until they succeed; only genuinely bad data is marked rejected.
- **OAuth2 token management** — client-credentials flow with in-memory token caching and automatic refresh before expiry.
- **Crash-safe** — retries the Elasticsearch connection on startup instead of exiting, and never dies on a single bad cycle.
- **Structured JSON logging** — one file per day with configurable retention, designed for an Elastic Agent sidecar in ECS.
- **Container-native** — ships as a Docker image intended for AWS ECS Fargate.

## Architecture

```
config/
├── settings.py          # All configuration from environment variables
└── logging_config.py    # JSON logging, daily rotation, retention cleanup
core/
├── elasticsearch_client.py  # Alert querying + write-back (proxy-aware)
├── itsm_client.py           # OAuth2 auth + incident submission to the gateway
└── alert_processor.py       # Two-loop orchestration engine
modules/
├── validator.py         # Mandatory-field validation
├── normalizer.py        # Severity → impact/urgency mapping, field defaults
└── payload_builder.py   # Assembles the ITSM incident payload
utils/
├── source_ticket_id.py  # Deterministic dedup key
├── retry.py             # Exponential-backoff decorator
└── time_utils.py        # ISO timestamps + retry-delay checks
main.py                  # Entry point: startup checks + polling loop
```

## Reliability model

Every alert flows through a decision tree that maps each response to the right action:

| Situation | Action |
|-----------|--------|
| Connectivity error (network / gateway unreachable) | Clear in-flight, **don't** count as retry, pick up next cycle |
| Transient gateway error (throttle, 5xx, token blocked) | Retry with connectivity backoff |
| Transient ITSM business error | Retry with a shorter business backoff |
| Permanent rejection (bad field value/format) | Mark rejected — data must be fixed |
| Success | Write incident ID back, done |
| Missing mandatory field | Mark invalid |

The guiding principle: **a valid alert always eventually becomes an incident** — infrastructure hiccups never cause permanent loss.

## Running locally

```bash
git clone https://github.com/AyushK715/incident-automation-service.git
cd incident-automation-service
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in your Elasticsearch + gateway values
python3 main.py
```

Or with Docker:

```bash
docker build -t incident-automation-service .
docker run --env-file .env incident-automation-service
```

## Configuration

All settings come from environment variables (see `.env.example`). Highlights:

| Variable | Purpose |
|----------|---------|
| `ES_HOST`, `ES_USER`, `ES_PASSWORD`, `ES_INDEX` | Elasticsearch connection |
| `APIGW_TOKEN_URL`, `APIGW_URL` | OAuth2 token endpoint + incident endpoint |
| `APIGW_CLIENT_ID`, `APIGW_CLIENT_SECRET` | OAuth2 client credentials |
| `MAX_RETRIES`, `RETRY_DELAY_SECONDS` | Retry tuning |
| `ALERT_CUTOFF_HOURS`, `POLL_INTERVAL_SECONDS`, `BATCH_SIZE` | Polling behavior |

## Tech

Python 3.11 · Elasticsearch · OAuth2 (client credentials) · Requests · Docker · AWS ECS Fargate

---

*Built by [Ayush Kumar](https://linkedin.com/in/ayushkumar715) — Backend Engineer (Python)*
