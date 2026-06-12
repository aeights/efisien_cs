from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent.orchestrator import handle_chat
from app.config import settings
from app.db import get_session
from app.integrations.calendar import LocalCalendar
from app.integrations.google_calendar import build_google_calendar
from app.integrations.email import ConsoleEmail, SmtpEmail
from app.llm.base import LLMClient
from app.llm.gemini import GeminiLLM
from app.rag.embeddings import GeminiEmbedder
from app.rag.retriever import Retriever
from app.rag.store import ChromaStore
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()


def get_llm() -> LLMClient:
    return GeminiLLM()


def get_retriever() -> Retriever:
    return Retriever(ChromaStore.persistent(), GeminiEmbedder())


def get_calendar():
    if settings.google_calendar_id and settings.google_service_account_file:
        return build_google_calendar(settings)
    return LocalCalendar()


def get_email():
    if settings.smtp_user and settings.smtp_password:
        return SmtpEmail(
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=settings.smtp_user,
            password=settings.smtp_password,
            sender=settings.smtp_from or settings.smtp_user,
        )
    return ConsoleEmail()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    session: Session = Depends(get_session),
    llm: LLMClient = Depends(get_llm),
    retriever: Retriever = Depends(get_retriever),
    calendar=Depends(get_calendar),
    mailer=Depends(get_email),
) -> ChatResponse:
    reply, user = handle_chat(
        session,
        llm,
        retriever,
        message=req.message,
        name=req.name,
        phone=req.phone,
        email=req.email,
        calendar=calendar,
        mailer=mailer,
    )
    return ChatResponse(reply=reply, user_id=user.id)
