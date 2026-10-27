---
applyTo: "**/*.py"
description: "Use when writing, analyzing, modifying, running, debugging, reviewing, or discussing Python code."
---
Diagnostic identifier: coding2

# Coding Instructions

## Environment
- Language: Python
- Package manager: uv
- Virtual environment: pre-created at `.venv/` — do not recreate it
- Always run Python commands via `uv run`
- We use strict type checking. Please fix pylance and ruff warnings.
- Ask me before suppressing any warnings or errors.
- We're using python >= 3.12, so we can use the latest language features.
- By default we mostly avoid experimental features that require `from __future__ import` statements. It is ok to use these features if they bring appropriate value to offset the risks. Ask if you want to use one of these features. 

## Code Style
- Prefer imports at the top of each file
- Deferred imports (inside functions) acceptable for performance reasons and some architectural reasons — document why if used
- We use markdown for design documents. It is ok to include Mermaid diagrams in markdown files.
- We use unicode characters directly in code and markdown. Avoid using unicode escape sequences.
- Comments state what we do, not the alternatives we rejected, unless their absence would read as a bug.

## Git
- After completing each task, propose a commit message summarizing the changes
- Use conventional commit format: `type(scope): description` (e.g. `feat(auth): add login endpoint`)

## Tests

Tests are derived from the spec, not from implementations.
A test that conflicts with `docs/specs/` is wrong — fix the test, not the spec.
Before writing a new test, identify which spec document it validates.
