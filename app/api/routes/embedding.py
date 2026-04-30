from fastapi import APIRouter
from pydantic import BaseModel

from app.services.embedding_service import generate_embedding

router = APIRouter(prefix="/embedding", tags=["embedding"])


class EmbeddingRequest(BaseModel):
    text: str


@router.post("")
def create_embedding(req: EmbeddingRequest):
    vector = generate_embedding(req.text)

    return {
        "dimension": len(vector),
        "embedding": vector
    }