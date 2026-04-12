.PHONY: tui cli

# Build + start TUI
tui:
	pnpm --dir tui build
	node tui/dist/index.js

# Start CLI mode (no TUI)
cli:
	uv run python main.py
