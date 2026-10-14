"""MessagingProvider interface (spec 2: SMS behind a provider; WhatsApp behind
Turn.io / WhatsApp Business API behind a MessagingProvider interface). No
credentials are ever faked: providers refuse to send until real credentials are
configured (Africa's Talking sandbox = human task H2, Turn.io = H4)."""

import logging
from typing import Protocol

import httpx

from gateway.config import GatewaySettings

logger = logging.getLogger("sisi.gateway.messaging")


class MessagingProvider(Protocol):
    def send_sms(self, phone: str, message: str) -> None: ...


class AfricasTalkingProvider:
    """Africa's Talking SMS. Sandbox host in dev/demo; production host otherwise.
    Raises without configured credentials — never sends with invented ones."""

    def __init__(self, settings: GatewaySettings) -> None:
        self._settings = settings

    def send_sms(self, phone: str, message: str) -> None:
        if not self._settings.at_username or not self._settings.at_api_key:
            logger.warning("Africa's Talking credentials not configured; SMS not sent (H2)")
            return
        host = (
            "https://api.sandbox.africastalking.com"
            if self._settings.env in {"dev", "demo"}
            else "https://api.africastalking.com"
        )
        httpx.post(
            f"{host}/version1/messaging",
            headers={
                "apiKey": self._settings.at_api_key,
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "username": self._settings.at_username,
                "to": phone,
                "message": message,
            },
            timeout=10.0,
        ).raise_for_status()


class TurnIoWhatsAppProvider:
    """Turn.io WhatsApp outbound. Raises without a configured token (H4)."""

    def __init__(self, settings: GatewaySettings) -> None:
        self._settings = settings

    def send_text(self, wa_id: str, message: str) -> None:
        if not self._settings.turn_token:
            logger.warning("Turn.io token not configured; WhatsApp reply not sent (H4)")
            return
        httpx.post(
            "https://whatsapp.turn.io/v1/messages",
            headers={"Authorization": f"Bearer {self._settings.turn_token}"},
            json={"to": wa_id, "type": "text", "text": {"body": message}},
            timeout=10.0,
        ).raise_for_status()


class RecordingProvider:
    """Test/demo provider: records outbound SMS instead of sending."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def send_sms(self, phone: str, message: str) -> None:
        self.messages.append((phone, message))
