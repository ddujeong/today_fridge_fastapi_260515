import os
from fastapi import HTTPException

model = None

ENABLE_LOCAL_EMBEDDING = os.getenv("ENABLE_LOCAL_EMBEDDING", "false").lower() == "true"


def get_model():
    global model

    if not ENABLE_LOCAL_EMBEDDING:
        raise HTTPException(
            status_code=503,
            detail="Local embedding is disabled in production"
        )

    if model is None:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    return model


def generate_embedding(text: str):
    return get_model().encode(text).tolist()