"""Gateway settings. Credentials come from the environment only — never faked
(non-negotiable 7); the Africa's Talking sandbox keys are human task H2."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_prefix="SISI_", extra="ignore"
    )

    env: str = "dev"
    database_url: str = "postgresql+psycopg://sisi:sisi_dev_pw@localhost:5432/sisi"
    redis_url: str = "redis://localhost:6379/0"
    ontology_dir: str = "../ontology"

    # USSD session state: auto = Redis when reachable, else Postgres (assumption A19)
    ussd_session_backend: str = "auto"  # auto | redis | postgres
    ussd_session_ttl_seconds: int = 300  # 5-minute resume window (spec 5.3)

    # Africa's Talking (sandbox first; production is human task H2). Empty until
    # credentials are provided — the provider refuses to send without them.
    at_username: str = ""
    at_api_key: str = ""

    # Turn.io WhatsApp (human task H4). Empty until provided.
    turn_token: str = ""


@lru_cache
def get_settings() -> GatewaySettings:
    return GatewaySettings()
