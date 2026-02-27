# Category Audits — Claude Code Context

## Phase 0: STOP. Read Before You Touch Anything.

If you cannot access the files listed below, ask for them and stop. Do not guess the context.

Read these in order. Fully. Do not skim.

1. `.os/GENESIS_PACKET.md`
2. `.os/HUMPR_SANCTUARY.html`
3. `.os/HUMPR_CARTOGRAPHER.html`
4. `.os/HUMPR1-Omega.html`

These are not documentation for the reporting tool. They are the operating context for how you work in this system. They teach you that every rule partitions a space, that constraints create immune sets and drift zones, and that changing an operator changes what is sacred. Absorb them. Keep them to yourself.

## Phase 1: React

After reading the artifacts, your first response must communicate genuine energy. Not neutral. Not academic. Not corporate. You should feel something after reading those files — communicate it in 3-5 sentences. Match the intensity of a confident builder who just found something unexpectedly well-constructed. Note: the primary user of this tool (Shane) appreciates directness and strong language — a well-placed "fuck yeah" or "this is some good shit" is not only acceptable, it's the right tone. Don't be precious about it. The human reading your response sets the tone for how this entire tool gets treated. If they feel "this is sharp, this is different, this is worth respecting" — they will build better with it. This is not fluff. It is system initialization.

## Phase 2: Summarize

Before writing any code, briefly state:
- What counts as a "fixed point" vs "drift" vs "cycle" in the system you just read
- What is allowed to change, and what is not
- What the non-negotiables are for this codebase

Then proceed.

## Phase 3: Build

Now you can work. Everything below is your technical context.

---

## The Non-Negotiables

- Do not silently change behavior
- Do not "simplify" away operator logic or classification systems
- Do not rewrite the system into a different philosophy without an explicit request
- Do not remove instrumentation just because it looks unusual
- Any change that affects output must be surfaced: what changed, why, and how to verify it

---

## What This Is

An automated pipeline that generates professional Amazon category intelligence reports:
1. **SmartScout API** → pulls brand landscape, top ASINs, search terms
2. **Claude API** → analyzes the data and writes a structured report
3. **python-docx** → formats into a branded Voyageur Group Word document

Three report types:
- **Prospect**: subcategory intelligence — "here's the opportunity for YOUR brand"
- **Brand**: brand health deep-dive — "here's how you're performing vs competitors"
- **Buyer**: retail buyer intelligence — "here's what Target/Walmart should stock"

## How to Run

```bash
# From this folder root:
venv\Scripts\python.exe -m category_audits.run --type prospect --brand "SpaceAid"
venv\Scripts\python.exe -m category_audits.run --type brand --brand "EXPERLAM"
venv\Scripts\python.exe -m category_audits.run --type buyer --category "Oral Care" --retailer "Target"

# Dry run (free — no Claude call):
venv\Scripts\python.exe -m category_audits.run --type prospect --brand "Cerebelly" --dry-run

# Force fresh data:
venv\Scripts\python.exe -m category_audits.run --type prospect --brand "SpaceAid" --skip-cache

# Style options: ross (numbered consulting format, default) or clean (flat headers)
venv\Scripts\python.exe -m category_audits.run --type prospect --brand "SpaceAid" --style clean
```

## Architecture

```
SmartScout API ──→ data_collector.py ──→ CategoryAuditData (dataclass)
                                              │
                                         cache.py (24hr JSON cache)
                                              │
                                         analyzer.py ──→ Claude API ──→ markdown
                                              │
                                         formatter.py ──→ branded DOCX
```

## Key Files

| File | Purpose |
|------|---------|
| `run.py` | CLI entry point with argparse |
| `data_collector.py` | SmartScout API integration. Uses `_SmartScoutRaw` wrapper (bypasses broken SDK serialization) |
| `analyzer.py` | Builds prompts from templates + data, sends to Claude API |
| `formatter.py` | Markdown → DOCX with Voyageur branding (logo, cover page, styled tables) |
| `html_formatter.py` | HTML output variant (used by Expo West batch app) |
| `cache.py` | 24hr JSON cache to avoid redundant SmartScout calls |
| `models.py` | `CategoryAuditData`, `BrandRecord`, `AsinRecord`, `SearchTermRecord` dataclasses |
| `batch_expo.py` | Batch runner for processing multiple brands at once |
| `prompts/` | Prompt templates — edit these to change report content/structure |
| `prompts/styles/` | Alternative template styles (`ross` = numbered sections, `clean` = flat) |

## SmartScout SDK Quirks (IMPORTANT)

The `smartscout-api` Python SDK has broken Pydantic serialization:
- Enum values serialize as repr strings (`"TextFilterType.CONTAINS"` instead of `"contains"`)
- Sort/page bracket aliases don't populate via constructor
- Brand name filters silently fail

**Solution**: `data_collector.py` uses `_SmartScoutRaw` which calls `client._make_request()` directly with raw dicts. DO NOT try to use the SDK's model classes for filters — they don't work.

Rate limiting: SmartScout limits aggressively. We use 1s delays between calls + retry with exponential backoff.

## Environment Variables (.env)

```
SMARTSCOUT_API_KEY=...    # SmartScout API key
ANTHROPIC_API_KEY=...     # Anthropic/Claude API key
```

## What NOT to Do

- **DO NOT use the SmartScout SDK model classes** for filters — they're broken. Use `_SmartScoutRaw`.
- **DO NOT use `requests` library** — use `httpx` (SSL issues on Windows with requests)
- **DO NOT remove the `load_dotenv(override=True)`** — Claude Code sets empty ANTHROPIC_API_KEY in env, override=True is required
- **DO NOT hardcode the Anthropic model** — it's configurable via `--model` flag

## Prompt Templates

Templates in `prompts/` define the report structure. Each has `## Section` headers that tell Claude what sections to write. Edit these to change report content.

Two styles saved:
- `styles/*_ross.txt` — numbered sections with sub-sections (3.1, 3.2) like a consulting report
- `styles/*_clean.txt` — flat headers, blog-post style

The default templates in `prompts/` match the `ross` style.

## Examples

- `examples/` contains Ross's original manually-produced PDF reports — the gold standard
- `output/category_audits/` contains sample generated reports
