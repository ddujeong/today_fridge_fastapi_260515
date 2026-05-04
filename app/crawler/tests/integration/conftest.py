from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

from app.crawler.tests.integration.support.fake_selenium import FakeWebDriver, FixturePage
from app.crawler.tests.integration.support.selenium_compat import install_selenium_stubs_if_missing


DEFAULT_LIST_URL = "https://www.10000recipe.com/recipe/list.html?cat4=63&order=reco&page=32"


@pytest.fixture
def crawler_dir() -> Path:
    configured = os.environ.get("CRAWLER_DIR")
    if configured:
        path = Path(configured).resolve()
    else:
        path = Path.cwd() / "app" / "crawler"

    if not (path / "Crawler_main.py").exists() or not (path / "Crawler_tool.py").exists():
        pytest.skip(
            "Crawler_main.py/Crawler_tool.py를 찾지 못했습니다. "
            "CRAWLER_DIR=/path/to/app/crawler 를 지정하세요."
        )
    return path


@pytest.fixture
def fixture_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def output_project_root(tmp_path, monkeypatch) -> Path:
    # Crawler_main.py writes to app/crawler/recipes_result/recipes{page}.csv relative to cwd.
    root = tmp_path
    (root / "app" / "crawler" / "recipes_result").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(root)
    return root


def import_crawler_modules_with_fake_driver(
    crawler_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    pages: list[FixturePage],
) -> tuple[ModuleType, ModuleType, FakeWebDriver]:
    """Import Crawler_tool and Crawler_main while replacing Chrome with FakeWebDriver.

    Crawler_main.py creates a Crawler instance at import time, so patching must happen
    before importing Crawler_main.
    """
    for module_name in ["Crawler_main", "Crawler_tool"]:
        sys.modules.pop(module_name, None)

    install_selenium_stubs_if_missing()
    sys.path.insert(0, str(crawler_dir))
    crawler_tool = importlib.import_module("Crawler_tool")

    fake_driver = FakeWebDriver(pages)
    monkeypatch.setattr(crawler_tool.webdriver, "Chrome", lambda options=None: fake_driver)
    monkeypatch.setattr(crawler_tool.Crawler, "wait", lambda self, a=0.0, b=0.0: None)
    monkeypatch.setitem(sys.modules, "Crawler_tool", crawler_tool)

    crawler_main = importlib.import_module("Crawler_main")
    return crawler_main, crawler_tool, fake_driver


@pytest.fixture
def import_with_fake_driver(crawler_dir, monkeypatch):
    def _import(pages: list[FixturePage]):
        return import_crawler_modules_with_fake_driver(crawler_dir, monkeypatch, pages)

    return _import
