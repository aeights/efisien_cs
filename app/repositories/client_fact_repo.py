from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.client_fact import ClientFact


class ClientFactRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, user_id: int, key: str, value: str) -> ClientFact:
        fact = self.session.scalar(
            select(ClientFact).where(
                ClientFact.user_id == user_id, ClientFact.key == key
            )
        )
        if fact is None:
            fact = ClientFact(user_id=user_id, key=key, value=value)
            self.session.add(fact)
        else:
            fact.value = value
        self.session.flush()
        return fact

    def list_for_user(self, user_id: int) -> list[ClientFact]:
        return list(
            self.session.scalars(
                select(ClientFact).where(ClientFact.user_id == user_id).order_by(ClientFact.id)
            )
        )
