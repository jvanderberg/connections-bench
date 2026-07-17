# connections-bench

Single-shot benchmark of LLMs on the NYT Connections puzzle: each model gets
**one attempt** to group the 16 words into the 4 official groups — no retries,
no feedback, no tools.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/results-dark.png">
  <img alt="Solve-rate grid: 19 models × 20 daily puzzles, with per-model reasoning level, solved counts, average output tokens, and cost" src="assets/results-light.png">
</picture>

## Results (June 25 – July 14, 2026)

| model | reasoning | solved | avg out tokens | avg cost/puzzle |
|---|---|---|---|---|
| GPT-5.5 (codex) | default | **20/20** | 1,248 | – (sub) |
| Claude Fable 5 | high | **20/20** | 1,407 | $0.18 |
| GPT-5.6 Luna | high | **20/20** | 4,257 | – (sub) |
| GPT-5.6 Sol | high | 19/20 | 1,695 | – (sub) |
| GPT-5.6 Terra | high | 19/20 | 1,853 | – (sub) |
| Claude Opus 4.8 | high | 19/20 | 2,324 | $0.11 |
| Claude Opus 4.5 | high | 19/20 | 7,874 | $0.26 |
| Kimi K3 | max | 17/20 | 7,608 | $0.11 |
| Claude Sonnet 5 | high | 16/20 | 5,411 | $0.13 |
| GPT-5.4 mini | default | 16/20 | 10,178 | – (sub) |
| GLM-5.2 | default | 15/20 | 21,713 | $0.073 |
| Kimi K2.6 | default | 15/20 | 22,986 | $0.075 |
| Claude Sonnet 4.5 | high | 13/20 | 5,529 | $0.11 |
| DeepSeek V4 Pro | default | 13/20 | 9,490 | $0.030 |
| Qwen3.6 35B A3B | default | 9/20 | 20,158 | $0.021 |
| MiniMax M3 | default | 9/20 | 31,024 | $0.038 |
| Claude Haiku 4.5 | high | 6/20 | 13,581 | $0.083 |
| DeepSeek V4 Flash | default | 5/20 | 19,964 | $0.005 |
| GPT-4.1 mini | none | 0/20 | 154 | – |

Reasoning levels aren't uniform, so the column is not an apples-to-apples knob:
`high` is pinned explicitly via `@high` in the model spec; `default` means the
benchmark passes no effort and takes whatever the CLI or provider chooses;
`none` is GPT-4.1 mini, which has no reasoning mode; `max` is Kimi K3, which
currently exposes only that one level.

Things the sweep surfaced:

- **Three models swept all twenty**: GPT-5.5 (codex), Claude Fable 5, and
  GPT-5.6 Luna. The GPT-5.6 family went 58/60 across its three variants.
- **Puzzle difficulty swings hard day to day** — July 12 beat all but 6 of 19
  models, while July 3 and July 9 fell to 18. Single-day comparisons are noise,
  and even twenty days is a small sample.
- **Reasoning is the entry ticket.** GPT-4.1 mini (no reasoning) answers in
  ~150 tokens and went 0/20. Everything that deliberates solves at least a few.
- **Capability shows up as token efficiency, not just accuracy.** The sweep's
  three perfect scorers average 1.2–4.3k output tokens; mid-tier models burn
  20–31k for half the solve rate.
- **Kimi K3 leads the open-weight field** — 17/20, well ahead of GLM-5.2 and its
  own predecessor K2.6 (both 15/20), while thinking a third as much as K2.6
  (7.6k vs 23k output tokens). All three of its non-solves were transport
  failures on a model released mid-sweep, never a wrong grouping: it has not
  actually missed a puzzle in 17 valid attempts. See the caveat below — its true
  rate is somewhere between 17/20 and 20/20 and this benchmark can't yet say
  where.
- **DeepSeek V4 Pro is the value pick** — 13/20 at $0.030, a third of K3's cost.

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
./bench.py run --start 2026-06-25 --end 2026-07-04 --models codex:gpt-5.5 --missing --no-record
./bench.py run --date 2026-07-09 --models codex:gpt-5.6-sol@high,codex:gpt-5.6-terra@high,codex:gpt-5.6-luna@high
./bench.py run --date 2026-07-04 --models claude:haiku@low,openrouter:z-ai/glm-5.2
./bench.py summary                               # leaderboard table
python3 viz.py                                   # regenerate viz.html
```

Keys: `OPENROUTER_API_KEY` and `OPENAI_API_KEY` from the environment or a
gitignored `.env`. Attempts already recorded for a (date, model, prompt-version)
are skipped; `--rerun` forces. Errored attempts retry automatically on the next
run. GPT-5.6 requires Codex CLI 0.144.0 or newer.

`--missing` is a harder variant that always removes the first word in board
order. The prompt only says that one word is missing and asks the model to group
the 15 shown words; grading expects three groups of four and one group of three.
Use `summary --missing` to keep its results separate from the standard benchmark.

The figure: `python3 viz.py` then
`npx playwright screenshot --viewport-size "1140,675" --color-scheme light viz.html assets/results-light.png`
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
- **Errors count as failures, and this understates Kimi K3.** K3 released on
  July 16, mid-sweep, and OpenRouter has been rate-limiting it hard: all 3 of its
  non-solves are HTTP 429s, rejected in 0.4–16s before it ran at all. Those score
  as failures, so K3 shows 17/20 — but it solved **all 17** attempts that
  actually returned. Its real rate is somewhere in 17/20–20/20 and this benchmark
  cannot yet say where. Retry passes over two days recovered six other throttled
  attempts (all solved) but never cleared these three, and the throttling ignores
  `--jobs 1`, so it is account-level quota rather than harness concurrency. Rerun
  once Moonshot capacity settles.
- **Kimi K3 is slow because it thinks, not because it's loaded.** Its throughput
  is a near-constant 35.5 tok/s (stdev 2.5) and duration correlates with output
  tokens at r=0.998 — a 978s run is 32k tokens at the same rate as a 24s / 845
  token run. Note `--timeout 900` is therefore too tight for it: a 978s solve is
  already in the data, so any harder puzzle gets scored as a failure it didn't
  earn. Use `--timeout 3600` for K3. (K2.6, by contrast, swings 45–171 tok/s,
  which does look like contention.)
- **OpenRouter pads slow non-streaming responses** with whitespace keepalives
  while waiting on the provider. `json.loads` skips them, but if the provider
  never answers, padding is all you get. `run_openrouter` reports that as
  "no payload" rather than a confusing `JSONDecodeError` at the end of the body.
  Note also that `urlopen`'s timeout is per-socket-operation, so padding would
  reset it forever; `read_with_deadline` bounds the request on total elapsed
  time instead. That deadline is monotonic-clock based, so it does not count
  time the machine spends asleep.
