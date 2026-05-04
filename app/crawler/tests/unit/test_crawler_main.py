from __future__ import annotations

import importlib
import sys
import types

import pytest


class FakeText:
    def __init__(self, value: str):
        self.text = value


class FakeElement:
    def __init__(self, text: str = "", attrs: dict | None = None):
        self.text = text
        self.attrs = attrs or {}
        self.children: dict[tuple[str, str], object] = {}
        self.children_lists: dict[tuple[str, str], list] = {}

    def add_child(self, by, value, child):
        self.children[(by, value)] = child
        return self

    def add_children(self, by, value, children):
        self.children_lists[(by, value)] = children
        return self

    def find_element(self, by, value):
        key = (by, value)
        if key not in self.children:
            raise LookupError(f"missing child: {key}")
        child = self.children[key]
        if isinstance(child, Exception):
            raise child
        return child

    def find_elements(self, by, value):
        key = (by, value)
        return self.children_lists.get(key, [])

    def get_attribute(self, name):
        return self.attrs.get(name)


class SequencedListElement:
    def __init__(self, responses):
        self.responses = list(responses)
        self.index = 0

    def find_elements(self, by, value):
        if not self.responses:
            return []
        response = self.responses[min(self.index, len(self.responses) - 1)]
        self.index += 1
        return response


class FakeCrawler:
    def __init__(self, target_url="https://example.test/recipe/list.html?page=32"):
        self.target_url = target_url
        self.list_element = FakeElement()
        self.summary_box = FakeElement()
        self.ingredient_area = FakeElement()
        self.step_area = FakeElement()
        self.title_image = FakeElement(attrs={"src": "https://img.test/title.jpg"})
        self.raise_by_class: dict[str, Exception] = {}
        self.raise_by_id: dict[str, Exception] = {}
        self.calls: list[tuple] = []

    def set_target_url(self, url):
        self.target_url = url
        self.calls.append(("set_target_url", url))

    def wait(self, *args, **kwargs):
        self.calls.append(("wait", args, kwargs))

    def ensure_list_page(self, url=None):
        self.calls.append(("ensure_list_page", url))

    def get_elem_class(self, classname):
        self.calls.append(("get_elem_class", classname))
        if classname in self.raise_by_class:
            raise self.raise_by_class[classname]
        if classname == "common_sp_list_ul":
            return self.list_element
        if classname == "view2_summary":
            return self.summary_box
        raise LookupError(classname)

    def get_elem_id(self, id_):
        self.calls.append(("get_elem_id", id_))
        if id_ in self.raise_by_id:
            raise self.raise_by_id[id_]
        if id_ == "divConfirmedMaterialArea":
            return self.ingredient_area
        if id_ == "obx_recipe_step_start":
            return self.step_area
        if id_ == "main_thumbs":
            return self.title_image
        raise LookupError(id_)

    def _close_ad_overlays(self):
        self.calls.append(("_close_ad_overlays",))

    def go(self, url):
        self.calls.append(("go", url))
        return True

    def back(self, fallback_url=None):
        self.calls.append(("back", fallback_url))

    def current_url(self):
        return self.target_url

    def dismiss_ads(self):
        self.calls.append(("dismiss_ads",))


def import_crawler_main(monkeypatch, fake_crawler: FakeCrawler):
    fake_crawler_tool = types.ModuleType("Crawler_tool")
    fake_crawler_tool.Crawler = lambda target_url=None: fake_crawler

    monkeypatch.setitem(sys.modules, "Crawler_tool", fake_crawler_tool)
    sys.modules.pop("Crawler_main", None)
    return importlib.import_module("Crawler_main")


def patch_dataframe(monkeypatch, crawler_main):
    captured = {"makedirs": []}

    class FakeDataFrame:
        def __init__(self, data):
            captured["data"] = data

        def to_csv(self, path, index, encoding):
            captured["path"] = path
            captured["index"] = index
            captured["encoding"] = encoding

    monkeypatch.setattr(crawler_main.pd, "DataFrame", FakeDataFrame)

    def fake_makedirs(path, exist_ok=False):
        captured["makedirs"].append((path, exist_ok))

    monkeypatch.setattr(crawler_main.os, "makedirs", fake_makedirs)
    return captured


def make_item(By, href="https://example.test/recipe/1"):
    link = FakeElement(attrs={"href": href})
    item = FakeElement().add_child(By.CSS_SELECTOR, "a.common_sp_link", link)
    return item


def configure_success_recipe(crawler_main, fake: FakeCrawler, *, title_image=True, bad_second_step=False):
    By = crawler_main.By
    item = make_item(By)
    fake.list_element = FakeElement().add_children(
        By.XPATH,
        "./li[contains(@class,'common_sp_list_li')]",
        [item],
    )

    fake.summary_box = (
        FakeElement()
        .add_child(By.TAG_NAME, "h3", FakeText("  김치찌개  "))
        .add_child(By.XPATH, ".//div[contains(@class, 'view2_summary_info')]//span[1]", FakeText(" 2인분 "))
        .add_child(By.XPATH, ".//div[contains(@class, 'view2_summary_info')]//span[2]", FakeText(" 30분 "))
        .add_child(By.XPATH, ".//div[contains(@class, 'view2_summary_info')]//span[3]", FakeText(" 초급 "))
    )

    ingredient_1 = (
        FakeElement()
        .add_child(By.XPATH, "./div", FakeText(" 김치 "))
        .add_child(By.XPATH, "./span", FakeText(" 1컵 "))
    )
    ingredient_2 = (
        FakeElement()
        .add_child(By.XPATH, "./div", FakeText(" 돼지고기 "))
        .add_child(By.XPATH, "./span", FakeText(" 200g "))
    )
    fake.ingredient_area = FakeElement().add_children(By.XPATH, "./ul/li", [ingredient_1, ingredient_2])

    header = FakeElement()
    step_1 = (
        FakeElement()
        .add_child(By.XPATH, "./div[1]", FakeText("김치를 볶는다."))
        .add_child(By.XPATH, "./div[2]/img", FakeElement(attrs={"src": "https://img.test/step1.jpg"}))
    )

    if bad_second_step:
        step_2 = FakeElement()
    else:
        step_2 = (
            FakeElement()
            .add_child(By.XPATH, "./div[1]", FakeText("물을 넣고 끓인다."))
            .add_child(By.XPATH, "./div[2]/img", FakeElement(attrs={"src": "https://img.test/step2.jpg"}))
        )
    fake.step_area = FakeElement().add_children(By.XPATH, "./div", [header, step_1, step_2])

    if title_image:
        fake.title_image = FakeElement(attrs={"src": "https://img.test/title.jpg"})
    else:
        fake.raise_by_id["main_thumbs"] = LookupError("missing title image")


def test_safe_find_text_returns_stripped_text(monkeypatch):
    fake = FakeCrawler()
    crawler_main = import_crawler_main(monkeypatch, fake)

    parent = FakeElement().add_child("by", "value", FakeText("  2인분 \n"))

    assert crawler_main._safe_find_text(parent, "by", "value") == "2인분"


def test_safe_find_text_returns_default_when_element_missing(monkeypatch):
    fake = FakeCrawler()
    crawler_main = import_crawler_main(monkeypatch, fake)

    parent = FakeElement()

    assert crawler_main._safe_find_text(parent, "by", "missing", default="N/A") == "N/A"


def test_main_collects_single_recipe_and_writes_csv(monkeypatch):
    fake = FakeCrawler()
    crawler_main = import_crawler_main(monkeypatch, fake)
    configure_success_recipe(crawler_main, fake)
    captured = patch_dataframe(monkeypatch, crawler_main)

    crawler_main.main()

    assert captured["path"] == "app/crawler/recipes_result/recipes32.csv"
    assert captured["index"] is False
    assert captured["encoding"] == "utf-8-sig"
    assert captured["data"] == [
        {
            "img": "https://img.test/title.jpg",
            "title": "김치찌개",
            "quantity": "2인분",
            "time": "30분",
            "difficulty": "초급",
            "ingredients": [
                {"name": "김치", "quantity": "1컵"},
                {"name": "돼지고기", "quantity": "200g"},
            ],
            "steps": [
                {"description": "김치를 볶는다.", "image": "https://img.test/step1.jpg"},
                {"description": "물을 넣고 끓인다.", "image": "https://img.test/step2.jpg"},
            ],
        }
    ]
    assert ("back", crawler_main.target_url) in fake.calls
    assert any(call[0] == "dismiss_ads" for call in fake.calls)


def test_main_skips_item_when_detail_url_is_empty(monkeypatch):
    fake = FakeCrawler()
    crawler_main = import_crawler_main(monkeypatch, fake)
    By = crawler_main.By
    fake.list_element = FakeElement().add_children(
        By.XPATH,
        "./li[contains(@class,'common_sp_list_li')]",
        [make_item(By, href="")],
    )
    captured = patch_dataframe(monkeypatch, crawler_main)

    crawler_main.main()

    assert captured["data"] == []
    assert not any(call[0] == "go" and call[1] == "" for call in fake.calls)


def test_main_recovers_to_list_page_when_summary_fails(monkeypatch):
    fake = FakeCrawler()
    crawler_main = import_crawler_main(monkeypatch, fake)
    By = crawler_main.By
    fake.list_element = FakeElement().add_children(
        By.XPATH,
        "./li[contains(@class,'common_sp_list_li')]",
        [make_item(By)],
    )
    fake.raise_by_class["view2_summary"] = LookupError("summary not found")
    captured = patch_dataframe(monkeypatch, crawler_main)

    crawler_main.main()

    assert captured["data"] == []
    assert ("go", crawler_main.target_url) in fake.calls
    assert ("dismiss_ads",) in fake.calls


def test_main_goes_back_when_ingredient_read_fails(monkeypatch):
    fake = FakeCrawler()
    crawler_main = import_crawler_main(monkeypatch, fake)
    configure_success_recipe(crawler_main, fake)
    fake.raise_by_id["divConfirmedMaterialArea"] = LookupError("ingredients missing")
    captured = patch_dataframe(monkeypatch, crawler_main)

    crawler_main.main()

    assert captured["data"] == []
    assert ("back", crawler_main.target_url) in fake.calls


def test_main_saves_previous_steps_when_later_step_is_malformed(monkeypatch):
    fake = FakeCrawler()
    crawler_main = import_crawler_main(monkeypatch, fake)
    configure_success_recipe(crawler_main, fake, bad_second_step=True)
    captured = patch_dataframe(monkeypatch, crawler_main)

    crawler_main.main()

    assert len(captured["data"]) == 1
    assert captured["data"][0]["steps"] == [
        {"description": "김치를 볶는다.", "image": "https://img.test/step1.jpg"}
    ]


def test_main_sets_title_image_to_none_when_main_thumbnail_missing(monkeypatch):
    fake = FakeCrawler()
    crawler_main = import_crawler_main(monkeypatch, fake)
    configure_success_recipe(crawler_main, fake, title_image=False)
    captured = patch_dataframe(monkeypatch, crawler_main)

    crawler_main.main()

    assert captured["data"][0]["img"] is None


def test_main_skips_when_current_items_shrink_during_iteration(monkeypatch):
    fake = FakeCrawler()
    crawler_main = import_crawler_main(monkeypatch, fake)
    By = crawler_main.By
    first = make_item(By, href="")
    second = make_item(By, href="https://example.test/recipe/2")
    fake.list_element = SequencedListElement([[first, second], [first], [first]])
    captured = patch_dataframe(monkeypatch, crawler_main)

    crawler_main.main()

    assert captured["data"] == []
    assert not any(call[0] == "go" and call[1] == "https://example.test/recipe/2" for call in fake.calls)
