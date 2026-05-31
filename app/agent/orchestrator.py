from sqlalchemy.orm import Session

from app.agent.prompts import SYSTEM_PROMPT
from app.llm.base import ChatMessage, LLMClient
from app.models.user import User
from app.repositories.message_repo import MessageRepository
from app.repositories.user_repo import UserRepository

HISTORY_LIMIT = 15


def handle_chat(
    session: Session,
    llm: LLMClient,
    *,
    message: str,
    name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
) -> tuple[str, User]:
    users = UserRepository(session)
    messages = MessageRepository(session)

    user = users.get_or_create(name=name, phone=phone, email=email)

    history = messages.recent(user.id, limit=HISTORY_LIMIT)
    llm_messages = [ChatMessage(role=m.role, content=m.content) for m in history]
    llm_messages.append(ChatMessage(role="user", content=message))

    reply = llm.generate(SYSTEM_PROMPT, llm_messages)

    messages.add(user.id, "user", message)
    messages.add(user.id, "assistant", reply)
    session.commit()

    return reply, user
