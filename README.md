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
    --models claude:opus,claude:sonnet,codex,codex:gpt-5.1 --jobs 6

# results table (also printed after every run)
./bench.py summary
```

Model specs are `runner[:model]` — the part after `:` is passed straight to
the CLI's `--model`/`-m` flag. Attempts already recorded for a (date, model)
pair are skipped; pass `--rerun` to redo them (the summary uses the latest
attempt per pair).

No dependencies beyond Python 3.10+ and the two CLIs on PATH.
