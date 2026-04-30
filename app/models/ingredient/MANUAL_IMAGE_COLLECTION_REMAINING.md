# 자동 수집 이후 — 수동으로 채울 것

자동으로는 **공개 웹 이미지 검색(DuckDuckGo)** 과 로컬에 이미 있는 **Grocery 조립**까지만 가능합니다. 아래는 **사람 손이 필요한** 나머지입니다.

## 1. 자동으로 받은 위치

| 경로 | 내용 |
|------|------|
| `data_sources/team_uploads/train/ing_XXXXX/*.jpg` | 웹 검색으로 내려받은 이미지 (`fetch_ingredient_images_web.py`) |
| `ml_datasets/ingredient_master_cls/` | `assemble_ingredient_master_cls_dataset.py` 로 Grocery(·Fruits-360·manifest) 복사본 |

## 2. 수동으로 할 일 (우선순위)

1. **커버리지 확인**  
   `python app/models/ingredient/tools/report_ingredient_master_cls_coverage.py`  
   `python app/models/ingredient/tools/export_ingredient_cls_gap_checklist.py`  
   → 여전히 train 부족인 `ing_XXXXX` 확인.

2. **웹 이미지 품질 검수**  
   `team_uploads` 에 들어온 사진이 라벨과 맞는지 샘플링. 틀린 파일은 삭제.

3. **검색어가 비었던 클래스**  
   `ingredient_image_search_aliases.json` 에서 `search_en` 보강 후 스크립트 재실행하거나, 직접 사진을 `team_uploads/train/ing_XXXXX/` 에 넣기.

4. **국내 공개데이터(AI-Hub 등)**  
   신청·다운로드 후 폴더를 정리하고, **`ingest_verified_path_manifest.py`** 또는 수동 복사로 `ing_XXXXX` 에 맞춤.  
   절차: `KOREAN_DATASET_APPLICATION_GUIDE.md`

5. **촬영·제품컷**  
   장류·젓갈·다진 재료 등 웹과 공개데이터로도 애매한 품목은 팀 촬영으로 보강.

6. **최종 조립**  
   ```powershell
   python app/models/ingredient/tools/assemble_ingredient_master_cls_dataset.py `
     --master-json app/models/ingredient/data/model_label_to_master.json `
     --grocery-root data_sources/GroceryStoreDataset/dataset `
     --team-root data_sources/team_uploads `
     --out ml_datasets/ingredient_master_cls --mode copy
   ```

## 3. 재실행 (웹 자동만 다시)

```powershell
cd project_final_backend_2
python app/models/ingredient/tools/export_ingredient_image_alias_template.py
pip install ddgs httpx pillow
python app/models/ingredient/tools/fetch_ingredient_images_web.py --target-per-class 12 --delay-ddgs 1.5
```

이미 목표 장수를 채운 폴더는 건너뜁니다(`target-per-class` 기준).
