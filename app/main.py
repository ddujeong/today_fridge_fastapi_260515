from fastapi import FastAPI
from app.api.routes.health import router as health_router

app = FastAPI(title="Today Fridge AI Server")

app.include_router(health_router, prefix="/api")