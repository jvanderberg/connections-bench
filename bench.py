#!/usr/bin/env python3
"""Benchmark LLM CLIs (claude, codex) on NYT Connections puzzles.

Puzzles are fetched from the public NYT endpoint and cached in puzzles/.
Each model gets one shot at grouping the 16 words; the attempt is graded
against the official answer and appended to results/runs.jsonl.

Usage:
  ./bench.py run --date 2026-07-04
  ./bench.py run --start 2026-06-01 --end 2026-06-30 --models claude,codex:gpt-5.1
  ./bench.py summary
"""

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUZZLE_DIR = ROOT / "puzzles"
RESULTS_FILE = ROOT / "results" / "runs.jsonl"

NYT_URL = "https://www.nytimes.com/svc/connections/v2/{date}.json"

PROMPT_TEMPLATE = """\
Solve this NYT Connections puzzle. Group the 16 words below into 4 groups of \
exactly 4 words each. Each group shares a common theme, and each word belongs \
to exactly one group. Beware of red herrings: some words seem to fit more than \
one theme, but only one complete grouping uses every word exactly once.

Words (in board order):
{words}

This is a single-shot attempt: give your one best complete answer. Do not use \
any tools, searches, or external lookups. Respond with ONLY a JSON object in \
exactly this format, with no other text before or after it:
{{"groups": [{{"theme": "...", "words": ["W1", "W2", "W3", "W4"]}}, {{"theme": "...", "words": ["W1", "W2", "W3", "W4"]}}, {{"theme": "...", "words": ["W1", "W2", "W3", "W4"]}}, {{"theme": "...", "words": ["W1", "W2", "W3", "W4"]}}]}}
"""


# ---------------------------------------------------------------- puzzles

def fetch_puzzle(date: str) -> dict:
    """Return the puzzle for YYYY-MM-DD, fetching and caching if needed."""
    PUZZLE_DIR.mkdir(exist_ok=True)
    cache = PUZZLE_DIR / f"{date}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    req = urllib.request.Request(
        NYT_URL.format(date=date), headers={"User-Agent": "connections-bench"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    if data.get("status") != "OK":
        raise RuntimeError(f"NYT returned status {data.get('status')} for {date}")
    cache.write_text(json.dumps(data, indent=2))
    return data


def board_words(puzzle: dict) -> list[str]:
    cards = [c for cat in puzzle["categories"] for c in cat["cards"]]
    return [c["content"] for c in sorted(cards, key=lambda c: c["position"])]


def answer_groups(puzzle: dict) -> dict[frozenset, str]:
    """Map frozenset of normalized words -> category title."""
    return {
        frozenset(norm(c["content"]) for c in cat["cards"]): cat["title"]
        for cat in puzzle["categories"]
    }


def norm(word: str) -> str:
    return word.strip().strip('"').upper()


# ---------------------------------------------------------------- runners

def parse_model_spec(spec: str) -> tuple[str, str | None, str | None]:
    """Parse 'runner[:model][@effort]'.

    'claude' -> ('claude', None, None)
    'claude:haiku' -> ('claude', 'haiku', None)
    'codex:@low' -> ('codex', None, 'low')  # default model, low reasoning
    'claude:sonnet@low' -> ('claude', 'sonnet', 'low')
    """
    runner, _, rest = spec.partition(":")
    if runner not in RUNNERS:
        raise ValueError(f"unknown runner {runner!r} in model spec {spec!r}")
    model, _, effort = rest.partition("@")
    return runner, model or None, effort or None


def secret(name: str) -> str:
    """Read a secret from the environment, falling back to the .env file."""
    val = os.environ.get(name)
    if not val:
        env_file = ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                k, _, v = line.strip().partition("=")
                if k == name and v:
                    val = v.strip().strip('"')
    if not val:
        raise RuntimeError(f"{name} not set (export it or put it in .env)")
    return val


def codex_api_home() -> Path:
    """A private CODEX_HOME so API-key runs don't touch ~/.codex auth."""
    home = ROOT / ".codex-api"
    home.mkdir(exist_ok=True)
    (home / "auth.json").write_text(
        json.dumps({"OPENAI_API_KEY": secret("OPENAI_API_KEY")}))
    (home / "config.toml").write_text('preferred_auth_method = "apikey"\n')
    return home


def run_openrouter(prompt: str, model: str | None, effort: str | None,
                   timeout: int) -> dict:
    if not model:
        raise ValueError("openrouter spec needs a model, e.g. "
                         "openrouter:deepseek/deepseek-v4-pro")
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "usage": {"include": True},
    }
    if effort:
        body["reasoning"] = {"effort": effort}
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {secret('OPENROUTER_API_KEY')}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    if data.get("error"):
        raise RuntimeError(f"openrouter error: {data['error']}")
    usage = data.get("usage", {})
    details = usage.get("completion_tokens_details") or {}
    return {
        "text": data["choices"][0]["message"].get("content") or "",
        "tokens_in": usage.get("prompt_tokens", 0),
        "tokens_in_cached": (usage.get("prompt_tokens_details") or {}).get(
            "cached_tokens", 0),
        "tokens_out": usage.get("completion_tokens", 0),
        "tokens_reasoning": details.get("reasoning_tokens"),
        "cost_usd": usage.get("cost"),
        "model_used": data.get("model", model),
    }


def run_claude(prompt: str, model: str | None, effort: str | None,
               timeout: int) -> dict:
    cmd = ["claude", "-p", "--tools", "", "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    if effort:
        cmd += ["--effort", effort]
    proc = subprocess.run(
        cmd, input=prompt, capture_output=True, text=True, timeout=timeout
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr[:500]}")
    data = json.loads(proc.stdout)
    usage = data.get("usage", {})
    return {
        "text": data.get("result", ""),
        "tokens_in": usage.get("input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0),
        "tokens_in_cached": usage.get("cache_read_input_tokens", 0),
        "tokens_out": usage.get("output_tokens", 0),
        "tokens_reasoning": None,  # not broken out separately by claude CLI
        "cost_usd": data.get("total_cost_usd"),
        "model_used": max(
            data.get("modelUsage", {}).items(),
            key=lambda kv: kv[1].get("outputTokens", 0),
            default=(None, None),
        )[0],
    }


def run_codex(prompt: str, model: str | None, effort: str | None,
              timeout: int, api: bool = False) -> dict:
    env = os.environ.copy()
    if api:
        env["CODEX_HOME"] = str(codex_api_home())
    cmd = [
        "codex", "exec",
        "--skip-git-repo-check",
        "--sandbox", "read-only",
        "-c", "tools.web_search=false",
        "--ephemeral",
        "--color", "never",
        "--json",
    ]
    if model:
        cmd += ["-m", model]
    if effort:
        cmd += ["-c", f"model_reasoning_effort={effort}"]
    cmd.append(prompt)
    proc = subprocess.run(
        cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        timeout=timeout, env=env,
    )
    if proc.returncode != 0:
        detail = ""
        for line in proc.stdout.splitlines():
            if '"error"' in line or line.startswith("ERROR"):
                detail = line.strip()[:300]
        raise RuntimeError(
            f"codex exited {proc.returncode}: {detail or proc.stderr[:300]}")
    text, usage = "", {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item", {})
        if event.get("type") == "item.completed" and item.get("type") == "agent_message":
            text = item.get("text", "")
        elif event.get("type") == "turn.completed":
            usage = event.get("usage", {})
    return {
        "text": text,
        "tokens_in": usage.get("input_tokens", 0) - usage.get("cached_input_tokens", 0),
        "tokens_in_cached": usage.get("cached_input_tokens", 0),
        "tokens_out": usage.get("output_tokens", 0),
        "tokens_reasoning": usage.get("reasoning_output_tokens"),
        "cost_usd": None,  # codex CLI does not report cost
        "model_used": model,
    }


def run_codex_api(prompt: str, model: str | None, effort: str | None,
                  timeout: int) -> dict:
    return run_codex(prompt, model, effort, timeout, api=True)


RUNNERS = {"claude": run_claude, "codex": run_codex,
           "codex-api": run_codex_api, "openrouter": run_openrouter}


# ---------------------------------------------------------------- grading

def extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a model response (may be fenced)."""
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = [fence.group(1)] if fence else []
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start : i + 1])
                    break
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue
    return None


def grade(text: str, answers: dict[frozenset, str]) -> dict:
    parsed = extract_json(text)
    result = {"parsed": False, "valid": False, "correct_groups": 0, "solved": False,
              "guess": None}
    if not parsed or not isinstance(parsed.get("groups"), list):
        return result
    result["parsed"] = True
    guess = []
    for g in parsed["groups"]:
        words = g.get("words") if isinstance(g, dict) else None
        if not isinstance(words, list):
            return result
        guess.append({"theme": g.get("theme", ""), "words": [str(w) for w in words]})
    result["guess"] = guess

    all_answer_words = set().union(*answers)
    guess_sets = [frozenset(norm(w) for w in g["words"]) for g in guess]
    used = [w for s in guess_sets for w in s]
    result["valid"] = (
        len(guess_sets) == 4
        and all(len(s) == 4 for s in guess_sets)
        and len(used) == 16
        and set(used) == all_answer_words
    )
    result["correct_groups"] = sum(1 for s in guess_sets if s in answers)
    result["solved"] = result["correct_groups"] == 4
    return result


# ---------------------------------------------------------------- results

def load_runs() -> list[dict]:
    if not RESULTS_FILE.exists():
        return []
    runs = []
    for line in RESULTS_FILE.read_text().splitlines():
        if line.strip():
            runs.append(json.loads(line))
    return runs


def append_run(run: dict) -> None:
    RESULTS_FILE.parent.mkdir(exist_ok=True)
    with RESULTS_FILE.open("a") as f:
        f.write(json.dumps(run) + "\n")


# ---------------------------------------------------------------- commands

def attempt(date: str, spec: str, timeout: int) -> dict:
    puzzle = fetch_puzzle(date)
    runner, model, effort = parse_model_spec(spec)
    prompt = PROMPT_TEMPLATE.format(words="\n".join(board_words(puzzle)))
    run = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "date": date,
        "puzzle_id": puzzle.get("id"),
        "model": spec,
        "runner": runner,
    }
    start = time.monotonic()
    try:
        out = RUNNERS[runner](prompt, model, effort, timeout)
    except Exception as e:  # noqa: BLE001 - record any failure as a failed run
        run.update({"error": f"{type(e).__name__}: {e}", "solved": False,
                    "correct_groups": 0, "duration_s": round(time.monotonic() - start, 1)})
        return run
    run["duration_s"] = round(time.monotonic() - start, 1)
    graded = grade(out["text"], answer_groups(puzzle))
    run.update(graded)
    run.update({k: out[k] for k in
                ("tokens_in", "tokens_in_cached", "tokens_out", "tokens_reasoning",
                 "cost_usd", "model_used")})
    run["raw"] = out["text"]
    return run


def cmd_run(args: argparse.Namespace) -> None:
    if args.date:
        dates = [args.date]
    elif args.start and args.end:
        d = dt.date.fromisoformat(args.start)
        end = dt.date.fromisoformat(args.end)
        dates = []
        while d <= end:
            dates.append(d.isoformat())
            d += dt.timedelta(days=1)
    else:
        sys.exit("run requires --date, or --start and --end")

    specs = [s.strip() for s in args.models.split(",") if s.strip()]
    done = {(r["date"], r["model"]) for r in load_runs() if not r.get("error")}
    tasks = [(d, s) for d in dates for s in specs
             if args.rerun or (d, s) not in done]
    skipped = len(dates) * len(specs) - len(tasks)
    if skipped:
        print(f"skipping {skipped} attempt(s) already recorded (use --rerun to redo)")
    if not tasks:
        return

    # Pre-fetch serially so parallel attempts hit the cache, and so a bad
    # date fails fast before any model spends tokens.
    for d in dates:
        fetch_puzzle(d)

    print(f"running {len(tasks)} attempt(s) with {args.jobs} worker(s)")
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(attempt, d, s, args.timeout): (d, s) for d, s in tasks}
        for fut in concurrent.futures.as_completed(futures):
            run = fut.result()
            append_run(run)
            if run.get("error"):
                status = f"ERROR {run['error'][:80]}"
            else:
                status = ("SOLVED" if run["solved"]
                          else f"failed ({run['correct_groups']}/4 groups)")
                status += (f"  in={run['tokens_in'] + run['tokens_in_cached']}"
                           f" out={run['tokens_out']} tok, {run['duration_s']}s")
            print(f"  {run['date']}  {run['model']:<24} {status}")
    cmd_summary(args)


def cmd_summary(_args: argparse.Namespace) -> None:
    runs = load_runs()
    if not runs:
        print("no runs recorded yet")
        return
    # Keep only the latest attempt per (date, model).
    latest: dict[tuple, dict] = {}
    for r in runs:
        latest[(r["date"], r["model"])] = r
    by_model: dict[str, list[dict]] = {}
    for r in latest.values():
        by_model.setdefault(r["model"], []).append(r)

    print(f"\n{'model':<24} {'puzzles':>7} {'solved':>6} {'rate':>6} "
          f"{'avg grp':>7} {'avg out tok':>11} {'avg cost':>9} {'avg time':>8}")
    for model in sorted(by_model):
        rs = by_model[model]
        ok = [r for r in rs if not r.get("error")]
        solved = sum(1 for r in ok if r.get("solved"))
        avg_grp = sum(r.get("correct_groups", 0) for r in ok) / len(ok) if ok else 0
        avg_out = (sum(r.get("tokens_out") or 0 for r in ok) / len(ok)) if ok else 0
        costs = [r["cost_usd"] for r in ok if r.get("cost_usd") is not None]
        avg_cost = f"${sum(costs) / len(costs):.3f}" if costs else "-"
        avg_time = (sum(r.get("duration_s", 0) for r in ok) / len(ok)) if ok else 0
        errs = len(rs) - len(ok)
        line = (f"{model:<24} {len(rs):>7} {solved:>6} "
                f"{solved / len(ok) * 100 if ok else 0:>5.0f}% "
                f"{avg_grp:>7.2f} {avg_out:>11.0f} {avg_cost:>9} {avg_time:>7.0f}s")
        if errs:
            line += f"  ({errs} error(s))"
        print(line)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="run models against puzzle date(s)")
    run_p.add_argument("--date", help="single puzzle date YYYY-MM-DD")
    run_p.add_argument("--start", help="range start YYYY-MM-DD")
    run_p.add_argument("--end", help="range end YYYY-MM-DD")
    run_p.add_argument("--models", default="claude,codex",
                       help="comma-separated specs: runner[:model][@effort], "
                            "e.g. claude:haiku,claude:sonnet@low,codex:@low "
                            "(default: claude,codex)")
    run_p.add_argument("--jobs", type=int, default=4, help="parallel attempts")
    run_p.add_argument("--timeout", type=int, default=600,
                       help="per-attempt timeout in seconds")
    run_p.add_argument("--rerun", action="store_true",
                       help="rerun even if already recorded")
    run_p.set_defaults(func=cmd_run)

    sum_p = sub.add_parser("summary", help="print results table")
    sum_p.set_defaults(func=cmd_summary)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
