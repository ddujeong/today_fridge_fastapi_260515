import sys
from pathlib import Path

# Add the project root to sys.path to allow running this script directly
project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from fastapi import FastAPI
from app.models.img2class.ingredientRouteClassifier import IngredientRouteClassifier


app = FastAPI()

classifier = IngredientRouteClassifier(
    model_path="app/models/img2class/best.pt",
    confidence_threshold=0.60,
    device=None,
    imgsz=224,
)

@app.post("/vision/ingredient-route")
def classify_ingredient_image(image_path: str):
    return classifier.classify_image(image_path)