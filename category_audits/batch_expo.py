"""Batch runner for Expo West intel reports.

Reads the BRANDS array from the expo-west-app, filters to SmartScout-matched
brands, runs the category_audits pipeline, and outputs mobile-friendly HTML
intel reports.

Usage:
    python -m src.category_audits.batch_expo --top 100 --min-revenue 1000000
    python -m src.category_audits.batch_expo --top 3 --dry-run
    python -m src.category_audits.batch_expo --brand "Once Upon a Farm"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Paths
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_APP_DIR = _PROJECT_ROOT / "Expo_west" / "enhancements" / "expo-west-app"
_DEFAULT_OUTPUT = str(_APP_DIR / "intel")


def _extract_brands_from_html(html_path: str) -> list:
    """Extract the BRANDS array from the app's index.html."""
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find the BRANDS array: const BRANDS=[...];
    match = re.search(r"const BRANDS\s*=\s*(\[.*?\]);\s*\n", content, re.DOTALL)
    if not match:
        raise RuntimeError(f"Could not find BRANDS array in {html_path}")

    brands_json = match.group(1)
    try:
        brands = json.loads(brands_json)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse BRANDS JSON: {e}")

    print(f"[brands] Extracted {len(brands)} brands from {html_path}")
    return brands


def _extract_brands_from_json(json_path: str) -> list:
    """Extract brands from app_data.json."""
    with open(json_path, "r", encoding="utf-8") as f:
        brands = json.load(f)
    print(f"[brands] Loaded {len(brands)} brands from {json_path}")
    return brands


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _generate_index_page(reports: list, output_dir: str):
    """Generate intel/index.html listing all reports."""
    reports_sorted = sorted(reports, key=lambda r: r.get("l12m_raw", 0), reverse=True)

    rows = ""
    for r in reports_sorted:
        rev = f"${r['l12m_raw']:,.0f}" if r.get("l12m_raw") else "N/A"
        rows += (
            f'<tr>'
            f'<td><a href="{r["slug"]}.html">{r["brand"]}</a></td>'
            f'<td>{rev}</td>'
            f'<td>{r.get("category", "")}</td>'
            f'</tr>\n'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#1F3864">
<title>Intel Reports | Voyageur Group — Expo West 2026</title>
<style>
:root {{ --navy: #1F3864; --border: #E2E8F0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, Calibri, sans-serif;
  background: #F8FAFC; color: #333; margin: 0; padding: 0;
}}
.container {{ max-width: 720px; margin: 0 auto; padding: 16px; }}
.header {{
  background: var(--navy); color: #fff; padding: 20px 16px;
  border-radius: 12px; margin-bottom: 16px;
}}
.header h1 {{ font-size: 22px; margin-bottom: 4px; }}
.header p {{ font-size: 14px; opacity: 0.8; }}
.back-link {{
  display: inline-block; color: var(--navy); font-size: 14px;
  text-decoration: none; padding: 8px 0; margin-bottom: 8px;
}}
#search {{
  width: 100%; padding: 10px 14px; border: 1px solid var(--border);
  border-radius: 8px; font-size: 15px; margin-bottom: 12px;
  background: #fff;
}}
.table-wrap {{
  overflow-x: auto; border: 1px solid var(--border); border-radius: 8px;
}}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
thead th {{
  background: var(--navy); color: #fff; padding: 10px 12px;
  text-align: left; font-weight: 600;
}}
tbody td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); }}
tbody tr:nth-child(even) {{ background: #F8FAFC; }}
tbody td a {{ color: var(--navy); font-weight: 600; text-decoration: none; }}
tbody td a:hover {{ text-decoration: underline; }}
.count {{ font-size: 13px; color: #64748b; margin-bottom: 8px; }}
</style>
</head>
<body>
<div class="container">
<a href="../" class="back-link">&larr; Back to Expo West App</a>
<div class="header">
<h1>Intel Reports</h1>
<p>{len(reports)} competitive intelligence reports for Expo West 2026</p>
</div>
<input type="text" id="search" placeholder="Search brands..." oninput="filterTable(this.value)">
<div class="count" id="count">{len(reports)} reports</div>
<div class="table-wrap">
<table>
<thead><tr><th>Brand</th><th>L12M Revenue</th><th>Category</th></tr></thead>
<tbody id="tbody">
{rows}
</tbody>
</table>
</div>
</div>
<script>
function filterTable(q) {{
  q = q.toLowerCase();
  var rows = document.querySelectorAll('#tbody tr');
  var shown = 0;
  rows.forEach(function(r) {{
    var text = r.textContent.toLowerCase();
    var match = !q || text.indexOf(q) !== -1;
    r.style.display = match ? '' : 'none';
    if (match) shown++;
  }});
  document.getElementById('count').textContent = shown + ' reports';
}}
</script>
</body>
</html>"""

    path = os.path.join(output_dir, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[index] Generated {path} with {len(reports)} reports")


def _generate_manifest(reports: list, output_dir: str):
    """Generate intel/manifest.json mapping company names to slugs."""
    manifest = {}
    for r in reports:
        manifest[r["brand"]] = r["slug"]
        # Also add lowercased version for easier matching
        manifest[r["brand"].lower()] = r["slug"]

    path = os.path.join(output_dir, "manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"[manifest] Generated {path} with {len(reports)} entries")


def main():
    parser = argparse.ArgumentParser(
        description="Batch generate Expo West intel reports"
    )
    parser.add_argument(
        "--top", type=int, default=100,
        help="Number of top brands to process (default: 100)"
    )
    parser.add_argument(
        "--min-revenue", type=float, default=1_000_000,
        help="Minimum L12M revenue filter (default: 1,000,000)"
    )
    parser.add_argument(
        "--brand", type=str, default=None,
        help="Process a single brand by name (overrides --top)"
    )
    parser.add_argument(
        "--output-dir", type=str, default=_DEFAULT_OUTPUT,
        help="Output directory for HTML reports"
    )
    parser.add_argument(
        "--model", type=str, default="claude-sonnet-4-20250514",
        help="Claude model for analysis"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Pull data only, skip Claude analysis"
    )
    parser.add_argument(
        "--skip-cache", action="store_true",
        help="Force fresh SmartScout data pulls"
    )
    parser.add_argument(
        "--data-source", type=str, default="auto",
        choices=["auto", "html", "json"],
        help="Brand data source: 'html' (index.html), 'json' (app_data.json), 'auto' (try json first)"
    )

    args = parser.parse_args()

    # Load brands
    app_html = str(_APP_DIR / "index.html")
    app_json = str(_APP_DIR.parent / "app_data.json")

    if args.data_source == "json" or (args.data_source == "auto" and os.path.exists(app_json)):
        brands = _extract_brands_from_json(app_json)
    elif os.path.exists(app_html):
        brands = _extract_brands_from_html(app_html)
    else:
        print(f"ERROR: No brand data found. Checked:\n  {app_json}\n  {app_html}")
        sys.exit(1)

    # Filter: must have matchedBrand and meet revenue threshold
    eligible = [
        b for b in brands
        if b.get("matchedBrand")
        and (b.get("l12mRaw") or 0) >= args.min_revenue
    ]
    print(f"[filter] {len(eligible)} brands with matchedBrand and L12M >= ${args.min_revenue:,.0f}")

    # Single brand mode
    if args.brand:
        target = args.brand.lower()
        eligible = [
            b for b in eligible
            if b.get("matchedBrand", "").lower() == target
            or b.get("company", "").lower() == target
        ]
        if not eligible:
            print(f"ERROR: Brand '{args.brand}' not found in eligible brands")
            sys.exit(1)
        print(f"[single] Processing: {eligible[0]['company']}")
    else:
        # Sort by revenue descending, take top N
        eligible.sort(key=lambda b: b.get("l12mRaw", 0), reverse=True)
        eligible = eligible[:args.top]
        print(f"[batch] Processing top {len(eligible)} brands by L12M revenue")

    # Lazy imports (so --help is fast)
    from dotenv import load_dotenv
    load_dotenv(override=True)

    from .cache import load_cached, save_cache
    from .data_collector import CategoryDataCollector
    from .analyzer import analyze
    from .html_formatter import generate_html

    collector = CategoryDataCollector(marketplace="US")
    os.makedirs(args.output_dir, exist_ok=True)

    reports = []
    errors = []
    total = len(eligible)

    for idx, brand_info in enumerate(eligible, 1):
        company = brand_info["company"]
        matched = brand_info["matchedBrand"]
        l12m = brand_info.get("l12mRaw", 0)
        category = brand_info.get("category", "")
        slug = _slugify(matched)

        print(f"\n{'='*60}")
        print(f"[{idx}/{total}] {company} (matched: {matched})")
        print(f"  L12M: ${l12m:,.0f} | Category: {category}")
        print(f"{'='*60}")

        try:
            # Phase 1: Data collection (with cache)
            data = None
            if not args.skip_cache:
                data = load_cached("prospect", matched, None, "US")

            if data is None:
                print(f"  [data] Pulling SmartScout data for '{matched}'...")
                data = collector.collect(
                    report_type="prospect",
                    brand_name=matched,
                )
                save_cache(data)
            else:
                print(f"  [data] Using cached data")

            if args.dry_run:
                print(f"  [dry-run] Skipping analysis")
                reports.append({
                    "brand": company,
                    "matched": matched,
                    "slug": slug,
                    "l12m_raw": l12m,
                    "category": category,
                })
                continue

            # Phase 2: Claude analysis
            print(f"  [analyze] Sending to {args.model}...")
            markdown = analyze(data, model=args.model, style="expo")

            # Save markdown for debugging
            md_path = os.path.join(args.output_dir, f"{slug}.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(markdown)

            # Phase 3: HTML report
            html_path = generate_html(markdown, data, output_dir=args.output_dir)
            print(f"  [done] {html_path}")

            reports.append({
                "brand": company,
                "matched": matched,
                "slug": slug,
                "l12m_raw": l12m,
                "category": category,
            })

            # Courtesy delay between Claude calls
            if idx < total:
                time.sleep(2)

        except Exception as e:
            print(f"  [ERROR] {company}: {e}")
            errors.append({"brand": company, "error": str(e)})
            continue

    # Generate index and manifest
    if reports:
        _generate_index_page(reports, args.output_dir)
        _generate_manifest(reports, args.output_dir)

    # Summary
    print(f"\n{'='*60}")
    print(f"BATCH COMPLETE")
    print(f"  Processed: {len(reports)}/{total}")
    print(f"  Errors: {len(errors)}")
    if errors:
        for e in errors:
            print(f"    - {e['brand']}: {e['error']}")
    print(f"  Output: {args.output_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
