"""Dataclasses for Category Audit pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class BrandRecord:
    name: str
    monthly_revenue: float          # current month estimate
    trailing_12_months: float       # TTM revenue (primary metric)
    share_pct: float                # computed: brand TTM / total TTM * 100
    month_growth_12: float          # YoY growth % (from SDK directly)
    share_delta_bp: Optional[float] # basis points vs prior 12mo (buyer reports only)
    total_products: int
    avg_price: float
    review_rating: float


@dataclass
class AsinRecord:
    asin: str
    title: str
    brand: str
    price: float                    # from buy_box_price.amount
    monthly_revenue_est: float      # from estimated_monthly_revenue.amount
    monthly_units_est: int          # estimated_monthly_sales
    review_count: int               # from reviews.total_reviews
    review_rating: float            # from reviews.average_rating
    subcategory_name: str
    subcategory_id: str             # from subcategory.id


@dataclass
class SearchTermRecord:
    term: str                       # search_term
    monthly_volume: int             # search_volume
    brands: List[str]               # brands that appear for this term
    cpc: float


@dataclass
class CategoryAuditData:
    report_type: str                # "prospect", "brand", "buyer"
    target_brand: Optional[str]
    category_name: str
    subcategory_name: str
    subcategory_id: Optional[str]
    retailer: Optional[str]
    marketplace: str
    data_pulled_at: datetime

    brands: List[BrandRecord] = field(default_factory=list)
    top_asins: List[AsinRecord] = field(default_factory=list)
    brand_asins: Optional[List[AsinRecord]] = None

    search_terms: List[SearchTermRecord] = field(default_factory=list)

    total_category_revenue_ttm: float = 0.0
    total_category_revenue_prior: Optional[float] = None
    yoy_growth_pct: float = 0.0

    def summary(self) -> str:
        """Human-readable summary for --dry-run output."""
        lines = [
            f"=== Category Audit Data ({self.report_type}) ===",
            f"Target brand:    {self.target_brand or '(none)'}",
            f"Category:        {self.category_name}",
            f"Subcategory:     {self.subcategory_name}",
            f"Subcategory ID:  {self.subcategory_id or '(not resolved)'}",
            f"Retailer:        {self.retailer or '(none)'}",
            f"Marketplace:     {self.marketplace}",
            f"Pulled at:       {self.data_pulled_at:%Y-%m-%d %H:%M}",
            "",
            f"--- Category Financials ---",
            f"TTM Revenue:          ${self.total_category_revenue_ttm:,.0f}",
            f"Prior 12mo Revenue:   {'${:,.0f}'.format(self.total_category_revenue_prior) if self.total_category_revenue_prior is not None else '(not computed)'}",
            f"YoY Growth:           {self.yoy_growth_pct:+.1f}%",
            "",
            f"--- Brands ({len(self.brands)}) ---",
        ]
        for i, b in enumerate(self.brands[:15], 1):
            delta = f"  delta={b.share_delta_bp:+.0f}bp" if b.share_delta_bp is not None else ""
            lines.append(
                f"  {i:>2}. {b.name:<30s}  TTM=${b.trailing_12_months:>12,.0f}  "
                f"share={b.share_pct:5.1f}%  YoY={b.month_growth_12:+.1f}%{delta}"
            )
        if len(self.brands) > 15:
            lines.append(f"  ... and {len(self.brands) - 15} more brands")

        lines.append(f"\n--- Top ASINs ({len(self.top_asins)}) ---")
        for i, a in enumerate(self.top_asins[:10], 1):
            lines.append(
                f"  {i:>2}. {a.asin}  ${a.monthly_revenue_est:>10,.0f}/mo  "
                f"{a.brand:<20s}  {a.title[:50]}"
            )
        if len(self.top_asins) > 10:
            lines.append(f"  ... and {len(self.top_asins) - 10} more ASINs")

        if self.brand_asins is not None:
            lines.append(f"\n--- Brand ASINs ({len(self.brand_asins)}) ---")
            for i, a in enumerate(self.brand_asins[:10], 1):
                lines.append(
                    f"  {i:>2}. {a.asin}  ${a.monthly_revenue_est:>10,.0f}/mo  {a.title[:50]}"
                )

        lines.append(f"\n--- Search Terms ({len(self.search_terms)}) ---")
        for i, t in enumerate(self.search_terms[:10], 1):
            brands_str = ", ".join(t.brands[:3]) if t.brands else "(none)"
            lines.append(
                f"  {i:>2}. {t.term:<35s}  vol={t.monthly_volume:>8,d}  "
                f"cpc=${t.cpc:.2f}  brands: {brands_str}"
            )
        if len(self.search_terms) > 10:
            lines.append(f"  ... and {len(self.search_terms) - 10} more terms")

        return "\n".join(lines)
