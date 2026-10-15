"""Application settings. Secrets come from the environment only (.env is gitignored);
see .env.example at the repo root. staging/prod refuse to boot with dev safety flags on."""

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_prefix="SISI_", extra="ignore"
    )

    # Environment
    env: str = "dev"  # dev | demo | staging | prod
    database_url: str = "postgresql+psycopg://sisi:sisi_dev_pw@localhost:5432/sisi"
    test_database_url: str = "postgresql+psycopg://sisi:sisi_dev_pw@localhost:5432/sisi_test"
    redis_url: str = "redis://localhost:6379/0"
    ontology_dir: Path = REPO_ROOT / "ontology"

    # Auth (users)
    jwt_secret: str = "dev-only-secret-change-me-32-bytes-minimum!"  # noqa: S105 — dev default; prod guarded below
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    phone_pepper: str = "dev-only-pepper-change-me"  # noqa: S105 — dev default; prod guarded below

    # Auth (staff)
    staff_idle_minutes: int = 15

    # Key management (envelope encryption)
    master_key_file: Path = REPO_ROOT / "backend" / "data" / "master.key"
    master_key_b64: str = ""

    # OTP
    otp_ttl_seconds: int = 300
    otp_max_requests_per_window: int = 5
    otp_max_failures: int = 10
    otp_dev_return: bool = True  # return OTP in the response (dev/demo ONLY)

    # Safety gating
    allow_unvalidated_rules: bool = (
        True  # dev/demo ONLY; engine refuses unvalidated rules otherwise
    )

    # Compliance config (defaults recorded in docs/assumptions.md A1-A4)
    self_consent_age: int = 18
    dsr_deadline_days: int = 30
    retention_diary_days: int = 2555
    retention_audit_days: int = 3650
    retention_voucher_days: int = 730
    helpline_child: str = "116"  # UNVERIFIED — confirm before launch
    helpline_gbv: str = "1195"  # UNVERIFIED — confirm before launch

    # Corridor (Phase 5)
    jitsi_domain: str = "meet.sisi-health.local"
    jitsi_app_id: str = "sisi"
    jitsi_app_secret: str = "dev-only-jitsi-secret-change-me"  # noqa: S105 — dev default; prod guarded below
    screening_config_path: Path = REPO_ROOT / "ontology" / "config" / "screening_schedule.json"

    @model_validator(mode="after")
    def _prod_guards(self) -> "Settings":
        if self.env in {"staging", "prod"}:
            if self.allow_unvalidated_rules:
                raise ValueError("SISI_ALLOW_UNVALIDATED_RULES must be false in staging/prod")
            if self.otp_dev_return:
                raise ValueError("SISI_OTP_DEV_RETURN must be false in staging/prod")
            if self.jwt_secret == "dev-only-secret-change-me-32-bytes-minimum!":  # noqa: S105 — guard, not a secret
                raise ValueError("SISI_JWT_SECRET must be set in staging/prod")
            if self.phone_pepper == "dev-only-pepper-change-me":
                raise ValueError("SISI_PHONE_PEPPER must be set in staging/prod")
            if self.jitsi_app_secret == "dev-only-jitsi-secret-change-me":  # noqa: S105 — guard, not a secret
                raise ValueError("SISI_JITSI_APP_SECRET must be set in staging/prod")
            if not self.master_key_b64:
                raise ValueError("SISI_MASTER_KEY_B64 must be set in staging/prod")
        if (
            self.env not in {"dev", "demo"}
            and self.master_key_b64 == ""
            and not self.master_key_file.exists()
        ):
            raise ValueError("master key required: set SISI_MASTER_KEY_B64 or create the key file")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
