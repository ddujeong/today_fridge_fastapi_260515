from fastapi import FastAPI
from app.api.routes.health import router as health_router
from app.api.internal.visionInternalApi import router as vision_internal_router
from app.api.routes.ingredient import router as ingredient_router

app = FastAPI(title="Today Fridge AI Server")

app.include_router(health_router, prefix="/api")
app.include_router(vision_internal_router)
app.include_router(ingredient_router, prefix="/api/v1")
