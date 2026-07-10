# connections-bench

Single-shot benchmark of LLMs on the NYT Connections puzzle: each model gets
**one attempt** to group the 16 words into the 4 official groups — no retries,
no feedback, no tools.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/results-dark.png">
  <img alt="Solve-rate grid: 18 models × 10 daily puzzles, with per-model solved counts, average output tokens, and cost" src="assets/results-light.png">
</picture>

## Results (June 25 – July 4, 2026)

| model | solved | avg out tokens | avg cost/puzzle |
|---|---|---|---|
| GPT-5.5 (codex) | **10/10** | 1,336 | – (sub) |
| Claude Fable 5 @high | **10/10** | 1,648 | $0.19 |
| GPT-5.6 Terra @high | **10/10** | 2,211 | – (sub) |
| GPT-5.6 Luna @high | **10/10** | 4,840 | – (sub) |
| Claude Opus 4.5 @high | **10/10** | 7,414 | $0.24 |
| GPT-5.6 Sol @high | 9/10 | 1,299 | – (sub) |
| Claude Opus 4.8 @high | 9/10 | 3,037 | $0.13 |
| GPT-5.4 mini | 9/10 | 10,142 | – (sub) |
| Claude Sonnet 5 @high | 8/10 | 4,112 | $0.10 |
| GLM-5.2 | 8/10 | 17,423 | $0.053 |
| DeepSeek V4 Pro | 7/10 | 12,207 | $0.039 |
| Kimi K2.6 | 7/10 | 23,057 | $0.069 |
| Claude Sonnet 4.5 @high | 6/10 | 5,416 | $0.11 |
| Qwen3.6 35B A3B | 5/10 | 17,235 | $0.018 |
| MiniMax M3 | 4/10 | 38,994 | $0.048 |
| Claude Haiku 4.5 @high | 3/10 | 12,135 | $0.080 |
| DeepSeek V4 Flash | 3/10 | 17,594 | $0.004 |
| GPT-4.1 mini | 0/10 | 153 | – |

Things the sweep surfaced:

- **The GPT-5.6 family went 29/30.** Terra and Luna swept all ten puzzles; Sol
  got 2/4 groups on June 25 despite using the fewest average output tokens.
- **Puzzle difficulty swings hard day to day** — July 3 fell to 17 of 18 models,
  June 25 to only 9. Single-day comparisons are noise.
- **Reasoning is the entry ticket.** GPT-4.1 mini (no reasoning) answers in
  ~150 tokens and went 0/10. Everything that deliberates solves at least a few.
- **Capability shows up as token efficiency, not just accuracy.** The top models
  average 1–5k output tokens; mid-tier models burn 10–40k for worse results.
- **GLM-5.2 is the open-weight standout** — 8/10 for half a cent per solve-tier
  performance, matching Claude Sonnet 5.

## How it works

- **Puzzles** come from NYT's public JSON endpoint
  (`https://www.nytimes.com/svc/connections/v2/<YYYY-MM-DD>.json`), cached in
  `puzzles/` (gitignored). Any date since 2023-06-12 works.
- **The prompt is deliberately bare** — the 16 words in board order plus the
  answer shape, nothing else. No rules, no "4 groups of 4", no red-herring
  warning (early testing showed those hints measurably help weaker models):

  ```
  Solve the puzzle:

  <the 16 words, one per line>

  Respond with ONLY a JSON object, no other text:
  {"groups": [{"theme": "...", "words": ["...", "..."]}, ...]}
  ```

- **Runners** (specs are `runner[:model][@effort]`):
  - `claude:<model>[@effort]` — `claude -p --tools ""` (Claude Code CLI, all tools disabled)
  - `codex[:<model>][@effort]` — `codex exec --sandbox read-only -c tools.web_search=false`
    on the ChatGPT account
  - `codex-api:<model>` — same, but with an isolated `CODEX_HOME` using
    `OPENAI_API_KEY` (unlocks models the ChatGPT plan rejects)
  - `openrouter:<model-id>` — direct chat-completions API call (no agent harness)
- **Anti-cheat**: answers for a given day are published all over the web, so
  web search and tools are disabled in every runner.
- **Grading** ignores theme labels. Solved = all four 4-word groupings match
  exactly. Partial credit recorded as `correct_groups` (0, 1, 2, or 4 — three
  correct implies four).
- **Records**: every attempt appends to `results/runs.jsonl` with token counts
  (in/cached/out/reasoning), cost where the API reports it, duration, the parsed
  guess, the raw response, and a `prompt_v` tag so prompt revisions never mix.

## Usage

```sh
./bench.py run --date 2026-07-04                 # roster from models.txt
./bench.py run --start 2026-06-25 --end 2026-07-04 --jobs 6
./bench.py run --date 2026-07-09 --models codex:gpt-5.6-sol@high,codex:gpt-5.6-terra@high,codex:gpt-5.6-luna@high
./bench.py run --date 2026-07-04 --models claude:haiku@low,openrouter:z-ai/glm-5.2
./bench.py summary                               # leaderboard table
python3 viz.py                                   # regenerate viz.html
```

Keys: `OPENROUTER_API_KEY` and `OPENAI_API_KEY` from the environment or a
gitignored `.env`. Attempts already recorded for a (date, model, prompt-version)
are skipped; `--rerun` forces. Errored attempts retry automatically on the next
run. GPT-5.6 requires Codex CLI 0.144.0 or newer.

The figure: `python3 viz.py` then
`npx playwright screenshot --viewport-size "1012,650" --color-scheme light viz.html assets/results-light.png`
(and again with `dark`).

## Caveats

- **Training-data contamination**: puzzles before each model's cutoff may have
  been memorized. All dates here (mid-2026) post-date every tested model's
  cutoff, but be careful benchmarking the 2023–2024 archive.
- **Harness asymmetry**: claude/codex attempts run inside their agent CLIs
  (system prompts included); OpenRouter attempts are raw API calls.
- **Costs**: claude numbers are the CLI's API-metered figure (notional if you're
  on a subscription); codex ChatGPT-account runs don't report cost; OpenRouter
  is exact.
- One attempt per (date, model) — solve rates on 10 puzzles carry ±1-puzzle
  noise; treat close rankings as ties.
