from __future__ import annotations

import importlib
import os
import sys

import pytest


pytestmark = [pytest.mark.integration, pytest.mark.live]


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_CRAWLER_TESTS") != "1",
    reason="실사이트 테스트는 RUN_LIVE_CRAWLER_TESTS=1 일 때만 실행합니다.",
)
def test_live_recipe_list_page_has_recipe_items(crawler_dir):
    """Real-site smoke test.

    This intentionally checks only the smallest stable contract:
    the list page loads and exposes at least one recipe item.
    """
    selenium_by = pytest.importorskip("selenium.webdriver.common.by")
    By = selenium_by.By

    sys.path.insert(0, str(crawler_dir))
    crawler_tool = importlib.import_module("Crawler_tool")

    url = "https://www.10000recipe.com/recipe/list.html?cat4=63&order=reco&page=1"
    crawler = crawler_tool.Crawler(target_url=url)
    try:
        crawler.go(url, required=(By.CLASS_NAME, "common_sp_list_ul"))
        crawler.dismiss_ads()
        recipe_items = crawler.get_elem_class("common_sp_list_ul").find_elements(
            By.XPATH,
            "./li[contains(@class,'common_sp_list_li')]",
        )
        assert len(recipe_items) > 0
    finally:
        try:
            crawler.driver.quit()
        except Exception:
            pass
