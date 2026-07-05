# connections-bench

Benchmark LLM coding-agent CLIs (`claude`, `codex`) on the NYT Connections
puzzle: each model gets a single shot at grouping the 16 words into the 4
official groups.

## How it works

- **Puzzles** are fetched from the public NYT endpoint
  `https://www.nytimes.com/svc/connections/v2/<YYYY-MM-DD>.json` and cached in
  `puzzles/` (gitignored — the puzzle content is NYT's). Any date from
  2023-06-12 onward works.
- **Attempts** shell out to the installed CLIs in headless one-shot mode with
  tools and web search disabled, so the model can't just look up the answer:
  - `claude -p --tools "" --output-format json [--model <m>]`
  - `codex exec --json --sandbox read-only -c tools.web_search=false --ephemeral [-m <m>]`
  - `openrouter:<model-id>` calls the OpenRouter chat-completions API directly
    (no agent harness — just the raw model). Needs `OPENROUTER_API_KEY` in the
    environment or in a gitignored `.env` file. Good for open-weight models,
    e.g. `openrouter:deepseek/deepseek-v4-pro`, `openrouter:moonshotai/kimi-k2.6`,
    `openrouter:z-ai/glm-5.2`, `openrouter:minimax/minimax-m3`,
    `openrouter:qwen/qwen3.6-35b-a3b`.
- **Grading** ignores the theme labels; an attempt is *solved* only if all four
  4-word groupings exactly match the official answer. Partial credit is
  recorded as `correct_groups` (0, 1, 2, or 4 — three correct implies four).
- **Results** are appended to `results/runs.jsonl`, one JSON object per
  attempt, including token counts (`tokens_in`, `tokens_in_cached`,
  `tokens_out`, `tokens_reasoning`), cost (claude only — codex doesn't report
  it), duration, the parsed guess, and the raw model response.

## Usage

```sh
# both default models on one puzzle
./bench.py run --date 2026-07-04

# a month of puzzles, specific model variants, 6 parallel attempts
./bench.py run --start 2026-06-01 --end 2026-06-30 \
    --models claude:opus,claude:haiku,codex,codex:@low --jobs 6

# results table (also printed after every run)
./bench.py summary
```

Model specs are `runner[:model][@effort]` — the model is passed straight to
the CLI's `--model`/`-m` flag, and the effort to `claude --effort` /
codex `-c model_reasoning_effort=`. `codex:@low` means codex's default model
at low reasoning effort (ChatGPT-account codex only accepts its default
model, so effort is the lever there). Attempts already recorded for a (date, model)
pair are skipped; pass `--rerun` to redo them (the summary uses the latest
attempt per pair).

No dependencies beyond Python 3.10+ and the two CLIs on PATH.
