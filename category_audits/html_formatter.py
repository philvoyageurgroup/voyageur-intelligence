"""Markdown -> mobile-friendly HTML formatter for Expo West intel reports.

Produces single-file HTML with inline CSS, no external dependencies.
Designed for phone-at-a-booth scanning: Kill Screen card at top,
collapsible sections, horizontally scrollable tables.
"""

from __future__ import annotations

import os
import re

from .models import CategoryAuditData

# ---------------------------------------------------------------------------
# Brand colours
# ---------------------------------------------------------------------------

NAVY = "#1F3864"

# ---------------------------------------------------------------------------
# CSS (mobile-first, inline)
# ---------------------------------------------------------------------------

_CSS = r"""
:root {
  --navy: #1F3864;
  --dark: #333333;
  --light-bg: #F8FAFC;
  --card-bg: #FFFFFF;
  --border: #E2E8F0;
  --kill-red: #DC2626;
  --kill-green: #059669;
  --kill-amber: #D97706;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { font-size: 16px; -webkit-text-size-adjust: 100%; }
body {
  font-family: -apple-system, BlinkMacSystemFont, Calibri, Roboto, sans-serif;
  background: var(--light-bg);
  color: var(--dark);
  line-height: 1.55;
  padding: 0; margin: 0;
}
.container { max-width: 720px; margin: 0 auto; padding: 12px 16px 40px; }
.back-link {
  display: inline-block; color: var(--navy); font-size: 14px;
  text-decoration: none; padding: 8px 0; margin-bottom: 8px;
}
.back-link:hover { text-decoration: underline; }
.report-header {
  background: var(--navy); color: #fff; padding: 20px 16px;
  border-radius: 12px; margin-bottom: 16px;
}
.report-header h1 { font-size: 22px; font-weight: 700; line-height: 1.2; margin-bottom: 4px; }
.report-header .subtitle { font-size: 14px; opacity: 0.85; }
.report-header .meta { font-size: 12px; opacity: 0.65; margin-top: 8px; }
.kill-screen {
  background: #FFF7ED; border: 2px solid var(--kill-amber);
  border-radius: 12px; padding: 16px; margin-bottom: 16px;
}
.kill-screen h2 {
  font-size: 16px; font-weight: 800; text-transform: uppercase;
  letter-spacing: 0.5px; color: var(--kill-amber); margin-bottom: 12px;
}
.kill-item { margin-bottom: 12px; }
.kill-item:last-child { margin-bottom: 0; }
.kill-label {
  display: inline-block; font-size: 11px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.5px;
  padding: 2px 8px; border-radius: 4px; margin-bottom: 4px;
}
.kill-label.threat { background: #FEE2E2; color: var(--kill-red); }
.kill-label.whitespace { background: #D1FAE5; color: var(--kill-green); }
.kill-label.leak { background: #FEF3C7; color: var(--kill-amber); }
.kill-text { font-size: 14px; line-height: 1.45; color: var(--dark); }
details {
  background: var(--card-bg); border: 1px solid var(--border);
  border-radius: 10px; margin-bottom: 10px; overflow: hidden;
}
details[open] { box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
summary {
  padding: 14px 16px; font-size: 15px; font-weight: 700;
  color: var(--navy); cursor: pointer; list-style: none;
  display: flex; align-items: center; justify-content: space-between;
  -webkit-tap-highlight-color: transparent; user-select: none;
}
summary::-webkit-details-marker { display: none; }
summary::after {
  content: '\25B6'; font-size: 11px;
  transition: transform 0.2s; color: #94A3B8;
}
details[open] > summary::after { transform: rotate(90deg); }
.section-body { padding: 0 16px 16px; font-size: 14px; }
.section-body h3 {
  font-size: 14px; font-weight: 700; color: var(--navy); margin: 14px 0 6px;
}
.table-wrap {
  overflow-x: auto; -webkit-overflow-scrolling: touch;
  margin: 10px 0; border-radius: 8px; border: 1px solid var(--border);
}
table { width: 100%; min-width: 400px; border-collapse: collapse; font-size: 13px; }
thead th {
  background: var(--navy); color: #fff; font-weight: 600;
  text-align: left; padding: 8px 10px; white-space: nowrap;
}
tbody td {
  padding: 7px 10px; border-bottom: 1px solid var(--border); white-space: nowrap;
}
tbody tr:nth-child(even) { background: #F8FAFC; }
ul, ol { padding-left: 20px; margin: 8px 0; }
li { margin-bottom: 4px; font-size: 14px; }
.section-body p { margin: 8px 0; }
strong { font-weight: 700; }
em { font-style: italic; }
hr { border: none; border-top: 1px solid var(--border); margin: 16px 0; }
.report-footer {
  text-align: center; font-size: 12px; color: #94A3B8;
  padding: 24px 0 16px; border-top: 1px solid var(--border); margin-top: 24px;
}
@media print {
  body { background: #fff; }
  .back-link { display: none; }
  details { break-inside: avoid; }
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _render_inline(text: str) -> str:
    """Convert inline markdown (bold, italic) to HTML."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def _parse_kill_screen(lines: list, start: int) -> tuple:
    """Parse Kill Screen section into styled HTML cards."""
    html = '<div class="kill-screen"><h2>Kill Screen</h2>\n'
    i = start

    kill_items = {
        "- **The Threat": ("threat", "The Threat"),
        "- **The White Space": ("whitespace", "The White Space"),
        "- **The Leak": ("leak", "The Leak"),
    }

    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("## ") and i > start:
            break

        matched = False
        for prefix, (label_class, label_text) in kill_items.items():
            if line.startswith(prefix):
                # Strip the prefix and bold markers
                content = line[len(prefix):]
                content = re.sub(r"^\*?\*?:?\s*", "", content)
                html += (
                    f'<div class="kill-item">'
                    f'<div class="kill-label {label_class}">{label_text}</div>'
                    f'<div class="kill-text">{_render_inline(_escape(content))}</div>'
                    f'</div>\n'
                )
                matched = True
                break

        i += 1
    html += "</div>\n"
    return html, i


def _parse_table(lines: list, start: int) -> tuple:
    """Parse markdown table into HTML table with scroll wrapper."""
    table_lines = []
    i = start
    while i < len(lines) and lines[i].strip().startswith("|"):
        table_lines.append(lines[i].strip())
        i += 1

    if not table_lines:
        return "", i

    rows = []
    for line in table_lines:
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.match(r"^:?-+:?$", c) for c in cells):
            continue
        rows.append(cells)

    if not rows:
        return "", i

    html = '<div class="table-wrap"><table>\n'
    for r_idx, row in enumerate(rows):
        if r_idx == 0:
            html += "<thead><tr>"
            for cell in row:
                html += f"<th>{_render_inline(_escape(cell))}</th>"
            html += "</tr></thead>\n<tbody>\n"
        else:
            html += "<tr>"
            for cell in row:
                html += f"<td>{_render_inline(_escape(cell))}</td>"
            html += "</tr>\n"
    html += "</tbody></table></div>\n"
    return html, i


def _markdown_to_html(markdown: str, brand_name: str) -> tuple:
    """Convert markdown analysis to HTML.

    Returns (kill_screen_html, sections_html).
    """
    lines = markdown.split("\n")
    kill_html = ""
    sections = []  # list of (title, body_html)
    current_title = ""
    current_body = ""
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            if current_title:
                current_body += "\n"
            i += 1
            continue

        # Skip top-level title
        if stripped.startswith("# ") and not stripped.startswith("## "):
            i += 1
            continue

        # Kill Screen section
        if stripped.upper().replace(" ", "").startswith("##KILLSCREEN"):
            i += 1
            kill_html, i = _parse_kill_screen(lines, i)
            continue

        # New section
        if stripped.startswith("## "):
            if current_title:
                sections.append((current_title, current_body))
            current_title = stripped.lstrip("#").strip()
            current_title = re.sub(r"^\d+[\.\)]\s*", "", current_title)
            current_body = ""
            i += 1
            continue

        # Content inside a section
        if current_title:
            # Sub-heading
            if stripped.startswith("### "):
                text = stripped.lstrip("#").strip()
                text = re.sub(r"^\d+[\.\)]\s*", "", text)
                current_body += f"<h3>{_render_inline(_escape(text))}</h3>\n"
                i += 1
                continue

            # HR
            if stripped in ("---", "***", "___"):
                current_body += "<hr>\n"
                i += 1
                continue

            # Table
            if stripped.startswith("|") and "|" in stripped[1:]:
                table_html, i = _parse_table(lines, i)
                current_body += table_html
                continue

            # Bullet list
            if stripped.startswith("- ") or stripped.startswith("* ") or stripped.startswith("\u2022 "):
                current_body += "<ul>\n"
                while i < len(lines):
                    s = lines[i].strip()
                    if s.startswith("- ") or s.startswith("* ") or s.startswith("\u2022 "):
                        content = s[2:]
                        current_body += f"<li>{_render_inline(_escape(content))}</li>\n"
                        i += 1
                    elif s.startswith("  ") and s.strip():
                        current_body = current_body.rstrip("\n")
                        current_body += f" {_render_inline(_escape(s.strip()))}\n"
                        i += 1
                    else:
                        break
                current_body += "</ul>\n"
                continue

            # Numbered list
            num_match = re.match(r"^\d+[\.\)]\s+", stripped)
            if num_match:
                current_body += "<ol>\n"
                while i < len(lines):
                    s = lines[i].strip()
                    nm = re.match(r"^\d+[\.\)]\s+", s)
                    if nm:
                        content = s[nm.end():]
                        current_body += f"<li>{_render_inline(_escape(content))}</li>\n"
                        i += 1
                    elif s.startswith("  ") and s.strip():
                        current_body = current_body.rstrip("\n")
                        current_body += f" {_render_inline(_escape(s.strip()))}\n"
                        i += 1
                    else:
                        break
                current_body += "</ol>\n"
                continue

            # Regular paragraph
            current_body += f"<p>{_render_inline(_escape(stripped))}</p>\n"
            i += 1
        else:
            i += 1

    if current_title:
        sections.append((current_title, current_body))

    # Build collapsible sections
    sections_html = ""
    for idx, (title, body) in enumerate(sections):
        open_attr = " open" if idx == 0 else ""
        sections_html += (
            f"<details{open_attr}>\n"
            f"<summary>{_escape(title)}</summary>\n"
            f'<div class="section-body">{body}</div>\n'
            f"</details>\n"
        )

    return kill_html, sections_html


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_html(
    markdown: str,
    data: CategoryAuditData,
    output_dir: str = "expo-west-app/intel/",
) -> str:
    """Generate a mobile-friendly HTML report from markdown analysis.

    Returns the output file path.
    """
    brand_name = data.target_brand or data.subcategory_name
    kill_html, sections_html = _markdown_to_html(markdown, brand_name)

    slug = re.sub(r"[^a-z0-9]+", "-", brand_name.lower()).strip("-")
    date_str = data.data_pulled_at.strftime("%B %Y")
    revenue_str = (
        f"${data.total_category_revenue_ttm:,.0f}"
        if data.total_category_revenue_ttm
        else "N/A"
    )

    page_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="{NAVY}">
<title>{_escape(brand_name)} — Intel Report | Voyageur Group</title>
<style>{_CSS}</style>
</head>
<body>
<div class="container">
<a href="../" class="back-link">&larr; Back to Expo West App</a>

<div class="report-header">
<h1>{_escape(brand_name)}</h1>
<div class="subtitle">Competitive Intelligence Report — {_escape(data.subcategory_name)}</div>
<div class="meta">Category TTM: {revenue_str} &bull; {_escape(date_str)} &bull; Voyageur Group</div>
</div>

{kill_html}

{sections_html}

<div class="report-footer">
Prepared by Voyageur Group &bull; Data: SmartScout &bull; Analysis: Claude AI<br>
For internal use only — Expo West 2026
</div>
</div>
</body>
</html>"""

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{slug}.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(page_html)
    return output_path
