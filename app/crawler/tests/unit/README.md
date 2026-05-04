# Crawler pytest 테스트 코드

## 목적

`Crawler_main.py`, `Crawler_tool.py`를 대상으로 한 pytest 기반 테스트 코드입니다.
실제 Chrome/Selenium 브라우저를 띄우지 않고 fake driver/fake element를 주입해서 다음을 검증합니다.

- 레시피 목록 → 상세 이동 → 요약/재료/조리단계/대표 이미지 수집 흐름
- 상세 URL 없음, 요약/재료/단계/이미지 누락 시 복구 흐름
- `Crawler_tool.Crawler`의 `go`, `back`, `ensure_list_page`, `dismiss_ads`, `click`, `type`, `download` 동작

## 배치 위치

권장 위치는 프로젝트 루트입니다.

```text
project_final_backend_2/
  app/
    crawler/
      Crawler_main.py
      Crawler_tool.py
  tests/
    crawler/
      conftest.py
      test_crawler_main.py
      test_crawler_tool.py
  pytest.ini
```

## 실행 방법

프로젝트 루트에서 실행하세요.

```bash
pytest
```

`Crawler_main.py`, `Crawler_tool.py`가 `app/crawler`가 아닌 다른 위치에 있다면 `CRAWLER_DIR`를 지정하세요.

```bash
CRAWLER_DIR=/Users/a0/Documents/git/project_final_backend_2/app/crawler pytest
```

## 주의

현재 `Crawler_main.py`는 import 시점에 `Crawler_tool.Crawler(...)`를 생성합니다. 이 테스트 코드는 fake `Crawler_tool` 모듈을 먼저 주입해서 실제 Chrome 실행을 막습니다.
