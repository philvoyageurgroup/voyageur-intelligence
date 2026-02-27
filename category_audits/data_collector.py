"""SmartScout data collection for Category Audit reports.

Pulls brand landscape, ASIN data, search terms, and (for buyer reports)
historical share data from SmartScout API.

NOTE: The smartscout-api SDK's Pydantic serialization is broken (enum values
serialize as repr strings, sort/page use bracket aliases that don't round-trip).
We call client._make_request() directly with raw dicts to bypass this.

Actual API response fields use camelCase and differ from SDK model definitions:
  - Brands: brandName, trailing12Months, monthGrowth12, subcategoryId, etc.
  - Products: brandName, monthlyRevenueEstimate, buyBoxPrice (plain floats), subcategoryId (direct)
  - Search terms: searchTermValue, estimateSearches, brands (int count, not list)
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from smartscout import SmartScoutAPIClient

from .models import (
    AsinRecord,
    BrandRecord,
    CategoryAuditData,
    SearchTermRecord,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COURTESY_DELAY = 1.0  # SmartScout rate limits aggressively


def _gf(d: dict, key: str, default=0.0) -> float:
    v = d.get(key)
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _gi(d: dict, key: str, default=0) -> int:
    v = d.get(key)
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Raw API wrapper
# ---------------------------------------------------------------------------


class _SmartScoutRaw:
    """Thin wrapper calling SmartScoutAPIClient._make_request directly.

    Sort/page go in query params (bracket notation), filters go in JSON body.
    """

    def __init__(self, api_key: str):
        self._client = SmartScoutAPIClient(api_key=api_key)

    def post(
        self,
        endpoint: str,
        body: Dict[str, Any],
        marketplace: str = "US",
        sort_by: Optional[str] = None,
        sort_order: str = "desc",
        page_size: int = 100,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"marketplace": marketplace}
        if sort_by:
            params["sort[by]"] = sort_by
            params["sort[order]"] = sort_order
        params["page[size]"] = page_size

        for attempt in range(3):
            try:
                return self._client._make_request(
                    "POST", endpoint, data=body, params=params
                )
            except Exception as e:
                if "rate limit" in str(e).lower() or "429" in str(e):
                    wait = 2 ** (attempt + 1)
                    print(f"  Rate limited, waiting {wait}s (attempt {attempt + 1}/3)")
                    time.sleep(wait)
                else:
                    raise
        return self._client._make_request(
            "POST", endpoint, data=body, params=params
        )


# ---------------------------------------------------------------------------
# Main collector
# ---------------------------------------------------------------------------


class CategoryDataCollector:
    """Collects all SmartScout data needed for a category audit report."""

    def __init__(self, marketplace: str = "US"):
        load_dotenv(override=True)
        api_key = os.getenv("SMARTSCOUT_API_KEY")
        if not api_key:
            raise RuntimeError("SMARTSCOUT_API_KEY not found in environment")
        self.api = _SmartScoutRaw(api_key)
        self.marketplace = marketplace

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def collect(
        self,
        report_type: str,
        brand_name: Optional[str] = None,
        category_name: Optional[str] = None,
        retailer: Optional[str] = None,
    ) -> CategoryAuditData:
        print(f"[collect] Starting {report_type} report data pull...")

        subcategory_name = ""
        subcategory_id = None
        resolved_category = category_name or ""

        if brand_name:
            print(f"[Step 1] Looking up brand: {brand_name}")
            brand_info, subcategory_name, resolved_category, subcategory_id = (
                self._resolve_brand(brand_name)
            )

        if category_name and not subcategory_name:
            subcategory_name = category_name

        # Step 2: Brands in subcategory
        print(f"[Step 2] Pulling brands in subcategory: {subcategory_name}")
        time.sleep(_COURTESY_DELAY)
        brand_records, total_ttm = self._pull_brands_in_subcategory(subcategory_name)

        # Step 3: Top 50 ASINs — also extracts subcategory_id if not yet resolved
        print("[Step 3] Pulling top ASINs in subcategory...")
        time.sleep(_COURTESY_DELAY)
        top_asins, resolved_subcat_id = self._pull_top_asins(subcategory_name)
        if not subcategory_id and resolved_subcat_id:
            subcategory_id = resolved_subcat_id

        # Step 4: Historical share deltas (buyer reports only)
        # NOTE: /brands/history/sales returns 404 on current SmartScout plan.
        # Fallback: estimate share deltas from monthGrowth12 vs category avg.
        prior_total = None
        if report_type == "buyer":
            print("[Step 4] Estimating share deltas from YoY growth rates...")
            brand_records = self._estimate_share_deltas(brand_records, total_ttm)
        else:
            print(f"[Step 4] Skipping history (report_type={report_type})")

        # Step 5: Brand's own ASINs (brand report only)
        brand_asins = None
        if report_type == "brand" and brand_name:
            print(f"[Step 5] Pulling {brand_name}'s own ASIN portfolio...")
            time.sleep(_COURTESY_DELAY)
            brand_asins = self._pull_brand_asins(brand_name)
        else:
            print(f"[Step 5] Skipping brand ASINs (report_type={report_type})")

        # Step 6: Search terms
        print("[Step 6] Pulling search terms...")
        time.sleep(_COURTESY_DELAY)
        search_terms = self._pull_search_terms(subcategory_name)

        yoy_growth = self._compute_weighted_yoy(brand_records, total_ttm)

        data = CategoryAuditData(
            report_type=report_type,
            target_brand=brand_name,
            category_name=resolved_category,
            subcategory_name=subcategory_name,
            subcategory_id=subcategory_id,
            retailer=retailer,
            marketplace=self.marketplace,
            data_pulled_at=datetime.now(),
            brands=brand_records,
            top_asins=top_asins,
            brand_asins=brand_asins,
            search_terms=search_terms,
            total_category_revenue_ttm=total_ttm,
            total_category_revenue_prior=prior_total,
            yoy_growth_pct=yoy_growth,
        )

        print(
            f"[collect] Done. {len(brand_records)} brands, "
            f"{len(top_asins)} ASINs, {len(search_terms)} search terms."
        )
        return data

    # ------------------------------------------------------------------
    # Step 1: Brand lookup
    # ------------------------------------------------------------------

    def _resolve_brand(self, brand_name: str):
        """Look up brand → (dict, subcategory_name, category_name, subcategory_id)."""
        body = {"brandName": {"type": "contains", "filter": brand_name}}
        resp = self.api.post(
            "/brands/search",
            body,
            self.marketplace,
            sort_by="trailing12Months",
            page_size=10,
        )
        items = resp.get("data", [])

        if not items:
            raise ValueError(
                f"No brand found matching '{brand_name}' in SmartScout"
            )

        # Find best match — prefer exact name match, fallback to highest TTM
        target = items[0]
        for item in items:
            if (item.get("brandName") or "").lower() == brand_name.lower():
                target = item
                break

        subcat = target.get("subcategoryName") or ""
        cat = target.get("categoryName") or ""
        subcat_id = target.get("subcategoryId")
        ttm = _gf(target, "trailing12Months")
        print(
            f"  Found: {target.get('brandName')} → "
            f"subcategory='{subcat}', category='{cat}', "
            f"subcategoryId={subcat_id}"
        )
        print(f"  TTM revenue: ${ttm:,.0f}")
        return target, subcat, cat, str(subcat_id) if subcat_id else None

    # ------------------------------------------------------------------
    # Step 2: All brands in subcategory
    # ------------------------------------------------------------------

    def _pull_brands_in_subcategory(
        self, subcategory_name: str
    ) -> tuple[List[BrandRecord], float]:
        body = {
            "subcategoryName": {"type": "exact", "filter": subcategory_name}
        }
        resp = self.api.post(
            "/brands/search",
            body,
            self.marketplace,
            sort_by="trailing12Months",
            page_size=100,
        )
        items = resp.get("data", [])

        if not items:
            print(
                f"  WARNING: No brands found for subcategory '{subcategory_name}'"
            )
            return [], 0.0

        total_ttm = sum(_gf(b, "trailing12Months") for b in items)
        print(f"  Found {len(items)} brands, total TTM=${total_ttm:,.0f}")

        records = []
        for b in items:
            ttm = _gf(b, "trailing12Months")
            records.append(
                BrandRecord(
                    name=b.get("brandName") or "",
                    monthly_revenue=_gf(b, "monthlyRevenue"),
                    trailing_12_months=ttm,
                    share_pct=(ttm / total_ttm * 100) if total_ttm > 0 else 0.0,
                    month_growth_12=_gf(b, "monthGrowth12"),
                    share_delta_bp=None,
                    total_products=_gi(b, "totalProducts"),
                    avg_price=_gf(b, "avgPrice"),
                    review_rating=_gf(b, "reviewRating"),
                )
            )

        return records, total_ttm

    # ------------------------------------------------------------------
    # Step 3: Top ASINs + subcategory_id
    # ------------------------------------------------------------------

    def _pull_top_asins(
        self, subcategory_name: str
    ) -> tuple[List[AsinRecord], Optional[str]]:
        body = {
            "subcategoryName": {"type": "exact", "filter": subcategory_name}
        }
        resp = self.api.post(
            "/products/search",
            body,
            self.marketplace,
            sort_by="monthlyRevenueEstimate",
            page_size=50,
        )
        items = resp.get("data", [])

        subcategory_id = None
        if items:
            sid = items[0].get("subcategoryId")
            if sid:
                subcategory_id = str(sid)
                print(f"  Resolved subcategory_id={subcategory_id}")

        records = [self._dict_to_asin(p) for p in items]
        print(f"  Found {len(records)} ASINs")
        return records, subcategory_id

    # ------------------------------------------------------------------
    # Step 4: Share delta estimation
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_share_deltas(
        brand_records: List[BrandRecord],
        total_ttm: float,
    ) -> List[BrandRecord]:
        """Estimate share deltas from YoY growth rates.

        /brands/history/sales returns 404 on current SmartScout plan.
        Fallback: if a brand grew faster than category average, it gained
        share; if slower, it lost share. We estimate the prior-year share
        from: prior_rev = ttm / (1 + growth_rate), then compute delta.
        """
        if not brand_records or total_ttm <= 0:
            return brand_records

        # Estimate each brand's prior-year revenue
        prior_revs = {}
        for b in brand_records:
            growth = b.month_growth_12 / 100 if b.month_growth_12 else 0
            prior = b.trailing_12_months / (1 + growth) if growth > -1 else b.trailing_12_months
            prior_revs[b.name] = prior

        total_prior = sum(prior_revs.values())

        for b in brand_records:
            share_now = (b.trailing_12_months / total_ttm * 100) if total_ttm > 0 else 0
            share_prior = (prior_revs[b.name] / total_prior * 100) if total_prior > 0 else 0
            b.share_delta_bp = (share_now - share_prior) * 100  # basis points

        gainers = sum(1 for b in brand_records if (b.share_delta_bp or 0) > 10)
        losers = sum(1 for b in brand_records if (b.share_delta_bp or 0) < -10)
        print(f"  Estimated share deltas: {gainers} gainers, {losers} losers")
        return brand_records

    # ------------------------------------------------------------------
    # Step 5: Brand's own ASINs
    # ------------------------------------------------------------------

    def _pull_brand_asins(self, brand_name: str) -> List[AsinRecord]:
        body = {"brandName": {"type": "exact", "filter": brand_name}}
        resp = self.api.post(
            "/products/search",
            body,
            self.marketplace,
            sort_by="monthlyRevenueEstimate",
            page_size=100,
        )
        items = resp.get("data", [])
        records = [self._dict_to_asin(p) for p in items]
        print(f"  Found {len(records)} ASINs for brand '{brand_name}'")
        return records

    # ------------------------------------------------------------------
    # Step 6: Search terms
    # ------------------------------------------------------------------

    def _pull_search_terms(self, subcategory_name: str) -> List[SearchTermRecord]:
        # Build a specific search seed from the subcategory name
        # e.g. "Free Standing Shoe Racks" → "shoe rack" (skip generic words)
        stop_words = {
            "and", "the", "for", "with", "of", "in", "on", "to", "a", "an",
            "free", "standing", "mounted", "wall", "hanging", "portable",
            "electric", "manual", "small", "large", "mini", "other",
        }
        meaningful = [
            w.lower()
            for w in subcategory_name.split()
            if len(w) > 2 and w.lower() not in stop_words
        ]
        # Use last 1-2 meaningful words (usually the noun core)
        if len(meaningful) >= 2:
            seed = " ".join(meaningful[-2:])
        elif meaningful:
            seed = meaningful[-1]
        else:
            seed = subcategory_name.lower()

        if not seed:
            print("  WARNING: No seed term for search — skipping")
            return []

        # Pull with multi-word seed, then broaden with single-word seed
        seeds = [seed]
        if " " in seed:
            seeds.append(seed.split()[-1])  # e.g. "racks" from "shoe racks"

        all_items: dict[str, dict] = {}  # dedupe by term
        for s in seeds:
            print(f"  Search seed: '{s}'")
            body = {
                "searchTermValue": {"type": "contains", "filter": s},
                "estimateSearches": {"min": 500},
            }
            resp = self.api.post(
                "/search-terms/search",
                body,
                self.marketplace,
                sort_by="estimateSearches",
                page_size=50,
            )
            for t in resp.get("data", []):
                term = t.get("searchTermValue") or ""
                if term and term not in all_items:
                    all_items[term] = t
            time.sleep(_COURTESY_DELAY)

        items = list(all_items.values())

        # Sort by volume descending, take top 30
        items_sorted = sorted(
            items,
            key=lambda t: _gi(t, "estimateSearches"),
            reverse=True,
        )[:30]

        records = []
        for t in items_sorted:
            records.append(
                SearchTermRecord(
                    term=t.get("searchTermValue") or "",
                    monthly_volume=_gi(t, "estimateSearches"),
                    brands=[],  # API returns brand count (int), not list
                    cpc=_gf(t, "estimatedCpc"),
                )
            )
        print(f"  Found {len(records)} search terms (min 500 vol)")
        return records

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _dict_to_asin(p: dict) -> AsinRecord:
        return AsinRecord(
            asin=p.get("asin") or "",
            title=p.get("title") or "",
            brand=p.get("brandName") or "",
            price=_gf(p, "buyBoxPrice"),
            monthly_revenue_est=_gf(p, "monthlyRevenueEstimate"),
            monthly_units_est=_gi(p, "monthlyUnitsSold"),
            review_count=_gi(p, "reviewCount"),
            review_rating=_gf(p, "reviewRating"),
            subcategory_name=p.get("subcategoryName") or "",
            subcategory_id=str(p.get("subcategoryId") or ""),
        )

    @staticmethod
    def _compute_weighted_yoy(
        brands: List[BrandRecord], total_ttm: float
    ) -> float:
        if not brands or total_ttm <= 0:
            return 0.0
        weighted_sum = sum(
            b.month_growth_12 * b.trailing_12_months for b in brands
        )
        return weighted_sum / total_ttm
