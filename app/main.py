from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from app.api.routes.health import router as health_router
from app.api.internal.visionInternalApi import router as vision_internal_router
from app.api.routes.ingredient import router as ingredient_router
from app.api.routes.embedding import router as embedding_router
from app.api.routes.recommendation_llm import router as recommendation_llm_router    
from app.api.routes.recipe_tag import router as recipe_tag_router
from app.api.routes.substitution_llm import router as substitution_llm_router

app = FastAPI(title="Today Fridge AI Server")

app.include_router(health_router, prefix="/api")
app.include_router(vision_internal_router)
app.include_router(ingredient_router, prefix="/api/v1")
app.include_router(embedding_router, prefix="/api/v1")
app.include_router(recommendation_llm_router, prefix="/api/v1")
app.include_router(recipe_tag_router, prefix="/api/v1")
app.include_router(substitution_llm_router, prefix="/api/v1")