"""Gateway dependency wiring: flow engine, providers, session store."""

from app.config import get_settings as backend_settings
from app.crypto.key_provider import DatabaseKeyProvider
from app.rules.loader import build_engine

from gateway.config import GatewaySettings
from gateway.flows.engine import FlowEngine
from gateway.providers.messaging import AfricasTalkingProvider, TurnIoWhatsAppProvider
from gateway.sessions.store import build_session_store


def build_flow_engine(settings: GatewaySettings) -> FlowEngine:
    backend = backend_settings()
    engine = build_engine(backend.ontology_dir, allow_unvalidated=backend.allow_unvalidated_rules)
    store = build_session_store(settings)
    provider = DatabaseKeyProvider(backend)
    sms = AfricasTalkingProvider(settings)
    return FlowEngine(store=store, settings=settings, engine=engine, provider=provider, sms=sms)


def get_flow_engine() -> FlowEngine:
    return build_flow_engine(GatewaySettings())


def get_whatsapp_provider() -> TurnIoWhatsAppProvider:
    return TurnIoWhatsAppProvider(GatewaySettings())
