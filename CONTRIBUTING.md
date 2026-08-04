# Contributing to DouHotCrawler

Thanks for your interest in contributing. This document covers how to set up the project, run tests, make changes, and open a pull request.

## Getting Started

### Prerequisites

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/) — project and dependency manager
- Git

### Setup

```bash
git clone <repo-url>
cd crael4i-demo
uv sync
```

This installs all runtime dependencies into a `.venv` at the project root.

### Verify

```bash
uv run pytest -q
```

All tests should pass before you start making changes.

## Project Structure

```
crael4i-demo/
├── douhot_crawler/       # Main application package
│   ├── core/             # Config, models, and Excel persistence
│   ├── browser/          # Browser setup, login, patch, and cookies
│   ├── crawling/         # Crawl orchestration and page automation
│   ├── transcript/       # Transcript extraction and cookie handling
│   ├── services/         # MCP job lifecycle and per-user storage
│   ├── interfaces/       # CLI and MCP entry points
│   ├── ui/               # Qt desktop app, settings, and resources
│   └── __main__.py       # Package CLI entry point
├── scripts/              # Build and launch scripts
│   ├── build_package.sh  # PyInstaller packaging
│   └── pyinstaller_gui.py  # PyInstaller entry point
├── tests/                # Unit tests
├── build/                # PyInstaller build artifacts (gitignored)
├── dist/                 # Packaged output (gitignored)
├── .github/workflows/    # CI/CD
├── pyproject.toml        # Project metadata and dependencies
└── README.md
```

## Development

### Running the GUI

```bash
uv run douhot-gui
```

### Running the CLI crawler

```bash
uv run douhot-crawl --keyword "美容" --result-type "视频总榜" --time-range "近7天"
```

### Running the login CLI

```bash
uv run douhot-login
```

## Code Style

- Python 3.12+ syntax (`from __future__ import annotations` is used).
- Type hints are expected on public functions and methods.
- Follow the patterns in the existing code: dataclass models, async/await for I/O, Qt signals/slots for GUI threading.
- Keep comments in Chinese for domain-specific logic (the target platform is Chinese); code identifiers and docstrings may be in either language.
- Use `pathlib.Path` for filesystem paths, never raw strings.

## Testing

Tests use `pytest` with `pytest-asyncio`; some small test classes still use
Python's built-in `unittest` assertions:

```bash
# Run all tests
uv run pytest -q

# Run a single test file
uv run pytest tests/test_cookie_status.py -q
```

When adding new features, include tests that cover:
- The happy path
- Common edge cases (missing files, expired data, network errors)
- Platform-specific behavior (especially Windows-only code paths)

## Packaging

The desktop bundle is built with PyInstaller:

```bash
bash scripts/build_package.sh
```

This produces a standalone folder at `dist/DouHotCrawler/`. The output is a self-contained directory — do not move the `.exe` out of it.

Releases are triggered by pushing a `v*` tag or manually dispatching the workflow on GitHub Actions. The CI matrix currently targets `windows-x86_64`.

## Commit Conventions

This project follows [Conventional Commits](https://www.conventionalcommits.org/). Every commit message must use one of these prefixes:

| Prefix | Usage |
|--------|-------|
| `feat:` | A new feature or enhancement |
| `fix:` | A bug fix |
| `refactor:` | Code restructuring that neither fixes a bug nor adds a feature |
| `chore:` | Maintenance tasks (deps, build, tooling, cleanup) |
| `test:` | Adding or updating tests |
| `docs:` | Documentation changes |

### Format

```
<type>: <short description in English>

Optional body explaining the motivation, approach, or trade-offs.
Keep lines wrapped at 72 characters.
```

Good examples from this repo:

```
feat: add diagnostics to cookie inspection for debugging profile path issues
fix: handle sys.stdin being None in PyInstaller --windowed mode
chore: relax chromium install timeout to 10 minutes
refactor: modularize douhot crawler mvp
```

### Rules

- The subject line must be **in English** and start with a lowercase letter after the prefix.
- Use the **imperative mood** ("add" not "added").
- Keep the subject under 72 characters — be concise.
- If the change is Windows-specific, mention it in the body, not just the subject.
- One logical change per commit. Split unrelated work into separate commits.

## Branch Naming

Name your branch with one of these prefixes, followed by a short kebab-case description:

| Prefix | Purpose |
|--------|---------|
| `feat/` | New features (`feat/transcript-batch-export`) |
| `fix/` | Bug fixes (`fix/cookie-encoding-error`) |
| `refactor/` | Refactoring (`refactor/browser-setup-cache`) |
| `chore/` | Maintenance (`chore/update-pyinstaller-config`) |

## Pull Request Process

### Before Opening

1. Create a feature branch from `main` using the naming convention above.
2. Make your changes, following the [Code Style](#code-style) and [Commit Conventions](#commit-conventions).
3. Add or update tests as needed.
4. Run the test suite locally — all tests must pass.
5. If you changed browser or GUI logic, manually smoke-test the GUI on Windows.
6. Rebase on `main` and resolve any conflicts. Keep a clean, linear history.

### PR Title

Use the same Conventional Commit format for the PR title:

```
feat: add batch export for transcript results
fix: resolve cookie read error on non-Default profiles
```

The PR title becomes the merge commit message, so it should summarize the entire change at a high level — not just the last commit.

### PR Description

Use this template when opening a PR:

```markdown
## What

Briefly describe the change and its motivation.

## Why

Explain why this approach was chosen. Link any related issues.

## How to Test

Step-by-step instructions to verify the change works:

1. ...
2. ...

## Screenshots / Logs

If the change affects the GUI, include before/after screenshots.
If it changes CLI output, paste sample output.

## Checklist

- [ ] Code follows the project style
- [ ] Tests added/updated and passing
- [ ] Manual smoke test done (if GUI or browser related)
- [ ] No new warnings or errors in the log
```

### Review

1. The CI workflow runs tests on every PR. Wait for it to pass.
2. At least one maintainer must approve before merging.
3. Address all review comments — respond to each thread, push fixup commits, then squash when ready.
4. Once approved, the author merges their own PR (squash-and-merge is preferred for multi-commit PRs; single-commit PRs may be rebased).

## Key Constraints

- **Native packaging**: CI builds Windows x86_64, Linux x86_64, and macOS arm64 bundles. Keep platform-specific behavior behind `sys.platform` guards.
- **Chrome / Edge first**: the app prefers a system-installed Chrome or Edge browser. Chromium download via Playwright is a fallback. Changes to browser detection should not regress system browser discovery.
- **Cookie safety**: never log, display, or write cookie values to disk outside the designated Chromium profile or `cookie.config`. The cookie status module is intentionally read-only on cookie contents.
- **No telemetry**: do not introduce analytics or unrelated network calls. The only expected remote access is browser automation and the explicitly configured transcript API.

## Need Help?

Open an issue with:
- What you're trying to do
- Your environment (Windows version, Python version, browser version)
- Any relevant error output or logs
