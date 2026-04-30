import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "app" / "crawler" / "Crawler_main.py"


def _load_module_with_mocks(mock_crawler):
    """Load Crawler_main.py with mocked dependencies before module execution."""
    fake_crawler_tool = types.SimpleNamespace(Crawler=MagicMock(return_value=mock_crawler))

    class _DummyDataFrame:
        def __init__(self, *_args, **_kwargs):
            pass

        def to_csv(self, *_args, **_kwargs):
            pass

    fake_pandas = types.SimpleNamespace(DataFrame=_DummyDataFrame)

    old_crawler_tool = sys.modules.get("Crawler_tool")
    old_pandas = sys.modules.get("pandas")

    sys.modules["Crawler_tool"] = fake_crawler_tool
    sys.modules["pandas"] = fake_pandas

    try:
        spec = importlib.util.spec_from_file_location("crawler_main_under_test", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
    finally:
        if old_crawler_tool is None:
            sys.modules.pop("Crawler_tool", None)
        else:
            sys.modules["Crawler_tool"] = old_crawler_tool

        if old_pandas is None:
            sys.modules.pop("pandas", None)
        else:
            sys.modules["pandas"] = old_pandas

    return module


def test_main_success_writes_expected_csv():
    mock_crawler = MagicMock()
    mock_crawler.target_url = "https://example.com/list?page=32"

    list_container = MagicMock()
    list_item = MagicMock()
    detail_link = MagicMock()
    detail_link.get_attribute.return_value = "https://example.com/recipe/1"
    list_item.find_element.return_value = detail_link
    list_container.find_elements.return_value = [list_item]

    summary_box = MagicMock()
    h3 = MagicMock()
    h3.text = "Kimchi Fried Rice"
    span1 = MagicMock()
    span1.text = "1 serving"
    span2 = MagicMock()
    span2.text = "20 min"
    span3 = MagicMock()
    span3.text = "Easy"
    summary_box.find_element.side_effect = [h3, span1, span2, span3]

    ingredient_area = MagicMock()
    ingredient_li = MagicMock()
    ingredient_name = MagicMock()
    ingredient_name.text = "Rice"
    ingredient_qty = MagicMock()
    ingredient_qty.text = "1 bowl"
    ingredient_li.find_element.side_effect = [ingredient_name, ingredient_qty]
    ingredient_area.find_elements.return_value = [ingredient_li]

    step_root = MagicMock()
    step_header = MagicMock()
    step_item = MagicMock()
    step_desc = MagicMock()
    step_desc.text = "Stir fry all ingredients"
    step_img = MagicMock()
    step_img.get_attribute.return_value = "https://example.com/step1.jpg"
    step_item.find_element.side_effect = [step_desc, step_img]
    step_root.find_elements.return_value = [step_header, step_item]

    thumb = MagicMock()
    thumb.get_attribute.return_value = "https://example.com/thumb.jpg"

    mock_crawler.get_elem_class.side_effect = [list_container, list_container, summary_box]
    mock_crawler.get_elem_id.side_effect = [ingredient_area, step_root, thumb]
    mock_crawler.current_url.return_value = "https://example.com/list?page=32"

    module = _load_module_with_mocks(mock_crawler)

    df_mock = MagicMock()
    module.pd.DataFrame = MagicMock(return_value=df_mock)
    module.os.makedirs = MagicMock()

    module.main()

    module.os.makedirs.assert_called_once_with("./recipes_result", exist_ok=True)
    module.pd.DataFrame.assert_called_once()
    df_mock.to_csv.assert_called_once()

    to_csv_args, to_csv_kwargs = df_mock.to_csv.call_args
    assert to_csv_args[0].endswith("recipes32.csv")
    assert to_csv_kwargs["index"] is False
    assert to_csv_kwargs["encoding"] == "utf-8-sig"


def test_main_skips_item_when_detail_url_missing():
    mock_crawler = MagicMock()
    mock_crawler.target_url = "https://example.com/list?page=32"

    list_container = MagicMock()
    list_item = MagicMock()
    detail_link = MagicMock()
    detail_link.get_attribute.return_value = ""
    list_item.find_element.return_value = detail_link
    list_container.find_elements.return_value = [list_item]

    mock_crawler.get_elem_class.side_effect = [list_container, list_container]

    module = _load_module_with_mocks(mock_crawler)

    df_mock = MagicMock()
    module.pd.DataFrame = MagicMock(return_value=df_mock)
    module.os.makedirs = MagicMock()

    module.main()

    mock_crawler.go.assert_not_called()
    module.pd.DataFrame.assert_called_once_with([])
    df_mock.to_csv.assert_called_once()


def test_safe_find_text_returns_default_on_error():
    parent = MagicMock()
    parent.find_element.side_effect = Exception("not found")

    module = _load_module_with_mocks(MagicMock())

    result = module._safe_find_text(parent, "XPATH", "//span", default="N/A")
    assert result == "N/A"
