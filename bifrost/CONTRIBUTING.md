# Contributing to Bifrost

Thanks for your interest in contributing. Bifrost is an OpenCode plugin and Python FastMCP companion that bridges agent capabilities. This guide covers how to set up your environment, run tests, follow the code style, and submit changes.

## Table of Contents

- [Dev Environment Setup](#dev-environment-setup)
- [Running Tests](#running-tests)
- [Code Style](#code-style)
- [Project Structure](#project-structure)
- [Pull Request Process](#pull-request-process)
- [Code of Conduct](#code-of-conduct)

## Dev Environment Setup

Bifrost has two components: a Python companion server and a TypeScript plugin. You'll need both toolchains.

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 20+
- npm 9+

### Python Companion

```bash
# From the bifrost/ directory
uv pip install -r requirements.txt

# Verify the server starts
uv run python -m companion.server
```

The companion uses FastMCP over stdio. Dependencies: `fastmcp`, `pyyaml`, `httpx`.

If you're working on companion code, you may also want to install test dependencies:

```bash
uv pip install pytest
```

### TypeScript Plugin

```bash
# From bifrost/plugin/
npm install

# Verify compilation
npx tsc --noEmit
```

The plugin depends on `@opencode-ai/plugin` and is type-checked with strict mode enabled.

## Running Tests

### Python Tests

All Python tests live under `bifrost/tests/` and use pytest:

```bash
# From the bifrost/ directory
uv run pytest tests/ -v

# Run a specific test file
uv run pytest tests/test_classifier_e2e.py -v

# Run with coverage (if pytest-cov is installed)
uv run pytest tests/ --cov=companion --cov-report=term
```

Tests use an SQLite database in a temp directory for isolation (see `conftest.py`). Each test file exercises one companion module: classifier, fusion, memory, skill loading, config migration, and context integration.

### TypeScript Checks

The plugin uses strict TypeScript compilation as its primary quality gate:

```bash
# From bifrost/plugin/
npx tsc --noEmit
```

There are currently no standalone TypeScript test suites. The plugin's correctness is verified through compilation and integration testing with a running OpenCode instance.

## Code Style

### Python

- **Type hints**: All functions must have type annotations. Use `from __future__ import annotations` for forward references.
- **Path handling**: Use `pathlib.Path` instead of `os.path`.
- **Docstrings**: Use Google-style or NumPy-style docstrings for public functions. At minimum, document parameters and return values.
- **Imports**: Standard library first, then third-party, then project modules. Use absolute imports from `companion.*`.
- **Line length**: Aim for 88 characters (Black-compatible). Not strictly enforced, but keep it readable.
- **Error handling**: Return typed error dictionaries rather than raising bare exceptions. The companion runs as a long-lived MCP process and must be resilient.

### TypeScript

- **Strict mode**: `tsconfig.json` has `"strict": true`. No `any` without explicit `// eslint-disable-next-line`.
- **Module system**: ES modules (`NodeNext` resolution). Use `import`/`export`, not `require`.
- **File organization**: Keep plugin hooks in `index.ts`. Transport logic (MCP relay, health check) lives in separate files.
- **Naming**: camelCase for functions and variables, PascalCase for types and interfaces.

### General

- Don't commit secrets, API keys, or `.db` files (see `.gitignore`).
- Run both `pytest` and `tsc --noEmit` before pushing.
- If you add a new companion module, register its MCP tool in `companion/server.py`.

## Project Structure

```
bifrost/
├── companion/           # Python FastMCP companion server
│   ├── server.py        # MCP tool registration and server entrypoint
│   ├── config.py        # Default configuration values
│   ├── db.py            # SQLite database layer
│   ├── classifier/      # Tool-call safety classifier
│   ├── context/         # Conversation context provider
│   ├── fusion/          # Multi-model fusion dispatch
│   ├── goal/            # Classifier-gated goal loop
│   ├── memory/          # Persistent memory (store, search, list)
│   ├── permission/      # Config migration tools
│   └── skill/           # Skill discovery and loader
├── plugin/              # TypeScript OpenCode plugin
│   ├── index.ts         # Main plugin hooks
│   ├── mcp-relay.ts     # MCP relay transport to companion
│   ├── health.ts        # Companion health check
│   └── package.json     # npm dependencies
├── tests/               # Python test suite
│   ├── conftest.py      # Shared fixtures (temp DB, etc.)
│   └── test_*.py        # Per-module tests
├── LICENSE              # MIT license
├── README.md            # Project overview
├── CONTRIBUTING.md      # This file
├── SKILL_COMPAT.md      # Skill compatibility matrix
└── requirements.txt     # Python dependencies
```

## Pull Request Process

1. **Open an issue first**. Describe the bug or feature before writing code. This lets maintainers confirm the change is in scope.
2. **Fork and branch**. Create a feature branch from `main` with a descriptive name (e.g., `fix-classifier-timeout`, `add-skill-cache`).
3. **Keep it small**. Each PR should address one concern. Split large changes into multiple PRs.
4. **Run the full test suite**. Both `uv run pytest tests/ -v` and `npx tsc --noEmit` must pass.
5. **Write a clear PR description**. Explain what changed, why, and how to verify it. Link the original issue.
6. **Wait for review**. A maintainer will review within a few days. Be ready to respond to feedback.
7. **No direct pushes to `main`**. All changes go through PR review.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). Be respectful, constructive, and inclusive. Harassment of any kind will not be tolerated.

## Questions?

Open an issue on the repository. For setup help, include your Python version, Node version, and the exact error message you're seeing.
