"""Claude analysis layer for Category Audit reports.

Takes assembled CategoryAuditData and produces structured markdown
via the Anthropic API.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from anthropic import Anthropic
from dotenv import load_dotenv

from .models import AsinRecord, BrandRecord, CategoryAuditData, SearchTermRecord

DEFAULT_MODEL = "claude-sonnet-4-6"

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# ---------------------------------------------------------------------------
# Template loading
# ---------------------------------------------------------------------------

_SECTION_TEMPLATES = {
    "prospect": "prospect_template.txt",
    "brand": "brand_template.txt",
    "buyer": "buyer_template.txt",
}


def _load_prompt(filename: str) -> str:
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8").strip()


def _load_template(report_type: str, style: str = "ross") -> str:
    """Load a section template, respecting style choice.

    Styles are stored in prompts/styles/{type}_{style}.txt.
    The default files in prompts/ are always the current active style.
    """
    style_file = _PROMPTS_DIR / "styles" / f"{report_type}_{style}.txt"
    if style_file.exists():
        return style_file.read_text(encoding="utf-8").strip()
    # Fall back to the default template
    return _load_prompt(_SECTION_TEMPLATES[report_type])


# ---------------------------------------------------------------------------
# Data formatting helpers (for the user prompt)
# ---------------------------------------------------------------------------


def _format_brands_table(brands: List[BrandRecord], limit: int = 20) -> str:
    lines = [
        f"{'#':>3} {'Brand':<30} {'TTM Revenue':>14} {'Share%':>7} "
        f"{'YoY%':>7} {'Delta BP':>9} {'Products':>9} {'Avg $':>7} {'Rating':>6}"
    ]
    lines.append("-" * len(lines[0]))
    for i, b in enumerate(brands[:limit], 1):
        delta = f"{b.share_delta_bp:+.0f}" if b.share_delta_bp is not None else "n/a"
        lines.append(
            f"{i:>3} {b.name:<30} ${b.trailing_12_months:>12,.0f} "
            f"{b.share_pct:>6.1f}% {b.month_growth_12:>+6.1f}% "
            f"{delta:>9} {b.total_products:>9} ${b.avg_price:>5.2f} "
            f"{b.review_rating:>5.1f}"
        )
    return "\n".join(lines)


def _format_asins_table(asins: List[AsinRecord], limit: int = 50) -> str:
    lines = [
        f"{'#':>3} {'ASIN':<12} {'Brand':<22} {'Est. Mo. Rev':>13} "
        f"{'Units':>7} {'Price':>7} {'Reviews':>8} {'Rating':>6} Title"
    ]
    lines.append("-" * 120)
    for i, a in enumerate(asins[:limit], 1):
        lines.append(
            f"{i:>3} {a.asin:<12} {a.brand[:21]:<22} "
            f"${a.monthly_revenue_est:>11,.0f} {a.monthly_units_est:>7,} "
            f"${a.price:>5.2f} {a.review_count:>8,} {a.review_rating:>5.1f}  "
            f"{a.title[:60]}"
        )
    return "\n".join(lines)


def _format_search_terms(terms: List[SearchTermRecord], limit: int = 30) -> str:
    lines = [
        f"{'#':>3} {'Search Term':<40} {'Est. Monthly Vol':>17} {'CPC':>6}"
    ]
    lines.append("-" * 70)
    for i, t in enumerate(terms[:limit], 1):
        lines.append(
            f"{i:>3} {t.term:<40} {t.monthly_volume:>17,} ${t.cpc:>5.2f}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def build_analysis_prompt(data: CategoryAuditData, style: str = "ross") -> str:
    """Build the full user prompt from assembled data."""
    section_template = _load_template(data.report_type, style)

    # Replace [Brand Name] placeholder in templates
    if data.target_brand:
        section_template = section_template.replace(
            "[Brand Name]", data.target_brand
        )
    if data.retailer:
        section_template = section_template.replace("[retailer]", data.retailer)
        section_template = section_template.replace("[Retailer]", data.retailer)

    prior_rev = (
        f"${data.total_category_revenue_prior:,.0f}"
        if data.total_category_revenue_prior is not None
        else "(not available — use brand-level YoY growth rates instead)"
    )

    brand_asins_section = ""
    if data.brand_asins:
        brand_asins_section = (
            f"\nBRAND'S OWN ASIN PORTFOLIO ({data.target_brand}):\n"
            f"{_format_asins_table(data.brand_asins)}"
        )

    return f"""Run a {data.report_type} category intelligence report.

CONTEXT:
- {"Target brand: " + data.target_brand if data.target_brand else "Category-wide view"}
- Category: {data.category_name} / {data.subcategory_name}
- {"Retailer lens: " + data.retailer if data.retailer else ""}
- Marketplace: {data.marketplace}
- Data as of: {data.data_pulled_at.strftime('%B %Y')}

CATEGORY FINANCIALS:
- TTM Revenue (est.): ${data.total_category_revenue_ttm:,.0f}
- Prior 12mo Revenue (est.): {prior_rev}
- YoY Growth (revenue-weighted avg): {data.yoy_growth_pct:+.1f}%

BRAND LANDSCAPE (sorted by TTM revenue, with computed share):
{_format_brands_table(data.brands[:20])}
(share_delta_bp = basis points change, TTM vs prior 12 months; "n/a" = not computed for this report type)
Note: share % is relative to tracked brand set, not absolute Amazon category share.

TOP ASINs by estimated monthly revenue:
{_format_asins_table(data.top_asins[:50])}
{brand_asins_section}

TOP SEARCH TERMS by estimated monthly volume:
{_format_search_terms(data.search_terms[:30])}

REQUIRED SECTIONS:
{section_template}

IMPORTANT:
- Use specific brand names, ASINs, revenue figures, and share data throughout.
- Every claim must be traceable to the data above.
- Label all SmartScout revenue figures as "estimated" throughout.
- Do NOT invent data not present above. If data is insufficient for a section, say so explicitly.
"""


# ---------------------------------------------------------------------------
# Analysis runner
# ---------------------------------------------------------------------------


def analyze(
    data: CategoryAuditData,
    model: str = DEFAULT_MODEL,
    style: str = "ross",
) -> str:
    """Send data to Claude and return markdown analysis."""
    load_dotenv(override=True)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not found in environment")

    client = Anthropic(api_key=api_key)
    system_prompt = _load_prompt("system_prompt.txt")
    user_prompt = build_analysis_prompt(data, style=style)

    print(f"[analyze] Sending to {model}...")
    print(f"  Prompt length: ~{len(user_prompt):,} chars")

    response = client.messages.create(
        model=model,
        max_tokens=12000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    result = response.content[0].text
    print(f"[analyze] Done. Response: ~{len(result):,} chars")
    return result
