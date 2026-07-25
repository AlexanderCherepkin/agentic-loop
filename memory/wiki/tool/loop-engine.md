# Loop Engine

Runtime orchestration for `/goal`, `/loop`, and `/workflows` inside Agentic Loop.

## Overview

The loop engine turns one-off agent tasks into repeatable, self-improving workflows:

- **Cheap executor swarm** (`claude-haiku-4-5`) does the bulk work.
- **Expensive verifier** (`claude-opus-4-8`) runs adversarial verification with ≥2 critics.
- **Cost guard** hard-stops the loop before the budget is exceeded.
- **CONSTRAINTS.md** remembers every verifier finding.
- **Verified workflows** are saved to `memory/wiki/` automatically and to `.claude/skills/` only after human approval.

## Commands

| Command | Purpose |
|---|---|
| `/goal` | One target, worker + verifier, closes automatically when criteria are met. |
| `/loop 10m` | Repeating check on a schedule. |
| `/workflows` or `ultracode:` | Parallel multi-agent orchestration for audits, migrations, large refactors. |

## Trust Levels

| Level | Mode | When to use |
|---|---|---|
| **L1** | Report only | New loop; observe for ≥7 days before promotion. |
| **L2** | Action with approval | Loop is reliable; every action waits for human OK. |
| **L3** | Autonomous | ≤5% rejections in L2 and stable `CONSTRAINTS.md`. |

**Human zones** (never L3): `git push`, deploy, `rm -rf`, database migrations, production secrets, bulk emails, payments.

## Presets

Available presets live in `runtime/loop_presets/`:

- [[anti-slop-sweeper]] — audit generated code for banned patterns.
- [[ci-sweeper]] — fix flaky CI failures and re-run tests.
- [[pr-babysitter]] — summarize open PRs and flag attention items.
- [[dependency-sweeper]] — scan dependencies for CVEs and stale versions.

## Cost Guard

`loop-cost` estimates a preset before execution. If `estimated_usd` exceeds the remaining budget, the loop aborts before any LLM call.

## Self-Improving Cycle

1. Run loop with a preset.
2. Verifier checks output and logs failures.
3. Failures become rules in `.agent_loop/CONSTRAINTS.md`.
4. Next run loads constraints automatically.
5. Once stable, export workflow to `memory/wiki/` and, after approval, to `.claude/skills/`.

## Links

- [[anti-slop-rule-set]] — banned patterns used by the anti-slop sweeper.
- [[cost-tracking]] — budget backend for the cost guard.
- [[spec-pilot]] — spec approval workflow that loops respect.
