from pydantic import BaseModel, model_validator


class ChatRequest(BaseModel):
    message: str
    name: str | None = None
    phone: str | None = None
    email: str | None = None

    @model_validator(mode="after")
    def require_identity(self):
        if not self.phone and not self.email:
            raise ValueError("phone or email is required")
        return self


class ChatResponse(BaseModel):
    reply: str
    user_id: int
