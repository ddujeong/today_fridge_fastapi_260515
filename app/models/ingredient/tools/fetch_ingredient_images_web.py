"""
Download ingredient images using DuckDuckGo image search (English queries).

Uses `ingredient_image_search_aliases.json`:
  - Tries `search_en` phrases in order; if a phrase yields no saves, tries the next.
  - If `search_en` is empty, rebuilds from `synonyms_ko` + `ko_to_en_image_search_seed.json`.

Writes under ``<out-root>/train/<model_folder>/`` as ``ddgs_*.jpg``.

**Train-only cap** (``--max-per-class``): each ``train/ing_XXX`` holds at most that many images.
Folders already at or above the cap are skipped (no trimming). While downloading a class,
as soon as the on-disk train count reaches the cap, the loop stops and the next class runs.
Per run, at most ``--target-per-class`` new images are requested per class, capped by remaining room.

If ``--skip-if-gte`` is 0, it defaults to the same value as ``--max-per-class`` (skip classes
that already have that many images in train).

Copyright: web images may be restricted; use only per team/license policy.

Usage (backend_2 root):
  pip install ddgs
  python app/models/ingredient/tools/fetch_ingredient_images_web.py --max-classes 5

Trim folders that already exceed the cap (optional cleanup):
  python app/models/ingredient/tools/trim_ingredient_cls_split_folders.py --dataset-root ml_datasets/ingredient_master_cls
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Set

# Force UTF-8 stdout so JSON logs preserve Korean in PowerShell/terminal capture.
# Without this, some environments write mojibake (� / 占싯...) into the log file itself.
try:  # Python 3.7+
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass
try:
    import httpx
except ImportError as exc:  # pragma: no cover
    raise SystemExit("pip install httpx") from exc

try:
    from ddgs import DDGS

    _DDGS_USE_LEGACY_KWARGS = False
except ImportError:  # pragma: no cover
    try:
        from duckduckgo_search import DDGS  # type: ignore

        _DDGS_USE_LEGACY_KWARGS = True
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("pip install ddgs  (or legacy: pip install duckduckgo-search)") from exc

try:
    from PIL import Image
    import io

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

_TOOL_DIR = Path(__file__).resolve().parent
_DATA = _TOOL_DIR.parent / "data"
_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
# Appended to each English base phrase so DDG hits bottles, jars, cooking shots, etc.
_QUERY_DIVERSITY_SUFFIXES = (
    " bottle",
    " jar",
    " packaging",
    " cooking",
    " ingredient",
    " food",
    " recipe",
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_ko_en_seed(path: Path) -> Dict[str, List[str]]:
    if not path.is_file():
        return {}
    data = load_json(path)
    m = data.get("map") or {}
    out: Dict[str, List[str]] = {}
    for k, v in m.items():
        if isinstance(v, list):
            out[str(k)] = [str(x) for x in v]
        elif isinstance(v, str):
            out[str(k)] = [v]
    # Also support no-space lookup (e.g. "매운고추" -> "매운 고추").
    normalized: Dict[str, List[str]] = {}
    for k, vals in out.items():
        nk = re.sub(r"\s+", "", str(k)).strip()
        if not nk:
            continue
        normalized.setdefault(nk, [])
        for term in vals:
            t = str(term).strip()
            if t and t not in normalized[nk]:
                normalized[nk].append(t)
    for nk, vals in normalized.items():
        out.setdefault(nk, [])
        for term in vals:
            if term not in out[nk]:
                out[nk].append(term)
    return out


def search_terms_for_entry(entry: Dict[str, Any], seed: Dict[str, List[str]]) -> List[str]:
    direct = entry.get("search_en") or []
    if isinstance(direct, list) and direct:
        return _unique_terms([str(x) for x in direct])
    syn = entry.get("synonyms_ko") or []
    # Fallback candidates when search_en is empty.
    fallback_ko: List[str] = [str(x) for x in syn]
    for extra in (entry.get("visual_base_ko"), entry.get("normalized_name"), entry.get("display_name")):
        if extra:
            fallback_ko.append(str(extra))
    terms: List[str] = []
    for ko in fallback_ko:
        key = str(ko).strip()
        if not key:
            continue
        terms.extend(seed.get(key, []))
        terms.extend(seed.get(re.sub(r"\s+", "", key), []))
    return _unique_terms(terms)


def _unique_terms(xs: List[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for x in xs:
        t = x.strip()
        if not t:
            continue
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out


def order_queries_short_first(queries: List[str]) -> List[str]:
    """Try shorter English phrases first (often better hit rate on image search)."""
    return sorted(queries, key=lambda q: (len(q.split()), len(q)))


def expand_queries_for_diversity(base_queries: List[str]) -> List[str]:
    """Add packaging/cooking-style variants per phrase (e.g. oyster sauce → bottle, jar, …)."""
    chunks: List[str] = []
    for b in base_queries:
        t = b.strip()
        if not t:
            continue
        chunks.append(t)
        low = t.lower()
        for suf in _QUERY_DIVERSITY_SUFFIXES:
            cand = (t + suf).strip()
            if cand.lower() != low:
                chunks.append(cand)
    return _unique_terms(chunks)


def class_shuffle_seed(folder: str, user_seed: int) -> int:
    h = hashlib.sha256(f"{user_seed}:{folder}".encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big")


def _is_ddgs_ratelimit(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "403" in msg or "ratelimit" in msg or "rate limit" in msg


def ddgs_fetch_with_retry(
    q: str,
    max_results: int,
    safesearch: str,
    delay_ddgs: float,
    ratelimit_sleep: float,
) -> List[str]:
    for attempt in range(5):
        try:
            return ddgs_image_urls(q, max_results=max_results, safesearch=safesearch)
        except Exception as exc:
            if attempt < 4:
                if _is_ddgs_ratelimit(exc):
                    time.sleep(ratelimit_sleep * (1 + attempt * 0.5))
                else:
                    time.sleep(delay_ddgs * (2 + attempt))
            else:
                print(json.dumps({"ddgs_error": str(exc), "query": q}, ensure_ascii=False))
    return []


def count_images_in_dir(dir_path: Path) -> int:
    if not dir_path.is_dir():
        return 0
    n = 0
    for p in dir_path.rglob("*"):
        if p.is_file() and p.suffix.lower() in _IMAGE_EXT:
            n += 1
    return n


def train_count(out_root: Path, folder: str) -> int:
    return count_images_in_dir(out_root / "train" / folder)


def save_image_jpeg(body: bytes, dest_jpg: Path) -> bool:
    dest_jpg.parent.mkdir(parents=True, exist_ok=True)
    if _HAS_PIL:
        try:
            im = Image.open(io.BytesIO(body))
            im.load()
            if im.mode in ("P", "LA", "PA"):
                im = im.convert("RGBA")
            if im.mode == "RGBA":
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[3])
                im = bg
            elif im.mode != "RGB":
                im = im.convert("RGB")
            im.save(dest_jpg, format="JPEG", quality=90)
            return True
        except Exception:
            return False
    if len(body) < 2048 or body[:4] in (b"<htm", b"<!DO", b"<HTML"):
        return False
    dest_jpg.write_bytes(body)
    return True


def download_one(url: str, dest_jpg: Path, timeout: float) -> bool:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; TodayFridgeIngredientBot/1.0; +edu-research)",
        "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
    }
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
            r = client.get(url)
            if r.status_code != 200:
                return False
            return save_image_jpeg(r.content, dest_jpg)
    except Exception:
        return False


def ddgs_image_urls(query: str, max_results: int, safesearch: str) -> List[str]:
    urls: List[str] = []
    with DDGS() as ddgs:
        if _DDGS_USE_LEGACY_KWARGS:
            gen = ddgs.images(
                keywords=query,
                region="wt-wt",
                safesearch=safesearch,
                max_results=max_results,
            )
        else:
            gen = ddgs.images(
                query,
                region="wt-wt",
                safesearch=safesearch,
                max_results=max_results,
            )
        if not gen:
            return urls
        for item in gen:
            u = item.get("image") or item.get("url")
            if u and isinstance(u, str) and u.startswith("http"):
                urls.append(u)
    return urls


def safe_name_hint(q: str) -> str:
    return re.sub(r"[^\w\-]+", "_", q)[:40].strip("_") or "q"


def load_packaged_exclude_folders(path: Path) -> Set[str]:
    """Read model_folder list from packaged proposal JSON (85 + borderline 25 = 110 when both present)."""
    if not path.is_file():
        return set()
    doc = load_json(path)
    out: Set[str] = set()
    for item in doc.get("proposed_packaged") or []:
        f = item.get("model_folder")
        if f:
            out.add(str(f))
    for item in doc.get("borderline_for_team") or []:
        f = item.get("model_folder")
        if f:
            out.add(str(f))
    return out


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(description="Fetch ingredient images via DuckDuckGo image search")
    parser.add_argument("--aliases-json", type=Path, default=_DATA / "ingredient_image_search_aliases.json")
    parser.add_argument("--seed-json", type=Path, default=_DATA / "ko_to_en_image_search_seed.json")
    parser.add_argument("--out-root", type=Path, default=Path("data_sources/team_uploads"))
    parser.add_argument(
        "--target-per-class",
        type=int,
        default=200,
        help="max new images to fetch per class this run (train only; capped by room under --max-per-class)",
    )
    parser.add_argument(
        "--max-per-class",
        type=int,
        default=200,
        help="hard ceiling for train/ing_XXX image count; at/above cap skip class; stop mid-class when cap reached",
    )
    parser.add_argument(
        "--ddgs-per-query",
        type=int,
        default=90,
        help="max DDG image results to scan per query",
    )
    parser.add_argument(
        "--skip-if-gte",
        type=int,
        default=0,
        help="if a folder already has this many images in train, skip the class (0 = use --max-per-class as threshold)",
    )
    parser.add_argument("--max-classes", type=int, default=0, help="0 = all entries in JSON; else cap for testing")
    parser.add_argument("--delay-ddgs", type=float, default=1.25, help="seconds between DDG searches")
    parser.add_argument(
        "--ddgs-ratelimit-sleep",
        type=float,
        default=80.0,
        help="extra sleep (seconds) after DuckDuckGo 403/ratelimit before retry (scales up per retry)",
    )
    parser.add_argument("--delay-download", type=float, default=0.35, help="seconds between HTTP downloads")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--safesearch", choices=["off", "moderate", "on"], default="moderate")
    parser.add_argument(
        "--short-queries-first",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="order base English phrases by length before expanding variants",
    )
    parser.add_argument(
        "--expand-queries",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="add bottle/jar/cooking/… variants per phrase for more diverse images",
    )
    parser.add_argument(
        "--shuffle-queries",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="shuffle expanded queries per class (spread hits across variants)",
    )
    parser.add_argument(
        "--shuffle-seed",
        type=int,
        default=1337,
        help="RNG seed mixed with folder id when --shuffle-queries",
    )
    parser.add_argument(
        "--max-stagnant-waves",
        type=int,
        default=12,
        help="stop a class after this many round-robin waves with no new saves",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--packaged-exclude-json",
        type=Path,
        default=_DATA / "packaged_ingredient_proposal.json",
        help="packaged_ingredient_proposal_v1 JSON; see excludeFromWebFetch / --apply-packaged-exclude",
    )
    parser.add_argument(
        "--apply-packaged-exclude",
        action="store_true",
        help="skip classes listed in packaged proposal JSON (without setting excludeFromWebFetch)",
    )
    parser.add_argument(
        "--only-folders",
        default="",
        help="comma-separated ing_XXXXX; if non-empty, only those classes are processed",
    )
    parser.add_argument(
        "--only-folders-file",
        type=Path,
        default=None,
        help="text file: one ing_XXXXX per line (or comma-separated line); merged with --only-folders",
    )
    args = parser.parse_args()

    if args.max_per_class < 1:
        print("--max-per-class must be >= 1", file=sys.stderr)
        sys.exit(2)
    if args.target_per_class < 0:
        print("--target-per-class must be >= 0", file=sys.stderr)
        sys.exit(2)
    cap = args.max_per_class
    _skip = args.skip_if_gte if args.skip_if_gte > 0 else cap
    effective_skip = min(cap, _skip)

    if not args.aliases_json.is_file():
        print(f"Missing {args.aliases_json} — run export_ingredient_image_alias_template.py first", file=sys.stderr)
        sys.exit(2)

    doc = load_json(args.aliases_json)
    entries: List[Dict[str, Any]] = doc.get("entries") or []
    seed = load_ko_en_seed(args.seed_json)

    packaged_skip: Set[str] = set()
    if args.packaged_exclude_json.is_file():
        pdoc = load_json(args.packaged_exclude_json)
        if pdoc.get("excludeFromWebFetch") or args.apply_packaged_exclude:
            packaged_skip = load_packaged_exclude_folders(args.packaged_exclude_json)

    alias_folders = {
        str(e.get("model_folder") or "")
        for e in entries
        if str(e.get("model_folder") or "").startswith("ing_")
    }

    stats = {"classes": 0, "downloaded": 0, "skipped_class": 0, "failed_queries": 0, "skipped_packaged": 0}
    processed = 0
    only_folders = {x.strip() for x in str(args.only_folders).split(",") if x.strip()}
    if args.only_folders_file and args.only_folders_file.is_file():
        for raw in args.only_folders_file.read_text(encoding="utf-8").splitlines():
            for part in raw.split(","):
                p = part.strip()
                if p.startswith("ing_"):
                    only_folders.add(p)

    explicit_fetch = bool(only_folders)
    print(
        json.dumps(
            {
                "info": "fetch_config",
                "out_root": str(args.out_root.resolve()),
                "cap": cap,
                "effective_skip": effective_skip,
                "target_per_class": args.target_per_class,
                "only_folders": len(only_folders) if only_folders else None,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    if packaged_skip:
        stale = sorted(packaged_skip - alias_folders)
        if stale:
            if explicit_fetch:
                overlap = sorted(packaged_skip & only_folders)
                print(
                    json.dumps(
                        {
                            "info": "packaged_exclude_vs_subset_aliases",
                            "detail": "packaged_ingredient_proposal.json lists many IDs that are not rows in this aliases JSON — expected when aliases are the 122-class subset. Those IDs are irrelevant for this run. Classes in --only-folders / --only-folders-file still download (packaged skip overridden for them).",
                            "packaged_ids_not_in_this_aliases_file": len(stale),
                            "packaged_skip_also_in_only_folders_overridden": overlap,
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
            else:
                print(
                    json.dumps(
                        {
                            "warn": "packaged_exclude_has_stale_folders",
                            "detail": "IDs in packaged proposal but not in ingredient_image_search_aliases JSON (e.g. after DB merge). Regen: gen_packaged_ingredient_proposal.py",
                            "stale": stale,
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

    for entry in entries:
        folder = str(entry.get("model_folder") or "")
        if not folder.startswith("ing_"):
            continue
        if only_folders and folder not in only_folders:
            continue
        if folder in packaged_skip and not (explicit_fetch and folder in only_folders):
            stats["skipped_packaged"] += 1
            stats["skipped_class"] += 1
            continue
        train_live = train_count(args.out_root, folder)
        if train_live >= effective_skip:
            print(
                json.dumps(
                    {
                        "info": "skip_train_at_threshold",
                        "folder": folder,
                        "train_count": train_live,
                        "effective_skip": effective_skip,
                        "cap": cap,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            stats["skipped_class"] += 1
            continue

        room = max(0, cap - train_live)
        need = min(args.target_per_class, room)
        if need <= 0:
            stats["skipped_class"] += 1
            continue

        queries = search_terms_for_entry(entry, seed)
        if args.short_queries_first:
            queries = order_queries_short_first(queries)
        if args.expand_queries:
            queries = expand_queries_for_diversity(queries)
        if args.shuffle_queries and queries:
            rng = random.Random(class_shuffle_seed(folder, args.shuffle_seed))
            rng.shuffle(queries)
        if not queries:
            print(json.dumps({"warn": "no search terms", "folder": folder, "nn": entry.get("normalized_name")}, ensure_ascii=False))
            stats["failed_queries"] += 1
            continue

        if args.dry_run:
            print(json.dumps({"dry": folder, "queries_preview": queries[:12], "n_queries": len(queries)}, ensure_ascii=False))
            processed += 1
            if args.max_classes and processed >= args.max_classes:
                break
            continue

        got = 0
        seen_urls: Set[str] = set()
        url_queues: Dict[str, Deque[str]] = {q: deque() for q in queries}
        stagnant_waves = 0

        while got < need and stagnant_waves < args.max_stagnant_waves and train_live < cap:
            wave_saved = 0
            for q in queries:
                if got >= need or train_live >= cap:
                    break
                if not url_queues[q]:
                    time.sleep(args.delay_ddgs)
                    for u in ddgs_fetch_with_retry(
                        q,
                        args.ddgs_per_query,
                        args.safesearch,
                        args.delay_ddgs,
                        args.ddgs_ratelimit_sleep,
                    ):
                        url_queues[q].append(u)
                url = None
                while url_queues[q]:
                    cand = url_queues[q].popleft()
                    if cand not in seen_urls:
                        url = cand
                        break
                if not url:
                    continue
                seen_urls.add(url)
                qh = safe_name_hint(q)
                h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
                fname = f"ddgs_{qh}_{got + 1}_{h}.jpg"
                dest = args.out_root / "train" / folder / fname
                time.sleep(args.delay_download)
                if download_one(url, dest, args.timeout):
                    got += 1
                    train_live += 1
                    stats["downloaded"] += 1
                    wave_saved += 1
                    if train_live >= cap:
                        break
            if wave_saved == 0:
                stagnant_waves += 1
            else:
                stagnant_waves = 0

        if got < need:
            print(
                json.dumps(
                    {
                        "warn": "class_shortfall",
                        "folder": folder,
                        "saved": got,
                        "needed": need,
                        "reason": f"no new images for {args.max_stagnant_waves} stagnant wave(s) or queries exhausted",
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

        stats["classes"] += 1
        print(
            json.dumps(
                {
                    "folder": folder,
                    "normalized_name": entry.get("normalized_name"),
                    "saved": got,
                    "train_count_after": train_live,
                    "queries_preview": queries[:8],
                    "n_queries": len(queries),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

        processed += 1
        if args.max_classes and processed >= args.max_classes:
            break

    print(json.dumps({"done": True, "stats": stats}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
