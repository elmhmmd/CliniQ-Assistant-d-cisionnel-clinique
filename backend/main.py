from fastapi import FastAPI

from backend.api.endpoints import auth, health, query
from backend.core.database import Base, engine
from backend.core.exceptions import register_exception_handlers

Base.metadata.create_all(bind=engine)

app = FastAPI(title="CliniQ", version="0.1.0")

register_exception_handlers(app)

app.include_router(health.router, tags=["health"])
app.include_router(auth.router, tags=["auth"])
app.include_router(query.router, tags=["query"])
