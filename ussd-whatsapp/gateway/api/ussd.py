"""USSD callback (Africa's Talking format). The response is plain text — AT
renders it directly to the subscriber; every screen ≤160 chars (linted)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form
from fastapi.responses import PlainTextResponse

from gateway.deps import get_flow_engine
from gateway.flows.engine import FlowEngine

logger = logging.getLogger("sisi.gateway.ussd")

router = APIRouter()


@router.post("/callback")
def ussd_callback(
    session_id: Annotated[str, Form(alias="sessionId")],
    phone_number: Annotated[str, Form(alias="phoneNumber")],
    text: Annotated[str, Form()] = "",
    service_code: Annotated[str, Form(alias="serviceCode")] = "",
    flow: Annotated[FlowEngine, Depends(get_flow_engine)] = None,  # type: ignore[assignment]
) -> PlainTextResponse:
    """Africa's Talking posts form fields; we return the next screen as text."""
    logger.info("ussd session=%s service=%s", session_id, service_code)
    response_text = flow.handle(
        session_id=session_id, phone=phone_number, text=text, channel="ussd"
    )
    return PlainTextResponse(response_text)
