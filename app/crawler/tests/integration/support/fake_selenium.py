from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from bs4 import BeautifulSoup

from app.crawler.tests.integration.support.selenium_compat import install_selenium_stubs_if_missing

install_selenium_stubs_if_missing()

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By


@dataclass(frozen=True)
class FixturePage:
    url: str
    path: Path


class FakeWebElement:
    """A small Selenium WebElement substitute for the crawler's current XPath/CSS usage."""

    def __init__(self, node, driver: "FakeWebDriver"):
        self.node = node
        self.driver = driver
        self.clicked = False

    @property
    def text(self) -> str:
        return self.node.get_text("\n", strip=True)

    def get_attribute(self, name: str):
        return self.node.get(name)

    def click(self):
        self.clicked = True
        href = self.get_attribute("href")
        if href:
            self.driver.get(href)

    def screenshot(self, path: str):
        Path(path).write_bytes(b"fake screenshot")
        return True

    def find_element(self, by=By.ID, value: Optional[str] = None):
        elements = self.find_elements(by, value)
        if not elements:
            raise NoSuchElementException(f"No element found by={by} value={value}")
        return elements[0]

    def find_elements(self, by=By.ID, value: Optional[str] = None) -> List["FakeWebElement"]:
        if value is None:
            return []

        if by == By.ID:
            found = self.node.find(id=value)
            return [FakeWebElement(found, self.driver)] if found else []

        if by == By.CLASS_NAME:
            found = self.node.find_all(class_=lambda classes: _has_class(classes, value))
            return [FakeWebElement(each, self.driver) for each in found]

        if by == By.TAG_NAME:
            found = self.node.find_all(value)
            return [FakeWebElement(each, self.driver) for each in found]

        if by == By.CSS_SELECTOR:
            found = self.node.select(value)
            return [FakeWebElement(each, self.driver) for each in found]

        if by == By.XPATH:
            found = _xpath(self.node, value)
            return [FakeWebElement(each, self.driver) for each in found]

        return []


class FakeWebDriver:
    """A small WebDriver substitute backed by fixture HTML files."""

    def __init__(self, pages: Iterable[FixturePage]):
        self.pages: Dict[str, Path] = {page.url: page.path for page in pages}
        self.current_url = "about:blank"
        self._history: List[str] = []
        self._soup = BeautifulSoup("<html><body></body></html>", "html.parser")
        self.page_load_timeout = None
        self.script_timeout = None

    @property
    def window_handles(self):
        return ["main"]

    def set_page_load_timeout(self, seconds: int):
        self.page_load_timeout = seconds

    def set_script_timeout(self, seconds: int):
        self.script_timeout = seconds

    def get(self, url: str):
        if self.current_url != "about:blank":
            self._history.append(self.current_url)
        self.current_url = url
        html_path = self.pages.get(url)
        if html_path is None:
            # Unknown pages intentionally render an empty document.
            self._soup = BeautifulSoup("<html><body></body></html>", "html.parser")
            return
        self._soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")

    def back(self):
        if not self._history:
            return
        previous = self._history.pop()
        self.current_url = previous
        html_path = self.pages.get(previous)
        if html_path is None:
            self._soup = BeautifulSoup("<html><body></body></html>", "html.parser")
        else:
            self._soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")

    def execute_script(self, script: str, *args):
        normalized = " ".join(script.split())
        if "return document.readyState" in normalized:
            return "complete"
        if "window.stop" in normalized:
            return None
        if "window.history.go(-1)" in normalized:
            self.back()
            return None
        if "arguments[0].click" in normalized and args:
            args[0].click()
            return None
        if "return { clicked" in normalized or "removedFrames" in normalized:
            return {"clicked": 0, "removedFrames": 0, "removedOverlays": 0}
        if "elementFromPoint" in normalized or "ad_position_box" in normalized:
            return False
        return None

    def find_element(self, by=By.ID, value: Optional[str] = None):
        return FakeWebElement(self._soup, self).find_element(by, value)

    def find_elements(self, by=By.ID, value: Optional[str] = None):
        return FakeWebElement(self._soup, self).find_elements(by, value)

    def quit(self):
        return None


def _has_class(classes, expected: str) -> bool:
    if not classes:
        return False
    if isinstance(classes, str):
        return expected in classes.split()
    return expected in classes


def _direct_children(node, tag_name: str):
    return [child for child in node.find_all(tag_name, recursive=False)]


def _xpath(node, value: str):
    compact = value.replace(" ", "")

    if compact == "./li[contains(@class,'common_sp_list_li')]":
        return [
            child
            for child in _direct_children(node, "li")
            if _has_class(child.get("class"), "common_sp_list_li")
        ]

    if compact == "./ul/li":
        results = []
        for ul in _direct_children(node, "ul"):
            results.extend(_direct_children(ul, "li"))
        return results

    if compact == "./div":
        return _direct_children(node, "div")

    if compact == "./span":
        return _direct_children(node, "span")

    if compact == "./div[1]":
        divs = _direct_children(node, "div")
        return divs[:1]

    if compact == "./div[2]/img":
        divs = _direct_children(node, "div")
        if len(divs) < 2:
            return []
        image = divs[1].find("img")
        return [image] if image else []

    # .//div[contains(@class, 'view2_summary_info')]//span[1]
    if compact.startswith(".//div[contains(@class,'view2_summary_info')]//span["):
        index_text = compact.rsplit("span[", 1)[1].rstrip("]")
        index = int(index_text) - 1
        info_div = node.find("div", class_=lambda classes: _has_class(classes, "view2_summary_info"))
        if not info_div:
            return []
        spans = info_div.find_all("span")
        if 0 <= index < len(spans):
            return [spans[index]]
        return []

    return []
