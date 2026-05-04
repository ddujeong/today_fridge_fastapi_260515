from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
import pytest

from app.crawler.tests.integration.conftest import DEFAULT_LIST_URL
from app.crawler.tests.integration.support.fake_selenium import FixturePage


pytestmark = pytest.mark.integration


def _read_output_csv(project_root: Path) -> pd.DataFrame:
    csv_path = project_root / "app" / "crawler" / "recipes_result" / "recipes32.csv"
    assert csv_path.exists(), f"CSV가 생성되지 않았습니다: {csv_path}"
    return pd.read_csv(csv_path)


def _pages(fixture_dir: Path, list_file: str) -> list[FixturePage]:
    return [
        FixturePage(DEFAULT_LIST_URL, fixture_dir / list_file),
        FixturePage("https://local.test/recipe/fixture-1", fixture_dir / "detail_valid_1.html"),
        FixturePage("https://local.test/recipe/fixture-2", fixture_dir / "detail_valid_2_no_main_image.html"),
        FixturePage("https://local.test/recipe/missing-ingredients", fixture_dir / "detail_missing_ingredients.html"),
    ]


def test_main_collects_local_fixture_recipes_and_writes_csv(
    fixture_dir,
    output_project_root,
    import_with_fake_driver,
):
    crawler_main, _, fake_driver = import_with_fake_driver(_pages(fixture_dir, "list_two_valid.html"))

    crawler_main.main()

    df = _read_output_csv(output_project_root)
    assert list(df.columns) == ["img", "title", "quantity", "time", "difficulty", "ingredients", "steps"]
    assert len(df) == 2

    first = df[df["title"] == "테스트 김치찌개"].iloc[0]
    assert first["quantity"] == "2인분"
    assert first["time"] == "30분 이내"
    assert first["difficulty"] == "초급"
    assert first["img"] == "https://img.local/kimchi-main.jpg"
    assert "김치" in first["ingredients"]
    assert "돼지고기" in first["ingredients"]
    assert "김치를 먹기 좋게 자른다." in first["steps"]

    second = df[df["title"] == "테스트 계란말이"].iloc[0]
    assert second["quantity"] == "1인분"
    assert second["time"] == "15분 이내"
    assert second["difficulty"] == "아무나"
    assert pd.isna(second["img"]), "대표 이미지가 없으면 CSV에서는 NaN으로 읽혀야 합니다."
    assert "계란" in second["ingredients"]
    assert "계란을 풀고 소금을 넣는다." in second["steps"]

    assert fake_driver.current_url == DEFAULT_LIST_URL


def test_main_skips_broken_detail_and_continues_next_recipe(
    fixture_dir,
    output_project_root,
    import_with_fake_driver,
):
    crawler_main, _, _ = import_with_fake_driver(_pages(fixture_dir, "list_one_valid_one_invalid.html"))

    crawler_main.main()

    df = _read_output_csv(output_project_root)
    assert len(df) == 1
    assert df.iloc[0]["title"] == "테스트 김치찌개"
    assert "재료 누락 레시피" not in set(df["title"])


def test_generated_csv_satisfies_recipe_import_contract(
    fixture_dir,
    output_project_root,
    import_with_fake_driver,
):
    crawler_main, _, _ = import_with_fake_driver(_pages(fixture_dir, "list_two_valid.html"))

    crawler_main.main()

    df = _read_output_csv(output_project_root)
    required_columns = {"img", "title", "quantity", "time", "difficulty", "ingredients", "steps"}
    assert required_columns.issubset(df.columns)

    for _, row in df.iterrows():
        assert isinstance(row["title"], str) and row["title"].strip()
        assert isinstance(row["quantity"], str) and row["quantity"].strip()
        assert isinstance(row["time"], str) and row["time"].strip()
        assert isinstance(row["difficulty"], str) and row["difficulty"].strip()

        ingredients = ast.literal_eval(row["ingredients"])
        assert isinstance(ingredients, list)
        assert ingredients, "레시피는 최소 1개 이상의 재료를 가져야 합니다."
        for ingredient in ingredients:
            assert set(ingredient) == {"name", "quantity"}
            assert ingredient["name"].strip()
            assert ingredient["quantity"].strip()

        steps = ast.literal_eval(row["steps"])
        assert isinstance(steps, list)
        assert steps, "레시피는 최소 1개 이상의 조리 단계를 가져야 합니다."
        for step in steps:
            assert set(step) == {"description", "image"}
            assert step["description"].strip()
            assert step["image"].strip()
