"""
Build a review file for image search / dataset matching: gap classes get
  - normalized_name (DB, fixed)
  - visual_base_ko (heuristic: strip parens, 조리/형용 접두·접미 등)
  - synonyms_ko (원명 + 줄인 형태; 본명으로 이미지가 안 나오면 동의어로 영문 검색)
  - search_en (ko_to_en_image_search_seed.json 에서 synonyms_ko 키로 수집)

수식어 제거 예 (팀 로직): 집된장→된장, 샤브용 소고기 목살→소고기 목살,
시원한 생수→생수, 간 깨→깨

Regenerate after DB or dataset changes:
  python export_ingredient_image_alias_template.py

Output default: app/models/ingredient/data/ingredient_image_search_aliases.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

_TOOL_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _TOOL_DIR.parents[3]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.models.ingredient.tools.export_ingredient_cls_gap_checklist import (  # noqa: E402
    count_images,
    parse_ingredient_id,
)


def load_labels(master_path: Path) -> Dict[str, Any]:
    data = json.loads(master_path.read_text(encoding="utf-8"))
    return data.get("labels") or {}


def strip_parens(s: str) -> str:
    s = re.sub(r"\s*[\(（][^)）]*[\)）]", "", s)
    return s.strip()


def apply_reduction_rules(s: str) -> str:
    """One pass of pattern-based shortening (repeat until fixed point).

    팀 규칙 예: 집된장→된장, 샤브용 소고기 목살→소고기 목살, 시원한 생수→생수, 간 깨→깨
    (불필요한 수식·접두를 떼고 동의어/검색 후보로 쓴다.)
    """
    t = s.strip()
    # 정확 일치 (캡처 없는 표현)
    if t == "대파흰부분":
        return "대파"
    if t in ("간 깨", "깨 간 것"):
        return "깨"

    m = re.match(r"^시원한\s+(.+)$", t)
    if m:
        return m.group(1).strip()
    # 집된장→된장, 집고추장→고추장 … (집 + 본품목)
    m = re.match(r"^집(.+)$", t)
    if m:
        rest = m.group(1).strip()
        if rest:
            return rest

    rules = [
        re.compile(r"^(.+?)\s+데친\s+것$"),
        re.compile(r"^삶은\s+(.+)$"),
        re.compile(r"^다진\s*(.+)$"),
        re.compile(r"^(.+?)\s+다진\s+것$"),
        re.compile(r"^(.+?)\s+다진$"),
        re.compile(r"^채\s*썬\s+(.+)$"),
        re.compile(r"^채썬\s+(.+)$"),
        re.compile(r"^편으로\s*썬\s+(.+)$"),
        re.compile(r"^깐\s*(.+)$"),
        re.compile(r"^샤브용\s+(.+)$"),
        re.compile(r"^(.+?)\s+작은것$"),
        re.compile(r"^(.+?)\s+작은거$"),
        re.compile(r"^(.+?)\s+중간\s*사이즈$"),
        re.compile(r"^(.+?)\s+줄기$"),
        re.compile(r"^(.+?)\s+흰부분$"),
        re.compile(r"^(.+?)\s+녹색부분$"),
        re.compile(r"^(.+?)\s+가루$"),
    ]
    for pat in rules:
        m = pat.match(t)
        if m:
            return m.group(1).strip()
    return t


def reduce_to_visual_base(name: str) -> str:
    s = strip_parens(name)
    for _ in range(12):
        nxt = apply_reduction_rules(s)
        if nxt == s:
            break
        s = nxt
    return s.strip() or name.strip()


def split_synonym_phrases(name: str) -> List[str]:
    """Split composite recipe lines into candidate Korean phrases."""
    s = strip_parens(name)
    parts: List[str] = []
    for sep in [" 또는 ", " + ", "/", ","]:
        if sep in s:
            parts = [p.strip() for p in s.split(sep) if p.strip()]
            break
    if not parts:
        parts = [s]
    out: List[str] = []
    for p in parts:
        out.append(p)
        rb = reduce_to_visual_base(p)
        if rb != p:
            out.append(rb)
    return out


def unique_preserve(xs: List[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for x in xs:
        k = x.strip()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def load_ko_en_seed(path: Path) -> Dict[str, List[str]]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    m = data.get("map") or {}
    if not isinstance(m, dict):
        return {}
    out: Dict[str, List[str]] = {}
    for k, v in m.items():
        if isinstance(v, list):
            out[str(k)] = [str(x) for x in v]
        elif isinstance(v, str):
            out[str(k)] = [v]
    return out


def collect_search_en(syn_ko: List[str], seed: Dict[str, List[str]]) -> List[str]:
    terms: List[str] = []
    for ko in syn_ko:
        terms.extend(seed.get(ko, []))
    seen: Set[str] = set()
    out: List[str] = []
    for t in terms:
        x = t.strip()
        if x and x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)
    return out


def main() -> None:
    here = Path(__file__).resolve().parent
    default_master = here.parent / "data" / "model_label_to_master.json"
    default_seed = here.parent / "data" / "ko_to_en_image_search_seed.json"
    default_out = here.parent / "data" / "ingredient_image_search_aliases.json"

    parser = argparse.ArgumentParser(description="Export image alias template for gap ingredients")
    parser.add_argument("--master-json", type=Path, default=default_master)
    parser.add_argument("--dataset-root", type=Path, default=Path("ml_datasets/ingredient_master_cls"))
    parser.add_argument("--min-train", type=int, default=1)
    parser.add_argument("--seed-json", type=Path, default=default_seed)
    parser.add_argument("--out", type=Path, default=default_out)
    parser.add_argument("--include-covered", action="store_true", help="all classes, not only train gaps")
    args = parser.parse_args()

    if not args.master_json.exists():
        print(f"ERROR: {args.master_json}", file=sys.stderr)
        sys.exit(2)

    labels = load_labels(args.master_json)
    class_folders = sorted({str(lk) for lk in labels.keys()})

    seed = load_ko_en_seed(args.seed_json)
    root = args.dataset_root
    entries: List[Dict[str, Any]] = []

    for folder in class_folders:
        meta = labels.get(folder) or {}
        if not isinstance(meta, dict):
            continue
        nn = str(meta.get("normalizedName") or meta.get("normalized_name") or "")
        if not nn:
            continue
        tr = count_images(root / "train" / folder)
        if not args.include_covered and tr >= args.min_train:
            continue

        visual = reduce_to_visual_base(nn)
        syn_parts = split_synonym_phrases(nn)
        syn_ko = unique_preserve([nn, visual] + syn_parts)
        search_en = collect_search_en(syn_ko, seed)

        iid = parse_ingredient_id(folder)
        entries.append(
            {
                "model_folder": folder,
                "ingredient_id": iid,
                "normalized_name": nn,
                "display_name": str(meta.get("displayName") or nn),
                "category_suggestion": str(meta.get("categorySuggestion") or ""),
                "train_image_count": tr,
                "visual_base_ko": visual,
                "synonyms_ko": syn_ko,
                "search_en": search_en,
                "notes": "",
            }
        )

    entries.sort(key=lambda e: (e["ingredient_id"] if e["ingredient_id"] is not None else 999999,))

    from datetime import datetime, timezone

    doc = {
        "schema": "ingredient_image_search_aliases_v1",
        "description": "팀 검토용: 이미지 검색·데이터셋 매칭 시 normalized_name은 유지하고, visual_base_ko·synonyms_ko·search_en을 수정한다. "
        "검색은 search_en 순서로 시도하거나, 본재료 영어가 없으면 동의어 쪽 영어를 쓴다.",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "gapOnly": not args.include_covered,
        "minTrain": args.min_train,
        "entries": entries,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"out": str(args.out.resolve()), "entryCount": len(entries), "seed": str(args.seed_json)},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
