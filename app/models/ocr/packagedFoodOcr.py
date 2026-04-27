def recognize_packaged_food_image(image_path, top_k=5):
    return [
        {
            "displayName": "서울우유",
            "normalizedName": "우유",
            "categorySuggestion": "유제품",
            "confidence": 0.91,
        }
    ]