from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.agent.orchestrator import handle_chat
from app.api.chat import get_calendar, get_email, get_llm, get_retriever, get_waha_client
from app.db import get_session

router = APIRouter()


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    session: Session = Depends(get_session),
    llm=Depends(get_llm),
    retriever=Depends(get_retriever),
    calendar=Depends(get_calendar),
    mailer=Depends(get_email),
    waha=Depends(get_waha_client),
) -> dict[str, str]:
    data = await request.json()
    if data.get("event") != "message":
        return {"status": "ignored"}
    payload = data.get("payload") or {}
    chat_id = payload.get("from") or ""
    body = payload.get("body") or ""
    if payload.get("fromMe") or chat_id.endswith("@g.us") or not body.strip():
        return {"status": "ignored"}
    phone = chat_id.split("@")[0]
    reply, _user = handle_chat(
        session, llm, retriever, message=body, phone=phone, calendar=calendar, mailer=mailer
    )
    waha.send_text(chat_id, reply)
    return {"status": "ok"}
