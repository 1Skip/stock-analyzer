"""Low-coupling path, cache and stock-name helpers for data_fetcher."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from config import RUNTIME_CACHE_DIR


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def runtime_cache_path(filename: str) -> str:
    cache_dir = RUNTIME_CACHE_DIR or str(PROJECT_ROOT)
    return os.path.join(cache_dir, filename)


def static_data_path(filename: str) -> str:
    return str(PROJECT_ROOT / "data" / "static" / filename)


def legacy_cache_path(filename: str) -> str:
    return str(PROJECT_ROOT / filename)


def ensure_parent_dir(path: str | os.PathLike[str]) -> None:
    parent = os.path.dirname(str(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def read_json_cache(primary_file: str, legacy_filename: str | None = None) -> tuple[Any, str | None]:
    candidates = [primary_file]
    if legacy_filename:
        legacy_file = legacy_cache_path(legacy_filename)
        if legacy_file != primary_file:
            candidates.append(legacy_file)

    for cache_file in candidates:
        if not os.path.exists(cache_file):
            continue
        with open(cache_file, "r", encoding="utf-8") as file:
            return json.load(file), cache_file
    return None, None


def normalize_stock_name(name: Any) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(name))).upper()


def clean_stock_name(name: Any) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(name)))


def stock_name_similarity(query: Any, candidate: Any) -> float:
    normalized_query = normalize_stock_name(query)
    normalized_candidate = normalize_stock_name(candidate)
    if not normalized_query or not normalized_candidate:
        return 0.0
    ratio = SequenceMatcher(None, normalized_query, normalized_candidate).ratio()
    if (
        len(normalized_query) >= 3
        and len(normalized_candidate) >= 3
        and sorted(normalized_query) == sorted(normalized_candidate)
    ):
        ratio = max(ratio, 0.95)
    return ratio
