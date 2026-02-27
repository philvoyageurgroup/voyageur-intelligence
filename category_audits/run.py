"""CLI entry point for Category Audit reports.

Usage (run from the handoff folder root):
    venv\\Scripts\\python.exe -m category_audits.run --type prospect --brand "SpaceAid"
    venv\\Scripts\\python.exe -m category_audits.run --type brand --brand "EXPERLAM"
    venv\\Scripts\\python.exe -m category_audits.run --type buyer --category "Oral Care" --retailer "Target"
"""

from __future__ import annotations

import argparse
import sys

# Windows console encoding fix
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    parser = argparse.ArgumentParser(
        description="Category Audit — SmartScout → Claude → DOCX pipeline"
    )
    parser.add_argument(
        "--type",
        required=True,
        choices=["prospect", "brand", "buyer"],
        help="Report type",
    )
    parser.add_argument("--brand", help="Target brand name (required for prospect/brand)")
    parser.add_argument("--category", help="Category name (required for buyer reports)")
    parser.add_argument("--retailer", help="Retailer name (buyer reports only)")
    parser.add_argument("--marketplace", default="US", help="Marketplace (default: US)")
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-20250514",
        help="Anthropic model ID (default: claude-sonnet-4-20250514)",
    )
    parser.add_argument(
        "--output-dir",
        default="output/category_audits/",
        help="Output directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Pull data and print summary only — no Claude call, no DOCX",
    )
    parser.add_argument(
        "--skip-cache",
        action="store_true",
        help="Force fresh SmartScout pulls (ignore cache)",
    )
    parser.add_argument(
        "--style",
        default="ross",
        choices=["ross", "clean"],
        help="Report style: 'ross' = numbered sections like consulting report (default), 'clean' = original flat style",
    )

    args = parser.parse_args()

    # Validate inputs
    if args.type in ("prospect", "brand") and not args.brand:
        parser.error(f"--brand is required for --type {args.type}")
    if args.type == "buyer" and not args.category:
        parser.error("--category is required for --type buyer")

    # Phase 1: Data collection (with cache)
    from .cache import load_cached, save_cache
    from .data_collector import CategoryDataCollector

    data = None
    if not args.skip_cache:
        data = load_cached(
            args.type, args.brand, args.category, args.marketplace
        )

    if data is None:
        collector = CategoryDataCollector(marketplace=args.marketplace)
        data = collector.collect(
            report_type=args.type,
            brand_name=args.brand,
            category_name=args.category,
            retailer=args.retailer,
        )
        save_cache(data)

    if args.dry_run:
        print("\n" + data.summary())
        print("\n[dry-run] Done. No Claude call or DOCX generated.")
        return

    # Phase 2: Analysis (Claude)
    from .analyzer import analyze

    markdown = analyze(data, model=args.model, style=args.style)

    # Save markdown alongside eventual DOCX
    import os

    os.makedirs(args.output_dir, exist_ok=True)
    ts = data.data_pulled_at.strftime("%Y%m%d_%H%M")
    safe_name = (data.subcategory_name or data.category_name).replace(" ", "_").lower()
    md_path = os.path.join(args.output_dir, f"{safe_name}_{args.type}_{ts}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown)
    print(f"\n[output] Markdown saved to: {md_path}")

    # Phase 3: DOCX output
    from .formatter import generate_docx

    docx_path = generate_docx(markdown, data, output_dir=args.output_dir)
    print(f"[output] DOCX saved to: {docx_path}")


if __name__ == "__main__":
    main()
