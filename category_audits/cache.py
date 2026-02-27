"""24-hour JSON cache for SmartScout data pulls.

Cache key: {report_type}_{brand_or_category}_{marketplace}_{date}
Stored in src/category_audits/cache/ as JSON files.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .models import (
    AsinRecord,
    BrandRecord,
    CategoryAuditData,
    SearchTermRecord,
)

_CACHE_DIR = Path(__file__).parent / "cache"
_CACHE_TTL_HOURS = 24


def _cache_key(
    report_type: str,
    brand: Optional[str],
    category: Optional[str],
    marketplace: str,
) -> str:
    """Build a filesystem-safe cache key."""
    raw = f"{report_type}_{brand or ''}_{category or ''}_{marketplace}"
    safe = raw.lower().replace(" ", "_")
    # Add date (YYYY-MM-DD) so cache rolls over daily
    date_str = datetime.now().strftime("%Y-%m-%d")
    return f"{safe}_{date_str}"


def _cache_path(key: str) -> Path:
    return _CACHE_DIR / f"{key}.json"


def load_cached(
    report_type: str,
    brand: Optional[str],
    category: Optional[str],
    marketplace: str,
) -> Optional[CategoryAuditData]:
    """Load cached data if it exists and is within TTL."""
    key = _cache_key(report_type, brand, category, marketplace)
    path = _cache_path(key)

    if not path.exists():
        return None

    # Check TTL
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    if datetime.now() - mtime > timedelta(hours=_CACHE_TTL_HOURS):
        print(f"[cache] Expired: {path.name}")
        path.unlink(missing_ok=True)
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        data = _deserialize(raw)
        age_min = (datetime.now() - mtime).total_seconds() / 60
        print(f"[cache] Hit: {path.name} ({age_min:.0f} min old)")
        return data
    except Exception as e:
        print(f"[cache] Error loading {path.name}: {e}")
        path.unlink(missing_ok=True)
        return None


def save_cache(data: CategoryAuditData):
    """Save data to cache."""
    key = _cache_key(
        data.report_type,
        data.target_brand,
        data.category_name if data.report_type == "buyer" else None,
        data.marketplace,
    )
    path = _cache_path(key)
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    raw = _serialize(data)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, default=str)
    print(f"[cache] Saved: {path.name}")


def _serialize(data: CategoryAuditData) -> dict:
    """Convert CategoryAuditData to JSON-serializable dict."""
    d = asdict(data)
    # datetime → ISO string
    d["data_pulled_at"] = data.data_pulled_at.isoformat()
    return d


def _deserialize(raw: dict) -> CategoryAuditData:
    """Reconstruct CategoryAuditData from JSON dict."""
    brands = [BrandRecord(**b) for b in raw.get("brands", [])]
    top_asins = [AsinRecord(**a) for a in raw.get("top_asins", [])]
    brand_asins = (
        [AsinRecord(**a) for a in raw["brand_asins"]]
        if raw.get("brand_asins")
        else None
    )
    search_terms = [SearchTermRecord(**t) for t in raw.get("search_terms", [])]

    return CategoryAuditData(
        report_type=raw["report_type"],
        target_brand=raw.get("target_brand"),
        category_name=raw["category_name"],
        subcategory_name=raw["subcategory_name"],
        subcategory_id=raw.get("subcategory_id"),
        retailer=raw.get("retailer"),
        marketplace=raw["marketplace"],
        data_pulled_at=datetime.fromisoformat(raw["data_pulled_at"]),
        brands=brands,
        top_asins=top_asins,
        brand_asins=brand_asins,
        search_terms=search_terms,
        total_category_revenue_ttm=raw.get("total_category_revenue_ttm", 0),
        total_category_revenue_prior=raw.get("total_category_revenue_prior"),
        yoy_growth_pct=raw.get("yoy_growth_pct", 0),
    )
