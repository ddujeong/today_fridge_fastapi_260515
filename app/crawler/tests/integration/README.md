# Crawler 통합 테스트 코드

이 테스트 묶음은 `Crawler_main.py`와 `Crawler_tool.py` 기준으로 작성한 pytest 통합 테스트입니다.

## 목적

기본 통합 테스트는 실제 외부 사이트에 접속하지 않고, 로컬 fixture HTML을 이용해 아래 흐름을 검증합니다.

```text
목록 HTML → 상세 HTML → Crawler_tool.Crawler → Crawler_main.main() → CSV 저장 → CSV 계약 검증
```

실제 만개의레시피 사이트에 접속하는 테스트는 `live` 마커로 분리했습니다. 외부 사이트/광고/네트워크/ChromeDriver 상태에 따라 흔들릴 수 있으므로 평소에는 제외하는 것을 권장합니다.


크롤러 파일 위치가 기본값인 `app/crawler`라면 바로 실행하면 됩니다.

```bash
pytest -m integration
```

크롤러 파일 위치가 다르면 `CRAWLER_DIR`를 지정합니다.

```bash
CRAWLER_DIR=/Users/a0/Documents/git/project_final_backend_2/app/crawler pytest -m integration
```

## 실사이트 Smoke Test 실행

기본 실행에서는 `live` 테스트를 돌리지 않는 것을 권장합니다.

```bash
pytest -m "integration and not live"
```

실제 만개의레시피 사이트와 Chrome을 사용해 smoke test를 실행하려면 아래처럼 명시적으로 켭니다.

```bash
RUN_LIVE_CRAWLER_TESTS=1 CRAWLER_DIR=/Users/a0/Documents/git/project_final_backend_2/app/crawler pytest -m live
```

## 테스트 범위

| 파일 | 역할 |
|---|---|
| `test_crawler_controlled_integration.py` | 로컬 HTML 기반으로 `Crawler_main.main()`이 CSV를 생성하는지 검증 |
| `test_crawler_live_smoke.py` | 실제 사이트 목록 페이지에서 최소 DOM이 잡히는지 검증하는 선택 테스트 |
| `support/fake_selenium.py` | Chrome 없이 `Crawler_tool.Crawler`를 실행하기 위한 fake WebDriver |
| `fixtures/*.html` | 목록/상세 페이지 테스트 HTML |

## 주의

현재 `Crawler_main.py`는 import 시점에 `Crawler_tool.Crawler(...)`를 생성합니다. 그래서 테스트에서는 먼저 `Crawler_tool.webdriver.Chrome`을 fake driver로 바꾼 뒤 `Crawler_main.py`를 import합니다. 이 처리를 빼면 테스트 중 실제 Chrome이 열릴 수 있습니다.
