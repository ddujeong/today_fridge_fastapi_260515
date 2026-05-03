import os
import csv
from dataclasses import dataclass
from typing import List

import psycopg2
import numpy as np
from sentence_transformers import SentenceTransformer


DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "today_fridge")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "1234")
DB_SCHEMA = os.getenv("DB_SCHEMA", "today_fridge")

MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

OUTPUT_CSV = os.getenv(
    "OUTPUT_CSV",
    "ingredient_normalization_candidates.csv"
)

# 너무 낮으면 오탐이 많고, 너무 높으면 후보가 적게 나옴.
# 첫 실행은 0.86 ~ 0.90 사이 추천.
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.88"))


@dataclass
class IngredientRow:
    ingredient_id: int
    canonical_name: str
    normalized_name: str


def fetch_ingredients() -> List[IngredientRow]:
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )

    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT
                    ingredient_id,
                    COALESCE(canonical_name, '') AS canonical_name,
                    COALESCE(normalized_name, '') AS normalized_name
                FROM {DB_SCHEMA}.ingredient_master
                WHERE normalized_name IS NOT NULL
                  AND normalized_name <> ''
                ORDER BY ingredient_id;
            """)
            rows = cur.fetchall()

        return [
            IngredientRow(
                ingredient_id=row[0],
                canonical_name=row[1],
                normalized_name=row[2],
            )
            for row in rows
        ]

    finally:
        conn.close()


def normalize_vector(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v, axis=1, keepdims=True)
    norm[norm == 0] = 1
    return v / norm


def build_text(row: IngredientRow) -> str:
    """
    임베딩에 넣을 텍스트.
    normalized_name만 넣으면 너무 짧아서 의미 정보가 부족할 수 있으므로
    canonical_name도 함께 넣는다.
    """
    if row.canonical_name and row.canonical_name != row.normalized_name:
        return f"식재료: {row.normalized_name}. 원문: {row.canonical_name}"
    return f"식재료: {row.normalized_name}"


def main():
    ingredients = fetch_ingredients()

    if not ingredients:
        print("ingredient_master에서 재료를 찾지 못했습니다.")
        return

    print(f"재료 수: {len(ingredients)}")
    print(f"임베딩 모델 로딩: {MODEL_NAME}")

    model = SentenceTransformer(MODEL_NAME)

    texts = [build_text(row) for row in ingredients]
    embeddings = model.encode(
        texts,
        batch_size=64,
        show_progress_bar=True,
        convert_to_numpy=True,
    )

    embeddings = normalize_vector(embeddings)

    # cosine similarity = normalized vector dot product
    similarity_matrix = embeddings @ embeddings.T

    candidates = []

    for i in range(len(ingredients)):
        for j in range(i + 1, len(ingredients)):
            left = ingredients[i]
            right = ingredients[j]

            # 이미 완전히 같은 normalized_name이면 기존 SQL에서 처리 가능하므로 제외
            if left.normalized_name == right.normalized_name:
                continue

            score = float(similarity_matrix[i, j])

            if score >= SIMILARITY_THRESHOLD:
                candidates.append({
                    "left_id": left.ingredient_id,
                    "left_canonical_name": left.canonical_name,
                    "left_normalized_name": left.normalized_name,
                    "right_id": right.ingredient_id,
                    "right_canonical_name": right.canonical_name,
                    "right_normalized_name": right.normalized_name,
                    "similarity": round(score, 4),
                    "suggested_name": "",
                    "approved": "",
                    "memo": "",
                })

    candidates.sort(key=lambda x: x["similarity"], reverse=True)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "left_id",
                "left_canonical_name",
                "left_normalized_name",
                "right_id",
                "right_canonical_name",
                "right_normalized_name",
                "similarity",
                "suggested_name",
                "approved",
                "memo",
            ]
        )
        writer.writeheader()
        writer.writerows(candidates)

    print(f"후보 수: {len(candidates)}")
    print(f"CSV 생성 완료: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()