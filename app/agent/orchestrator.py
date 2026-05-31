from sqlalchemy.orm import Session

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import TOOL_SPECS, dispatch
from app.llm.base import ChatMessage, LLMClient
from app.models.user import User
from app.repositories.message_repo import MessageRepository
from app.repositories.user_repo import UserRepository

HISTORY_LIMIT = 15
MAX_ITERATIONS = 6
FALLBACK_REPLY = (
    "Mohon maaf, saya sedang mengalami kendala memproses permintaan Anda. "
    "Boleh saya hubungkan dengan tim kami?"
)


def handle_chat(
    session: Session,
    llm: LLMClient,
    retriever,
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
    convo = [ChatMessage(role=m.role, content=m.content) for m in history]
    convo.append(ChatMessage(role="user", content=message))

    reply = FALLBACK_REPLY
    for _ in range(MAX_ITERATIONS):
        response = llm.generate(SYSTEM_PROMPT, convo, tools=TOOL_SPECS)
        if response.tool_calls:
            convo.append(ChatMessage(role="assistant", tool_calls=response.tool_calls))
            for tool_call in response.tool_calls:
                result = dispatch(tool_call, retriever=retriever)
                convo.append(
                    ChatMessage(role="tool", tool_name=tool_call.name, content=result)
                )
            continue
        reply = response.text or ""
        break

    messages.add(user.id, "user", message)
    messages.add(user.id, "assistant", reply)
    session.commit()

    return reply, user
