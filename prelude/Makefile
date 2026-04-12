.PHONY: tui cli test verify verify-python verify-tui

# Build + start TUI
tui:
	pnpm --dir tui build
	node tui/dist/index.js

# Start CLI mode (no TUI)
cli:
	uv run python main.py

# Run Python tests
test:
	uv run pytest -q

# Verify Python + TUI build gates
verify-python:
	uv run pytest -q

verify-tui:
	pnpm --dir tui build

verify: verify-python verify-tui
