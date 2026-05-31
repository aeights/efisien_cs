from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.chat import router

app = FastAPI(title="Efisien CS")
app.include_router(router)
# Explicit API routes above take precedence; this serves the chat UI at "/".
app.mount("/", StaticFiles(directory="static", html=True), name="static")
