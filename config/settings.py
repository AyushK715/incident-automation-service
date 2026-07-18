import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

ES_HOST     = os.getenv("ES_HOST",     "https://elasticsearch.example.com:9243")
ES_USER     = os.getenv("ES_USER",     "")
ES_PASSWORD = os.getenv("ES_PASSWORD", "")
ES_INDEX    = os.getenv("ES_INDEX",    "alerts_index")

HTTP_PROXY  = os.getenv("http_proxy",  "http://proxy.internal:8080")
HTTPS_PROXY = os.getenv("https_proxy", "http://proxy.internal:8080")

PROXIES = {
    "http":  HTTP_PROXY,
    "https": HTTPS_PROXY,
}

NO_PROXY = os.getenv(
    "no_proxy",
    "elasticsearch.example.com,localhost,127.0.0.1"
)

APIGW_TOKEN_URL = os.getenv(
    "APIGW_TOKEN_URL",
    "https://auth.example.com/oauth2/access_token"
)

APIGW_URL = os.getenv(
    "APIGW_URL",
    "https://apigw.example.com/gateway/api/arsys/v1/entry/TSM:GWS:INC_Incoming/v1/api/arsys/v1/entry/TSM:GWS:INC_Incoming?fields=values(Error_Status,Incident_Number,Error_Code,Error_Message)"
)

APIGW_QUERY_URL = os.getenv(
    "APIGW_QUERY_URL",
    "https://apigw.example.com/gateway/TSM_INI_Details/v1/api/arsys/v1/entry/TSM:HPD:Retrieve_Inc_Details"
)

APIGW_CLIENT_ID     = os.getenv("APIGW_CLIENT_ID",     "")
APIGW_CLIENT_SECRET = os.getenv("APIGW_CLIENT_SECRET", "")
APIGW_OAUTH_SCOPE   = os.getenv("APIGW_OAUTH_SCOPE",   "default")

CLUSTER_UUID     = os.getenv("CLUSTER_UUID",     "")
ENVIRONMENT_NAME = os.getenv("ENVIRONMENT_NAME", "")

MAX_RETRIES           = int(os.getenv("MAX_RETRIES",           "8"))
RETRY_DELAY_SECONDS        = int(os.getenv("RETRY_DELAY_SECONDS",        "900"))
RETRY_DELAY_TSM_SECONDS    = int(os.getenv("RETRY_DELAY_TSM_SECONDS",    "480"))
ALERT_CUTOFF_HOURS    = int(os.getenv("ALERT_CUTOFF_HOURS",    "48"))
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
BATCH_SIZE            = int(os.getenv("BATCH_SIZE",            "100"))

SUCCESS_HTTP_CODES  = {200, 201}
RETRY_HTTP_CODES    = {429, 500, 502, 503, 504}
PERMANENT_HTTP_CODES = {400}

RETRY_APIGW_CODES = {
    "900900", "900901", "900902", "900905", "900907",
    "900908", "900909", "900910",
    "900800", "900802", "900803", "900804", "900805", "900806", "900807",
    "700700",
    "101000", "101001", "101500", "101501", "101503", "101504",
    "101505", "101506", "101507", "101508", "101509", "101510",
    "100302", "10313", "10310",
}

PERMANENT_APIGW_CODES = {
    "10316",
    "1291053",
    "1291205",
    "102511",
}

MANDATORY_FIELDS = [
    "rule_id",
]

OPTIONAL_FIELDS = [
    "assignment_group",
    "severity",
    "message",
    "host.name",
    "category_1",
    "category_2",
    "link",
    "rule_name",
    "application.name",
    "application_env",
]

ITSM_INCIDENT_TYPE         = "User Service Restoration"
ITSM_TSM_SERVICE_AFFECTING = "Yes"
ITSM_WORK_LOG_TYPE         = "General Information"
ITSM_VIEW_ACCESS           = "Internal"
ITSM_SECURE_WORK_LOG       = "Yes"

ITSM_DIRECT_CONTACT_FIRST  = "Event"
ITSM_DIRECT_CONTACT_LAST   = "Admin"

ITSM_IMPACT_HIGH  = "2-Significant/Large"
ITSM_IMPACT_LOW   = "3-Moderate/Limited"
ITSM_URGENCY_HIGH = "1-Critical"
ITSM_URGENCY_LOW  = "2-High"

DEFAULT_ASSIGNMENT_GROUP = "OPS-DEFAULT-GROUP"

ASSIGNMENT_GROUP_OVERRIDES = {
    "VENDOR-AWS-INFRAOPS": "OPS-DEFAULT-GROUP",
    "VENDOR-AWS-INFRA":    "OPS-DEFAULT-GROUP",
}

ITSM_CATEGORY_TIER2_DEFAULT = "Server"
ITSM_CATEGORY_TIER3_DEFAULT = "Patrol"
