from __future__ import annotations

import sys
import types


def install_selenium_stubs_if_missing() -> None:
    """Install tiny Selenium stubs for controlled tests when selenium is absent.

    These stubs are only for the local fixture-based integration tests. The live
    smoke test still requires the real selenium package and a real browser.
    """
    try:
        import selenium  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    class TimeoutException(Exception):
        pass

    class NoSuchElementException(Exception):
        pass

    class ElementClickInterceptedException(Exception):
        pass

    class StaleElementReferenceException(Exception):
        pass

    class WebDriverException(Exception):
        pass

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

        def add_argument(self, argument: str):
            self.arguments.append(argument)

    class WebDriverWait:
        def __init__(self, driver, timeout: int):
            self.driver = driver
            self.timeout = timeout

        def until(self, condition):
            result = condition(self.driver)
            if result:
                return result
            raise TimeoutException("condition was not satisfied by selenium stub")

    selenium = types.ModuleType("selenium")
    webdriver = types.ModuleType("selenium.webdriver")
    webdriver.Chrome = lambda options=None: None

    common = types.ModuleType("selenium.webdriver.common")
    by_module = types.ModuleType("selenium.webdriver.common.by")
    by_module.By = By

    chrome = types.ModuleType("selenium.webdriver.chrome")
    options_module = types.ModuleType("selenium.webdriver.chrome.options")
    options_module.Options = Options

    support = types.ModuleType("selenium.webdriver.support")
    ui_module = types.ModuleType("selenium.webdriver.support.ui")
    ui_module.WebDriverWait = WebDriverWait

    common_exceptions = types.ModuleType("selenium.common.exceptions")
    common_exceptions.TimeoutException = TimeoutException
    common_exceptions.NoSuchElementException = NoSuchElementException
    common_exceptions.ElementClickInterceptedException = ElementClickInterceptedException
    common_exceptions.StaleElementReferenceException = StaleElementReferenceException
    common_exceptions.WebDriverException = WebDriverException

    selenium.webdriver = webdriver
    sys.modules.setdefault("selenium", selenium)
    sys.modules.setdefault("selenium.webdriver", webdriver)
    sys.modules.setdefault("selenium.webdriver.common", common)
    sys.modules.setdefault("selenium.webdriver.common.by", by_module)
    sys.modules.setdefault("selenium.webdriver.chrome", chrome)
    sys.modules.setdefault("selenium.webdriver.chrome.options", options_module)
    sys.modules.setdefault("selenium.webdriver.support", support)
    sys.modules.setdefault("selenium.webdriver.support.ui", ui_module)
    sys.modules.setdefault("selenium.common", types.ModuleType("selenium.common"))
    sys.modules.setdefault("selenium.common.exceptions", common_exceptions)
