<div align="center">
  <img src="assets/FreeSWE_logo.png" alt="FreeSWE" width="760" />
  <h1>FreeSWE</h1>
  <p><strong>Realistic single-file issue injection for SWE-style benchmarks</strong></p>
  <p>Generate behaviorally meaningful buggy states from correct code, validate the resulting patch, and keep the complete provenance of each run.</p>
</div>

## Overview

FreeSWE packages two complementary issue-injection modes behind one small
command-line interface. Both modes start from a verified, correct source file
and produce an injected file plus a unified diff that can be applied to the
original file.

![FreeSWE framework](assets/framework.png)

The vector figure is available as [PDF](assets/framework.pdf).

### What is different

| Mode | Model interaction | Final artifact |
|---|---|---|
| **Numbered Fixed** | A model sees the fixed file with reference line numbers and directly proposes an issue patch. | `<issue_patch>` → injected file + unified diff |
| **Task Plan + Executor** | A planner proposes a task plan and problem statement; a separate executor implements that plan in the fixed file. | `<task_plan>` → `<modified_file>` → injected file + unified diff |

The planner decides the task. The executor implements the plan. Keeping these
roles separate is important: the executor is not asked to invent a different
bug after seeing the plan.

## Installation

Python 3.10 or newer is required.

```bash
git clone <repository-url>
cd FreeSWE
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
```

The client uses the official OpenAI SDK defaults when no runtime endpoint
override is supplied. For another OpenAI-compatible server, set the endpoint
through an environment variable at runtime; no provider-specific URL is stored
in this repository.

## Quick start

Set a credential and the model identifiers in the shell that launches FreeSWE.
They are intentionally not stored in configuration files or output metadata.

```bash
export OPENAI_API_KEY='your-key'
```

The example source is deliberately small and contains no repository-specific
information:

```text
examples/fixed_context.py
```

### Numbered Fixed

The input file itself remains unnumbered. Reference numbers are added only to
the model prompt, and the returned patch must apply to the original source
without those prefixes.

```bash
export NUMBERED_FIXED_MODEL='your-numbered-fixed-model'

freeswe numbered-fixed \
  --model "$NUMBERED_FIXED_MODEL" \
  --input examples/fixed_context.py \
  --output-dir outputs/numbered_fixed
```

The model must return exactly:

```text
<issue_patch>
diff --git a/fixed_context.py b/fixed_context.py
...
</issue_patch>
```

### Task Plan + Executor

The planner returns both a structured implementation plan and a natural
language problem statement. The executor receives the fixed source and the
plan, then returns the complete modified file. The problem statement is saved
but is not passed to the executor by default; use the flag only for an
intentional problem-statement variant.

```bash
export TASK_PLAN_MODEL='your-task-plan-model'
export TASK_PLAN_EXECUTOR_MODEL='your-task-plan-executor-model'

freeswe task-plan \
  --planner-model "$TASK_PLAN_MODEL" \
  --executor-model "$TASK_PLAN_EXECUTOR_MODEL" \
  --input examples/fixed_context.py \
  --output-dir outputs/task_plan
```

The expected planner format is:

```text
<task_plan>...</task_plan>
<problem_statement>...</problem_statement>
```

The expected executor format is:

```text
<modified_file>
...complete modified source file...
</modified_file>
```

## Validation and safety checks

Every generated result passes the same local validation sequence:

1. exactly one target file is changed;
2. the patch is applied with `git apply`;
3. if the first apply fails, the runner retries with `git apply --recount`;
4. the resulting file is checked by a reverse-apply roundtrip;
5. only then are `injected_file` and `injection.patch` marked successful.

The package does not run a repository-wide test suite. Repository-level Docker
evaluation and benchmark orchestration are intentionally outside this minimal,
public release.

## Output layout

Each run writes only relative artifact names inside the requested output
directory:

```text
messages.json                 # sanitized prompt messages
planner_messages.json         # Task Plan mode only
executor_messages.json        # Task Plan mode only
model_raw_output.txt          # Numbered Fixed mode only
planner_raw_output.txt        # Task Plan mode only
executor_raw_output.txt       # Task Plan mode only
task_plan.txt                 # Task Plan mode only
problem_statement.txt         # Task Plan mode only, when returned
modified_file                 # Task Plan mode only
injected_file                 # validated issue-state file
injection.patch               # validated single-file unified diff
result.json                   # status, patch statistics, and validation details
```

`result.json` records the selected model identifier but never records API keys,
runtime credentials, absolute input paths, or endpoint values.

## Runtime configuration

The following values are runtime-only:

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | API credential |
| `OPENAI_BASE_URL` | Optional OpenAI-compatible endpoint override |
| `OPENAI_MODEL` | Fallback model identifier |
| `NUMBERED_FIXED_MODEL` | Numbered Fixed model identifier |
| `TASK_PLAN_MODEL` | Planner model identifier |
| `TASK_PLAN_EXECUTOR_MODEL` | Executor model identifier |

Command-line model options override the corresponding environment variables.
Never commit a real `.env` file or generated output containing proprietary
source code.

## Repository structure

```text
FreeSWE/
├── assets/
│   ├── FreeSWE_logo.png
│   ├── framework.pdf
│   └── framework.png
├── examples/
│   └── fixed_context.py
├── src/freeswe/
│   ├── api.py                  # provider-neutral OpenAI SDK client
│   ├── cli.py                  # unified CLI
│   ├── numbered_fixed.py       # direct patch generation
│   ├── task_plan.py            # planner + executor generation
│   └── patches.py              # single-file validation and apply fallback
├── tests/
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

## Development

```bash
python -m pip install -e .
python -m pytest -q
```

The test suite uses a fake model client and makes no network requests.

## Scope and limitations

- Current release: single-file issue injection only.
- The code does not bundle model checkpoints or select a particular hosted
  model automatically.
- The code does not include benchmark data, Docker images, repository clones,
  or repo-bounded evaluation infrastructure.
- Multi-file orchestration can be added later without changing the two
  single-file output contracts.
