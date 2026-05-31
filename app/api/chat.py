from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent.orchestrator import handle_chat
from app.db import get_session
from app.llm.base import LLMClient
from app.llm.gemini import GeminiLLM
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()


def get_llm() -> LLMClient:
    return GeminiLLM()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    session: Session = Depends(get_session),
    llm: LLMClient = Depends(get_llm),
) -> ChatResponse:
    reply, user = handle_chat(
        session,
        llm,
        message=req.message,
        name=req.name,
        phone=req.phone,
        email=req.email,
    )
    return ChatResponse(reply=reply, user_id=user.id)
