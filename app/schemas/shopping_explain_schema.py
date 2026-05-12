from typing import List, Optional
from pydantic import BaseModel


class ShoppingItemInfo(BaseModel):
    mallName: str
    productName: str
    price: int
    shippingType: str  # FREE, STANDARD, EXPRESS, NEXT_DAY
    originalPrice: Optional[int] = None
    discountRate: Optional[int] = None


class ShoppingExplainRequest(BaseModel):
    ingredientName: str
    # 레시피 컨텍스트 (선택)
    recipeTitle: Optional[str] = None
    recipeId: Optional[int] = None
    matchedIngredients: List[str] = []
    missingIngredients: List[str] = []
    # 쇼핑 컨텍스트
    shoppingItems: List[ShoppingItemInfo] = []
    lowestPrice: Optional[int] = None


class ShoppingExplainResponse(BaseModel):
    explanation: str
