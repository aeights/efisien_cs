from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.chat import router
from app.api.whatsapp import router as whatsapp_router

app = FastAPI(title="Efisien CS")
app.include_router(router)
app.include_router(whatsapp_router)
# Explicit API routes above take precedence; this serves the chat UI at "/".
app.mount("/", StaticFiles(directory="static", html=True), name="static")
