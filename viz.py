#!/usr/bin/env python3
"""Render results/runs.jsonl into a self-contained HTML figure (viz.html).

Screenshot for the README with:
  npx playwright screenshot --viewport-size "1060,<h>" viz.html assets/results.png
"""

import json
from html import escape
from pathlib import Path

from bench import PROMPT_VERSION, load_runs

ROOT = Path(__file__).resolve().parent

# Ordinal blue ramp (validated, steps 250-600): more correct -> darker.
CELL = {0: "#86b6ef", 1: "#5598e7", 2: "#2a78d6", 3: "#256abf", 4: "#184f95"}
BAR = "#1baf7a"  # aqua, second sequential context (token magnitude)

LABELS = {
    "claude:claude-fable-5@high": "Claude Fable 5",
    "claude:claude-opus-4-8@high": "Claude Opus 4.8",
    "claude:claude-opus-4-5@high": "Claude Opus 4.5",
    "claude:claude-sonnet-5@high": "Claude Sonnet 5",
    "claude:claude-sonnet-4-5@high": "Claude Sonnet 4.5",
    "claude:claude-haiku-4-5@high": "Claude Haiku 4.5",
    "codex": "GPT-5.5 (codex)",
    "codex:gpt-5.4-mini": "GPT-5.4 mini",
    "codex-api:gpt-4.1-mini": "GPT-4.1 mini",
    "openrouter:deepseek/deepseek-v4-pro": "DeepSeek V4 Pro",
    "openrouter:deepseek/deepseek-v4-flash": "DeepSeek V4 Flash",
    "openrouter:moonshotai/kimi-k2.6": "Kimi K2.6",
    "openrouter:z-ai/glm-5.2": "GLM-5.2",
    "openrouter:minimax/minimax-m3": "MiniMax M3",
    "openrouter:qwen/qwen3.6-35b-a3b": "Qwen3.6 35B A3B",
}


def build() -> str:
    latest = {}
    for r in load_runs():
        if r.get("prompt_v", 1) == PROMPT_VERSION:
            latest[(r["date"], r["model"])] = r
    dates = sorted({d for d, _ in latest})
    models = sorted({m for _, m in latest})

    stats = []
    for m in models:
        rs = [latest[(d, m)] for d in dates if (d, m) in latest]
        ok = [r for r in rs if not r.get("error")]
        solved = sum(1 for r in ok if r.get("solved"))
        toks = sum(r.get("tokens_out") or 0 for r in ok) / max(len(ok), 1)
        costs = [r["cost_usd"] for r in ok if r.get("cost_usd") is not None]
        cost = sum(costs) / len(costs) if costs else None
        stats.append((m, solved, len(ok), toks, cost))
    stats.sort(key=lambda s: (-s[1] / max(s[2], 1), s[3]))
    max_tok = max(s[3] for s in stats) or 1

    day_headers = "".join(
        f'<div class="day">{d[8:].lstrip("0")}</div>' for d in dates)
    rows = []
    for m, solved, n, toks, cost in stats:
        cells = []
        for d in dates:
            r = latest.get((d, m))
            if r is None or r.get("error"):
                cells.append('<div class="cell miss" title="no result"></div>')
                continue
            g = 4 if r.get("solved") else r.get("correct_groups", 0)
            tip = f"{d}: {'solved' if g == 4 else f'{g}/4 groups'}"
            cells.append(
                f'<div class="cell" style="background:{CELL[g]}" title="{tip}"></div>')
        bar_w = max(2, round(toks / max_tok * 160))
        if cost is None:
            cost_s = "–"
        else:
            cost_s = f"${cost:.3f}" if cost < 0.10 else f"${cost:.2f}"
        rows.append(f"""
      <div class="row">
        <div class="name">{escape(LABELS.get(m, m))}</div>
        <div class="cells">{''.join(cells)}</div>
        <div class="solved">{solved}/{n}</div>
        <div class="tok"><span class="tokbar" style="width:{bar_w}px"></span>
          <span class="tokval">{toks:,.0f}</span></div>
        <div class="cost">{cost_s}</div>
      </div>""")

    period = f"June {dates[0][8:].lstrip('0')} – July {dates[-1][8:].lstrip('0')}, 2026"
    return f"""<!doctype html>
<meta charset="utf-8">
<title>connections-bench results</title>
<style>
  :root {{
    --surface: #fcfcfb; --plane: #f9f9f7; --ink: #0b0b0b; --ink2: #52514e;
    --muted: #898781; --hairline: #e1e0d9; --ring: rgba(11,11,11,0.10);
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --surface: #1a1a19; --plane: #0d0d0d; --ink: #ffffff; --ink2: #c3c2b7;
      --muted: #898781; --hairline: #2c2c2a; --ring: rgba(255,255,255,0.10);
    }}
  }}
  body {{ margin: 0; background: var(--plane);
    font: 14px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif; color: var(--ink); }}
  .fig {{ background: var(--surface); border: 1px solid var(--ring);
    border-radius: 8px; margin: 16px; padding: 20px 24px; width: 980px; box-sizing: border-box; }}
  h1 {{ font-size: 17px; margin: 0 0 2px; font-weight: 600; }}
  .sub {{ color: var(--ink2); font-size: 12.5px; margin-bottom: 14px; }}
  .row, .hdr {{ display: grid; grid-template-columns: 150px 300px 46px 240px 60px;
    gap: 14px; align-items: center; padding: 3px 0; }}
  .hdr {{ color: var(--muted); font-size: 11px; border-bottom: 1px solid var(--hairline);
    padding-bottom: 5px; margin-bottom: 4px; }}
  .hdr .days {{ display: flex; gap: 2px; }}
  .day {{ width: 28px; text-align: center; }}
  .name {{ font-size: 12.5px; white-space: nowrap; }}
  .cells {{ display: flex; gap: 2px; }}
  .cell {{ width: 28px; height: 18px; border-radius: 3px; }}
  .cell.miss {{ background: transparent; box-shadow: inset 0 0 0 1px var(--hairline); }}
  .solved {{ font-variant-numeric: tabular-nums; font-size: 12.5px; text-align: right; }}
  .tok {{ display: flex; align-items: center; gap: 6px; }}
  .tokbar {{ height: 8px; border-radius: 0 4px 4px 0; background: {BAR}; display: inline-block; }}
  .tokval {{ color: var(--ink2); font-size: 11.5px; font-variant-numeric: tabular-nums; }}
  .cost {{ color: var(--ink2); font-size: 11.5px; text-align: right; font-variant-numeric: tabular-nums; }}
  .legend {{ display: flex; gap: 14px; margin-top: 14px; padding-top: 10px;
    border-top: 1px solid var(--hairline); color: var(--ink2); font-size: 11.5px; align-items: center; }}
  .sw {{ width: 14px; height: 14px; border-radius: 3px; display: inline-block;
    vertical-align: -2px; margin-right: 5px; }}
</style>
<div class="fig">
  <h1>NYT Connections — single-shot solve rate by model</h1>
  <div class="sub">{period} · one attempt per puzzle · prompt gives only the 16 words
    and the answer shape · tools/web disabled</div>
  <div class="hdr">
    <div>model</div>
    <div class="days">{day_headers}</div>
    <div style="text-align:right">solved</div>
    <div>avg output tokens per puzzle</div>
    <div style="text-align:right">avg cost</div>
  </div>
  {''.join(rows)}
  <div class="legend">
    <span>groups correct:</span>
    <span><span class="sw" style="background:{CELL[0]}"></span>0</span>
    <span><span class="sw" style="background:{CELL[1]}"></span>1</span>
    <span><span class="sw" style="background:{CELL[2]}"></span>2</span>
    <span><span class="sw" style="background:{CELL[4]}"></span>4 (solved)</span>
    <span style="margin-left:auto">cost is API-metered; – = subscription</span>
  </div>
</div>
"""


if __name__ == "__main__":
    out = ROOT / "viz.html"
    out.write_text(build())
    print(f"wrote {out}")
