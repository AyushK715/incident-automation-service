from config import settings

def generate_source_ticket_id(alert_id: str) -> str:
    return f"alerts-{alert_id}"
