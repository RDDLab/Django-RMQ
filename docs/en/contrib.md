---
title: Contribution Guide
order: 13
---

# Contribution guide

We welcome contributions to Django-RMQ. This guide covers the basic local workflow for development, testing, and
documentation.

If you are not sure whether a change fits the project, open an issue or a draft pull request first.

Please keep changes focused and include tests when behavior changes.

## Setting up environment

The project uses `uv` for Python dependency management. To install it, follow the official guide in
the [uv documentation](https://docs.astral.sh/uv/getting-started/installation/).

After cloning the repository, install dependencies:

```bash
uv sync --all-extras
```

## Linting

Run Ruff locally before opening a pull request:

```bash
uv run ruff check .
uv run ruff format --check .
```

## Testing

Run the test suite with pytest:

```bash
uv run pytest
```

You can also use tox to test against configured environments:

```bash
tox
```

## Working with documentation

Documentation is built with [VuePress 2](https://vuepress.vuejs.org/) and `vuepress-theme-hope`.

Install Node dependencies:

```bash
npm install
```

Run the documentation server with hot reload:

```bash
npm run docs:dev
```

Build and preview the production documentation:

```bash
npm run docs:build
npm run docs:serve
```

## Project conventions

All Python code in this repository follows the rules below (enforced by Ruff and pyrefly in CI):

- **Full typing** — annotate every function parameter, return value, and variable. The project targets `pyrefly` strict
  mode.
- **No relative imports** — always use absolute imports (`from django_rmq.producer import Producer`, not
  `from .producer import Producer`).
- **Key-value call parameters** — pass arguments by keyword where possible (
  `Producer(queue='orders').publish(body='...')`).
- **`uv run` instead of `python`** — run scripts and management commands as `uv run python manage.py ...` or
  `uv run pytest`.
