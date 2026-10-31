# Prompts for Claude Code

Use these in order. The first is for Plan mode. The second is the overnight run.

## 1. Planning prompt (Plan mode, do this while awake)

```text
Read CLAUDE.md, SPEC.md, DECISIONS.md, and docs/REQUIREMENTS.md.
Do not write code yet. Give me:
1. A short plan for milestones M1 to M12.
2. Anything in SPEC.md that is ambiguous, contradictory, or likely to cause a look-ahead or leakage bug.
3. The three places you think correctness is most at risk, and how the tests will catch each.
Keep it under 400 words.
```

Read the answer. If it flags a real problem in the spec, fix SPEC.md yourself and commit before continuing. Then approve and switch out of Plan mode.

## 2. Overnight prompt (Accept edits or Auto mode)

```text
Read CLAUDE.md, SPEC.md, and DECISIONS.md. Work through milestones M1 to M12 in SPEC.md in order.

After each milestone: run `make check`, fix any failures, then commit with a one-line message that names the milestone.
Do not edit SPEC.md. Do not weaken or delete any test, especially the causality tests.
Log every non-obvious choice in DECISIONS.md as you go.
If something is ambiguous, pick the simplest honest option, log it, and keep going. Do not stop to ask.

There is no real price data in this environment. If data/raw/ has no real CSVs, skip milestone M10, leave the README results block saying NOT RUN ON REAL DATA, and log it in DECISIONS.md. Never present synthetic results as real. Never type a result by hand.

For milestone M12, use a fresh subagent to review the diff against SPEC.md for correctness gaps only (look-ahead, cost accounting, drift, walk-forward leakage, metric definitions, anywhere results could be overstated). Fix real findings and add a regression test for each.

Finish by printing: the final `make check` output, `make demo` output, the list of milestones completed, and anything you skipped or are unsure about.
```

## 3. If the run stopped early

Start a new cloud session on the same branch and send:

```text
Read CLAUDE.md, SPEC.md, and DECISIONS.md. Run `git log --oneline` to see which milestones are done. Continue from the first incomplete milestone in SPEC.md and follow the same rules. Finish with the same final report.
```

## 4. After you run real data locally (morning)

Run `make data && make run && make report`. Then, in a local or new session:

```text
Read reports/real/report.md and the tables it links. Draft a Findings section for the README: what the numbers show, what they do not show, and the limits. Use only numbers that appear in those files. Flag it DRAFT for the owner to verify. Do not call any strategy profitable or investable.
```
