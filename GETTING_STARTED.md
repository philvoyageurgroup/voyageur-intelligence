# Category Audits — Getting Started

This tool generates professional category intelligence reports from SmartScout data. One command, ~90 seconds, polished Word doc with Voyageur branding.

---

## What You Need

1. **Python 3.11+** installed on your machine
2. **Claude Code** (the CLI or the new in-app version)
3. **API Keys** — ask Phil for the `.env` file, or create one with:
   ```
   SMARTSCOUT_API_KEY=your_key_here
   ANTHROPIC_API_KEY=your_key_here
   ```

---

## First-Time Setup

Open a terminal in this folder and run:

```bash
python -m venv venv
venv\Scripts\pip.exe install smartscout-api anthropic python-dotenv httpx python-docx pdfplumber
```

Drop the `.env` file (from Phil) into this folder's root.

That's it. You're ready.

---

## Running Reports

All commands run from this folder's root:

### Prospect Report
"Here's your category — here's the opportunity for YOUR brand."
Best for: pitching a brand on why they need Voyageur managing their Amazon.

```bash
venv\Scripts\python.exe -m category_audits.run --type prospect --brand "SpaceAid"
```

### Brand Health Report
"Here's how YOUR brand is performing vs the category."
Best for: existing clients or deep-dive pitches.

```bash
venv\Scripts\python.exe -m category_audits.run --type brand --brand "SpaceAid"
```

### Buyer Report
"Here's what's selling online — here's what you should stock."
Best for: pitching retail buyers (Target, Walmart) on which brands to carry.

```bash
venv\Scripts\python.exe -m category_audits.run --type buyer --category "Oral Care" --retailer "Target"
```

---

## Options

| Flag | What it does | Example |
|------|-------------|---------|
| `--brand` | Brand to analyze (required for prospect/brand) | `--brand "Kindred Bravely"` |
| `--category` | Category name (required for buyer) | `--category "Baby Food"` |
| `--retailer` | Retailer name (buyer only) | `--retailer "Target"` |
| `--marketplace` | Default: US | `--marketplace CA` |
| `--style` | `ross` (numbered consulting style, default) or `clean` (flat headers) | `--style clean` |
| `--dry-run` | Pull data + show summary, skip Claude + DOCX (free, no API cost) | |
| `--skip-cache` | Force fresh SmartScout pull (ignores 24hr cache) | |
| `--model` | Claude model to use (default: claude-sonnet-4-20250514) | |

---

## Output

Every run produces two files in `output/category_audits/`:
- `.md` — raw markdown (good for pasting into Slack/email)
- `.docx` — branded Word doc with Voyageur logo, tables, cover page

---

## Costs

| Component | Cost |
|-----------|------|
| SmartScout | $0 (included in plan) |
| Claude API | ~$0.05-0.10 per report |
| **Total** | **~$0.05-0.10 per report** |

10 reports/week = ~$5/month.

---

## Using Claude Code with This Tool

Point Claude Code at this folder. It can see all the code and run reports for you. Just tell it what you want in plain English:

> "Run a prospect report for Grinds"
> "Generate a buyer report for Target in the Oral Care category"
> "Show me a dry run for Cerebelly to see what data we have"

Claude Code can also:
- Modify the prompt templates to change report style
- Add new report types
- Tweak the DOCX formatting
- Build on top of the SmartScout data for new analyses

The prompt templates live in `category_audits/prompts/` — edit those to change what the reports contain.

---

## Troubleshooting

**"Brand not found"** — Try the exact name as it appears on Amazon. Use `--dry-run` to test.

**SmartScout 500 errors** — Their API has occasional outages. Wait and retry.

**Wrong category** — Some brands (like Grinds) get classified under broad categories. The report will still be useful but the competitive set may be broader than expected.

**"ANTHROPIC_API_KEY not found"** — Make sure your `.env` file is in the root folder.

---

## File Structure

```
handoff/
├── .env                          # API keys (get from Phil)
├── GETTING_STARTED.md            # This file
├── CLAUDE.md                     # Context for Claude Code
├── assets/
│   └── voyageur_logo.png         # Logo for DOCX header
├── category_audits/              # The tool
│   ├── run.py                    # CLI entry point
│   ├── data_collector.py         # SmartScout API pulls
│   ├── analyzer.py               # Claude analysis
│   ├── formatter.py              # Markdown → DOCX
│   ├── html_formatter.py         # HTML output (Expo West style)
│   ├── cache.py                  # 24hr data cache
│   ├── models.py                 # Data models
│   ├── batch_expo.py             # Batch runner for multiple brands
│   └── prompts/                  # Prompt templates
│       ├── system_prompt.txt
│       ├── prospect_template.txt
│       ├── brand_template.txt
│       ├── buyer_template.txt
│       └── styles/               # Alternative styles
├── output/                       # Generated reports land here
│   └── category_audits/
└── examples/                     # Ross's original manual reports (gold standard)
```
