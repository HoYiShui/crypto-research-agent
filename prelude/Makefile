.PHONY: tui cli test verify verify-python verify-tui tui-install tui-smoke

# Build + start TUI
tui: tui-install
	pnpm --dir tui build
	node tui/dist/index.js

# Start CLI mode (no TUI)
cli:
	uv run python main.py

# Run Python tests
test:
	uv run pytest -q

tui-install:
	CI=true pnpm --dir tui install --frozen-lockfile

# Non-interactive runtime dependency check for pi-tui transitive deps.
tui-smoke:
	node -e "import('./tui/node_modules/@mariozechner/pi-tui/dist/utils.js').then(() => console.log('pi-tui runtime deps OK')).catch((e) => { console.error(e); process.exit(1); })"

# Verify Python + TUI build gates
verify-python:
	uv run pytest -q

verify-tui: tui-install
	pnpm --dir tui build
	$(MAKE) tui-smoke

verify: verify-python verify-tui
