from fastapi import FastAPI
from app.api.routes.health import router as health_router
from app.api.routes.ingredient import router as ingredient_router

app = FastAPI(title="Today Fridge AI Server")

app.include_router(health_router, prefix="/api")
app.include_router(ingredient_router, prefix="/api/v1")
