from datetime import date, timedelta
from typing import Optional

# 카테고리별 보관일 기준표 (문서 09_카테고리별_기본보관일_초안.md 기준)
# storageType: ROOM | REFRIGERATED | FROZEN | ETC
STORAGE_DAYS: dict[str, dict[str, int]] = {
    "VEGETABLE": {"ROOM": 2,  "REFRIGERATED": 5,   "FROZEN": 30,  "ETC": 3},
    "FRUIT":     {"ROOM": 3,  "REFRIGERATED": 7,   "FROZEN": 30,  "ETC": 4},
    "MEAT":      {"ROOM": 1,  "REFRIGERATED": 2,   "FROZEN": 30,  "ETC": 1},
    "SEAFOOD":   {"ROOM": 1,  "REFRIGERATED": 2,   "FROZEN": 30,  "ETC": 1},
    "DAIRY":     {"ROOM": 1,  "REFRIGERATED": 5,   "FROZEN": 30,  "ETC": 2},
    "GRAIN":     {"ROOM": 30, "REFRIGERATED": 60,  "FROZEN": 180, "ETC": 30},
    "SEASONING": {"ROOM": 60, "REFRIGERATED": 120, "FROZEN": 365, "ETC": 60},
    "SAUCE":     {"ROOM": 30, "REFRIGERATED": 90,  "FROZEN": 365, "ETC": 30},
    "ETC":       {"ROOM": 2,  "REFRIGERATED": 5,   "FROZEN": 30,  "ETC": 2},
}

# storageType만 있고 카테고리 없을 때 fallback
STORAGE_FALLBACK: dict[str, int] = {
    "ROOM": 2,
    "REFRIGERATED": 5,
    "FROZEN": 30,
    "ETC": 3,
}

DEFAULT_DAYS = 2  # 카테고리/보관방식 둘 다 없을 때 보수적 기본값


def estimate_expiration(
    category_code: Optional[str],
    storage_type: Optional[str],
) -> dict:
    """
    규칙 기반 유통기한 추정.
    반환: { estimated_expiration_date, base_days, estimated_by, needs_review }
    """
    today = date.today()
    needs_review = False

    category = (category_code or "").upper()
    storage = (storage_type or "").upper()

    if category in STORAGE_DAYS:
        storage_map = STORAGE_DAYS[category]
        base_days = storage_map.get(storage, storage_map["REFRIGERATED"])
        estimated_by = "rule:category+storage"
    elif storage in STORAGE_FALLBACK:
        base_days = STORAGE_FALLBACK[storage]
        estimated_by = "rule:storage_only"
        needs_review = True
    else:
        base_days = DEFAULT_DAYS
        estimated_by = "rule:default"
        needs_review = True

    estimated_date = today + timedelta(days=base_days)

    return {
        "estimated_expiration_date": estimated_date.isoformat(),
        "base_days": base_days,
        "estimated_by": estimated_by,
        "needs_review": needs_review,
    }
