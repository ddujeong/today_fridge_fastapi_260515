from __future__ import annotations

import importlib
import sys

import pytest


class FakeDriver:
    def __init__(self, current_url="https://example.test/recipe/list.html", ready_state="complete"):
        self.current_url = current_url
        self.ready_state = ready_state
        self.window_handles = ["main"]
        self.get_calls = []
        self.back_calls = 0
        self.scripts = []
        self.find_element_map = {}
        self.find_elements_map = {}
        self.raise_on_get = None
        self.raise_on_window_handles = None
        self.script_results = []

    def get(self, url):
        self.get_calls.append(url)
        if self.raise_on_get is not None:
            raise self.raise_on_get
        self.current_url = url

    def back(self):
        self.back_calls += 1

    def execute_script(self, script, *args):
        self.scripts.append((script, args))
        if self.script_results:
            result = self.script_results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        if "document.readyState" in script:
            return self.ready_state
        if script.strip().startswith("return"):
            return False
        return None

    def find_element(self, by, value):
        key = (by, value)
        if key not in self.find_element_map:
            raise self.no_such_element("not found")
        value = self.find_element_map[key]
        if isinstance(value, Exception):
            raise value
        return value

    def find_elements(self, by, value):
        return self.find_elements_map.get((by, value), [])


class FakeElement:
    def __init__(self, *, text="", attrs=None, click_errors=None, js_click_error=None):
        self.text = text
        self.attrs = attrs or {}
        self.click_errors = list(click_errors or [])
        self.js_click_error = js_click_error
        self.click_count = 0
        self.sent_keys = []
        self.screenshots = []

    def click(self):
        self.click_count += 1
        if self.click_errors:
            raise self.click_errors.pop(0)

    def get_attribute(self, name):
        return self.attrs.get(name)

    def send_keys(self, text):
        self.sent_keys.append(text)

    def screenshot(self, path):
        self.screenshots.append(path)
        return True


class ImmediateWait:
    def __init__(self, driver, timeout):
        self.driver = driver
        self.timeout = timeout

    def until(self, condition):
        result = condition(self.driver)
        if result:
            return result
        # crawler_tool_module fixture에서 주입한 모듈 예외를 사용하기 위해 런타임에 import합니다.
        import Crawler_tool

        raise Crawler_tool.TimeoutException("condition was not truthy")


def import_crawler_tool(monkeypatch):
    # Crawler_main 테스트에서 fake Crawler_tool이 sys.modules에 들어갔을 수 있으므로 제거합니다.
    sys.modules.pop("Crawler_tool", None)
    module = importlib.import_module("Crawler_tool")
    monkeypatch.setattr(module, "WebDriverWait", ImmediateWait)
    return module


@pytest.fixture()
def crawler_tool(monkeypatch):
    module = import_crawler_tool(monkeypatch)
    FakeDriver.no_such_element = module.NoSuchElementException
    return module


def make_crawler(crawler_tool, driver=None, target_url="https://example.test/recipe/list.html?page=32"):
    crawler = object.__new__(crawler_tool.Crawler)
    crawler.driver = driver or FakeDriver()
    crawler.target_url = target_url
    crawler.debug = False
    crawler.speed = {}
    return crawler


def test_set_target_url_updates_target(crawler_tool):
    crawler = make_crawler(crawler_tool)

    crawler.set_target_url("https://example.test/changed")

    assert crawler.target_url == "https://example.test/changed"


def test_strip_fragment_removes_hash(crawler_tool):
    crawler = make_crawler(crawler_tool)

    assert crawler._strip_fragment("https://example.test/a#section") == "https://example.test/a"
    assert crawler._strip_fragment(None) is None


def test_safe_url_returns_unavailable_when_driver_raises(crawler_tool):
    class BrokenDriver:
        @property
        def current_url(self):
            raise RuntimeError("broken")

    crawler = make_crawler(crawler_tool, driver=BrokenDriver())

    assert crawler._safe_url() == "<unavailable>"


def test_driver_alive_false_when_window_handles_raise(crawler_tool):
    class BrokenDriver:
        @property
        def window_handles(self):
            raise crawler_tool.WebDriverException("closed")

    crawler = make_crawler(crawler_tool, driver=BrokenDriver())

    assert crawler.is_alive() is False


def test_on_list_page_checks_current_url(crawler_tool):
    crawler = make_crawler(crawler_tool, driver=FakeDriver(current_url="https://x.test/recipe/list.html?page=1"))

    assert crawler.on_list_page() is True

    crawler.driver.current_url = "https://x.test/recipe/123"

    assert crawler.on_list_page() is False


def test_ensure_list_page_recovers_when_not_on_list_page(monkeypatch, crawler_tool):
    driver = FakeDriver(current_url="https://x.test/recipe/123")
    crawler = make_crawler(crawler_tool, driver=driver, target_url="https://x.test/recipe/list.html?page=1")
    calls = []
    monkeypatch.setattr(crawler, "go", lambda url: calls.append(("go", url)))
    monkeypatch.setattr(crawler, "dismiss_ads", lambda: calls.append(("dismiss_ads",)))

    crawler.ensure_list_page()

    assert calls == [("go", "https://x.test/recipe/list.html?page=1"), ("dismiss_ads",)]


def test_ensure_list_page_does_nothing_when_already_on_list_page(monkeypatch, crawler_tool):
    crawler = make_crawler(crawler_tool, driver=FakeDriver(current_url="https://x.test/recipe/list.html?page=1"))
    calls = []
    monkeypatch.setattr(crawler, "go", lambda url: calls.append(("go", url)))
    monkeypatch.setattr(crawler, "dismiss_ads", lambda: calls.append(("dismiss_ads",)))

    crawler.ensure_list_page()

    assert calls == []


def test_go_returns_true_when_ready_state_is_complete(crawler_tool):
    driver = FakeDriver(ready_state="complete")
    crawler = make_crawler(crawler_tool, driver=driver)

    result = crawler.go("https://x.test/detail")

    assert result is True
    assert driver.get_calls == ["https://x.test/detail"]


def test_go_continues_after_page_load_timeout_and_stops_window(crawler_tool):
    driver = FakeDriver(ready_state="complete")
    driver.raise_on_get = crawler_tool.TimeoutException("slow")
    crawler = make_crawler(crawler_tool, driver=driver)

    result = crawler.go("https://x.test/detail")

    assert result is True
    assert any("window.stop" in script for script, _ in driver.scripts)


def test_go_returns_false_when_webdriver_get_fails(crawler_tool):
    driver = FakeDriver()
    driver.raise_on_get = crawler_tool.WebDriverException("driver crashed")
    crawler = make_crawler(crawler_tool, driver=driver)

    result = crawler.go("https://x.test/detail")

    assert result is False


def test_go_returns_false_when_required_element_missing(crawler_tool):
    driver = FakeDriver(ready_state="complete")
    crawler = make_crawler(crawler_tool, driver=driver)

    result = crawler.go("https://x.test/detail", required=("id", "required-box"))

    assert result is False


def test_go_returns_true_when_required_element_exists(crawler_tool):
    driver = FakeDriver(ready_state="complete")
    driver.find_elements_map[("id", "required-box")] = [object()]
    crawler = make_crawler(crawler_tool, driver=driver)

    result = crawler.go("https://x.test/detail", required=("id", "required-box"))

    assert result is True


def test_back_falls_back_to_direct_get_when_history_does_not_move(crawler_tool):
    driver = FakeDriver(current_url="https://x.test/recipe/123", ready_state="complete")
    crawler = make_crawler(crawler_tool, driver=driver)

    crawler.back(fallback_url="https://x.test/recipe/list.html?page=1")

    assert driver.back_calls == 1
    assert "https://x.test/recipe/list.html?page=1" in driver.get_calls


def test_is_ad_returns_true_when_known_ad_position_box_exists(crawler_tool):
    driver = FakeDriver()
    crawler = make_crawler(crawler_tool, driver=driver)
    driver.find_element_map[(crawler_tool.By.ID, "ad_position_box")] = object()

    assert crawler.is_ad() is True


def test_is_ad_uses_script_detection_when_known_ad_id_missing(crawler_tool):
    driver = FakeDriver()
    driver.script_results = [True]
    crawler = make_crawler(crawler_tool, driver=driver)

    assert crawler.is_ad() is True


def test_dismiss_ads_closes_overlay_only_when_ad_exists(monkeypatch, crawler_tool):
    crawler = make_crawler(crawler_tool)
    calls = []
    monkeypatch.setattr(crawler, "is_ad", lambda: True)
    monkeypatch.setattr(crawler, "_close_ad_overlays", lambda: calls.append("close"))
    monkeypatch.setattr(crawler, "wait", lambda *args: calls.append("wait"))

    crawler.dismiss_ads()

    assert calls == ["close", "wait"]


def test_dismiss_ads_does_not_close_when_ad_absent(monkeypatch, crawler_tool):
    crawler = make_crawler(crawler_tool)
    calls = []
    monkeypatch.setattr(crawler, "is_ad", lambda: False)
    monkeypatch.setattr(crawler, "_close_ad_overlays", lambda: calls.append("close"))
    monkeypatch.setattr(crawler, "wait", lambda *args: calls.append("wait"))

    crawler.dismiss_ads()

    assert calls == ["wait"]


def test_close_ad_overlays_does_nothing_when_driver_is_dead(monkeypatch, crawler_tool):
    driver = FakeDriver()
    crawler = make_crawler(crawler_tool, driver=driver)
    monkeypatch.setattr(crawler, "_driver_alive", lambda: False)

    crawler._close_ad_overlays()

    assert driver.scripts == []


def test_close_ad_overlays_executes_cleanup_script_when_driver_alive(crawler_tool):
    driver = FakeDriver()
    driver.script_results = [{"clicked": 1, "removedFrames": 2, "removedOverlays": 0}]
    crawler = make_crawler(crawler_tool, driver=driver)

    crawler._close_ad_overlays()

    assert driver.scripts
    assert "Remove known ad iframes" in driver.scripts[0][0]


def test_click_success_with_native_click(monkeypatch, crawler_tool):
    crawler = make_crawler(crawler_tool)
    elem = FakeElement(attrs={"class": "target"})
    monkeypatch.setattr(crawler, "dismiss_ads", lambda: None)

    result = crawler.click(elem)

    assert result is True
    assert elem.click_count == 1
    assert any("scrollIntoView" in script for script, _ in crawler.driver.scripts)


def test_click_uses_js_click_after_intercepted_click(monkeypatch, crawler_tool):
    driver = FakeDriver()
    crawler = make_crawler(crawler_tool, driver=driver)
    elem = FakeElement(click_errors=[crawler_tool.ElementClickInterceptedException("blocked")])
    monkeypatch.setattr(crawler, "dismiss_ads", lambda: None)
    close_calls = []
    monkeypatch.setattr(crawler, "_close_ad_overlays", lambda: close_calls.append("closed"))

    result = crawler.click(elem)

    assert result is True
    assert close_calls == ["closed"]
    assert any("arguments[0].click" in script for script, _ in driver.scripts)


def test_click_returns_false_when_native_and_js_click_keep_failing(monkeypatch, crawler_tool):
    driver = FakeDriver()

    def execute_script(script, *args):
        driver.scripts.append((script, args))
        if "arguments[0].click" in script:
            raise RuntimeError("js failed")
        return None

    driver.execute_script = execute_script
    crawler = make_crawler(crawler_tool, driver=driver)
    elem = FakeElement(
        click_errors=[
            crawler_tool.ElementClickInterceptedException("blocked 1"),
            crawler_tool.ElementClickInterceptedException("blocked 2"),
            crawler_tool.ElementClickInterceptedException("blocked 3"),
            crawler_tool.ElementClickInterceptedException("blocked 4"),
        ]
    )
    monkeypatch.setattr(crawler, "dismiss_ads", lambda: None)
    monkeypatch.setattr(crawler, "_close_ad_overlays", lambda: None)
    monkeypatch.setattr(crawler, "wait", lambda *args: None)

    result = crawler.click(elem)

    assert result is False
    assert elem.click_count == 4


def test_type_sends_keys_and_waits_when_wait_args_exist(monkeypatch, crawler_tool):
    crawler = make_crawler(crawler_tool)
    elem = FakeElement()
    wait_calls = []
    monkeypatch.setattr(crawler, "wait", lambda a, b: wait_calls.append((a, b)))

    crawler.type(elem, "김치", wait_a=0.1, wait_b=0.2)

    assert elem.sent_keys == ["김치"]
    assert wait_calls == [(0.1, 0.2)]


def test_download_screenshots_to_result_graph_and_waits(monkeypatch, crawler_tool):
    crawler = make_crawler(crawler_tool)
    elem = FakeElement()
    wait_calls = []
    monkeypatch.setattr(crawler, "wait", lambda a, b: wait_calls.append((a, b)))

    result = crawler.download(elem, wait_a=0.1, wait_b=0.2)

    assert result is True
    assert elem.screenshots == ["./resultGraph.png"]
    assert wait_calls == [(0.1, 0.2)]
