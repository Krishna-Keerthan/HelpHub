---
name: day-review
description: Day-end review of a git range - runs the deterministic gate, then the relevant reviewer agents one after another and prints one combined report. Use ONLY when explicitly requested.
argument-hint: "[git range, default HEAD~1..HEAD]"
allowed-tools: Bash(scripts/gate.sh *) Bash(git diff *) Bash(git log *) Bash(git status *)
---
Range = `$ARGUMENTS` if given, else `HEAD~1..HEAD`. Do not edit any file.

## 1. Gate
Run `scripts/gate.sh` from the repo root (never in parallel with another pytest session). If it exits non-zero, print its output and STOP; no agents run.

## 2. Choose agents
Run `git diff --name-only <range>`. If empty, say "Empty range" and stop. Pick:
- `tenant-reviewer` and `design-reviewer`: any path under `backend/app/` or `backend/alembic/`.
- `test-quality-reviewer`: any path under `backend/tests/`.
- `security-auditor`, ONLY if a changed path matches one of: `app/api/`, `app/core/`, `app/services/documents`, upload or extraction code (`uploads`, `extraction`, `pdf_worker`), chat or LLM code (`chat`, `llm`, `prompts`), search or ES code (`search`, `es_`, `reindex`), config (`config.py`, `.env.example`), Docker or compose files, dependencies (`pyproject.toml`, `uv.lock`), or `alembic/`.

## 3. Run
Call the chosen agents one after another (never in parallel) with the Agent tool, `subagent_type` = the agent name, prompt = `Range: <range>`. If an agent's output exceeds 40 lines, or an agent reports editing a file, flag it in the report.

## 4. Report
Print ONE combined report of at most 40 lines:
- line 1: `Range <range>: gate ok; agents: <names>`
- then per agent a header `## <name>` followed by its findings verbatim (drop its closing count line), merged by severity within the agent
- if over 40 lines, keep the highest-severity findings and end with `(+N more omitted)`
- last line: `Total findings: <n>`
