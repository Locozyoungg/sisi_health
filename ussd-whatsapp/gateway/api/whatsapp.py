"""WhatsApp webhook (Turn.io format): inbound text messages drive the same
assessment flow as USSD; replies go back through the Turn.io provider."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from gateway.deps import get_flow_engine, get_whatsapp_provider
from gateway.flows.engine import FlowEngine
from gateway.providers.messaging import TurnIoWhatsAppProvider

logger = logging.getLogger("sisi.gateway.whatsapp")

router = APIRouter()

FlowDep = Annotated[FlowEngine, Depends(get_flow_engine)]
WhatsAppProviderDep = Annotated[TurnIoWhatsAppProvider, Depends(get_whatsapp_provider)]


@router.post("/webhook")
async def whatsapp_webhook(
    request: Request,
    flow: FlowDep,
    provider: WhatsAppProviderDep,
) -> dict[str, Any]:
    """Turn.io posts {contacts: [{wa_id}], messages: [{text: {body}}]}."""
    body = await request.json()
    contacts = body.get("contacts") or []
    messages = body.get("messages") or []
    replies: list[str] = []
    for contact, message in zip(contacts, messages, strict=False):
        wa_id = contact.get("wa_id")
        text = (message.get("text") or {}).get("body", "")
        if not wa_id:
            continue
        response_text = flow.handle(session_id=wa_id, phone=wa_id, text=text, channel="whatsapp")
        provider.send_text(wa_id, response_text)
        replies.append(wa_id)
    return {"replies": replies}
