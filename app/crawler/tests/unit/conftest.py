"""공통 테스트 설정.

이 파일은 두 가지를 처리합니다.

1. Crawler_main.py / Crawler_tool.py가 있는 폴더를 sys.path에 추가합니다.
2. 테스트 환경에 selenium이 없더라도 import 단위 테스트가 가능하도록 최소 stub을 설치합니다.

실제 프로젝트 환경에 selenium이 설치되어 있으면 stub은 사용되지 않습니다.
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path


def _install_selenium_stubs_if_needed() -> None:
    try:
        import selenium  # noqa: F401
        return
    except Exception:
        pass

    selenium = types.ModuleType("selenium")
    webdriver = types.ModuleType("selenium.webdriver")
    common = types.ModuleType("selenium.webdriver.common")
    by_mod = types.ModuleType("selenium.webdriver.common.by")
    chrome_mod = types.ModuleType("selenium.webdriver.chrome")
    options_mod = types.ModuleType("selenium.webdriver.chrome.options")
    support_mod = types.ModuleType("selenium.webdriver.support")
    support_ui_mod = types.ModuleType("selenium.webdriver.support.ui")
    exceptions_mod = types.ModuleType("selenium.common.exceptions")
    selenium_common = types.ModuleType("selenium.common")

    class By:
        ID = "id"
        XPATH = "xpath"
        CLASS_NAME = "class name"
        CSS_SELECTOR = "css selector"
        TAG_NAME = "tag name"

    class Options:
        def __init__(self):
            self.arguments = []
            self.page_load_strategy = None

        def add_argument(self, value):
            self.arguments.append(value)

    class TimeoutException(Exception):
        pass

    class NoSuchElementException(Exception):
        pass

    class WebDriverException(Exception):
        pass

    class ElementClickInterceptedException(Exception):
        pass

    class StaleElementReferenceException(Exception):
        pass

    class WebDriverWait:
        def __init__(self, driver, timeout):
            self.driver = driver
            self.timeout = timeout

        def until(self, condition):
            result = condition(self.driver)
            if result:
                return result
            raise TimeoutException("condition was not truthy")

    class Chrome:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("Chrome stub should not be instantiated in unit tests")

    by_mod.By = By
    options_mod.Options = Options
    support_ui_mod.WebDriverWait = WebDriverWait
    exceptions_mod.TimeoutException = TimeoutException
    exceptions_mod.NoSuchElementException = NoSuchElementException
    exceptions_mod.WebDriverException = WebDriverException
    exceptions_mod.ElementClickInterceptedException = ElementClickInterceptedException
    exceptions_mod.StaleElementReferenceException = StaleElementReferenceException
    webdriver.Chrome = Chrome

    sys.modules.setdefault("selenium", selenium)
    sys.modules.setdefault("selenium.webdriver", webdriver)
    sys.modules.setdefault("selenium.webdriver.common", common)
    sys.modules.setdefault("selenium.webdriver.common.by", by_mod)
    sys.modules.setdefault("selenium.webdriver.chrome", chrome_mod)
    sys.modules.setdefault("selenium.webdriver.chrome.options", options_mod)
    sys.modules.setdefault("selenium.webdriver.support", support_mod)
    sys.modules.setdefault("selenium.webdriver.support.ui", support_ui_mod)
    sys.modules.setdefault("selenium.common", selenium_common)
    sys.modules.setdefault("selenium.common.exceptions", exceptions_mod)


def _find_crawler_dir() -> Path:
    env_dir = os.getenv("CRAWLER_DIR")
    candidates = []
    if env_dir:
        candidates.append(Path(env_dir))

    cwd = Path.cwd()
    this_file = Path(__file__).resolve()
    repo_like_roots = [cwd, *this_file.parents]

    for root in repo_like_roots:
        candidates.extend(
            [
                root / "app" / "crawler",
                root / "crawler",
                root,
            ]
        )

    for candidate in candidates:
        if (candidate / "Crawler_main.py").exists() or (candidate / "Crawler_tool.py").exists():
            return candidate

    return cwd


_install_selenium_stubs_if_needed()

CRAWLER_DIR = _find_crawler_dir()
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))
