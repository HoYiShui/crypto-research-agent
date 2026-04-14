/**
 * Prelude TUI
 *
 * Chat interface for the crypto research agent.
 * Spawns Python bridge as a subprocess, communicates via JSONL over stdio.
 */

import chalk from "chalk";
import { spawn, ChildProcessWithoutNullStreams } from "child_process";
import * as path from "path";
import * as fs from "fs";
import { fileURLToPath } from "url";
import {
  CancellableLoader,
  CombinedAutocompleteProvider,
  Editor,
  Key,
  Markdown,
  matchesKey,
  ProcessTerminal,
  Spacer,
  Text,
  TUI,
  type EditorTheme,
  type MarkdownTheme,
} from "@mariozechner/pi-tui";

// ── Themes ────────────────────────────────────────────────────────────────────

const editorTheme: EditorTheme = {
  borderColor: (s: string) => chalk.cyan(s),
  selectList: {
    selectedPrefix: (s: string) => chalk.cyan(s),
    selectedText: (s: string) => chalk.inverse(s),
    description: (s: string) => chalk.dim(s),
    scrollInfo: (s: string) => chalk.dim(s),
    noMatch: (s: string) => chalk.dim(s),
  },
};

const markdownTheme: MarkdownTheme = {
  heading: (s: string) => chalk.bold.cyan(s),
  link: (s: string) => chalk.blue.underline(s),
  linkUrl: (s: string) => chalk.blue.underline(s),
  code: (s: string) => chalk.bgHex("#1e1e1e").white(s),
  codeBlock: (s: string) => chalk.bgHex("#1e1e1e").white(s),
  codeBlockBorder: (s: string) => chalk.dim(s),
  quote: (s: string) => chalk.dim(s),
  quoteBorder: (s: string) => chalk.dim("│ "),
  hr: (s: string) => chalk.dim("─".repeat(40)),
  listBullet: (s: string) => chalk.dim("  " + s),
  bold: (s: string) => chalk.bold(s),
  italic: (s: string) => chalk.italic(s),
  strikethrough: (s: string) => chalk.strikethrough(s),
  underline: (s: string) => chalk.underline(s),
};

const userMarkdownTheme: MarkdownTheme = {
  ...markdownTheme,
};

// ── Bridge process ────────────────────────────────────────────────────────────

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, "..", "..");
const bridgeScript = path.join(projectRoot, "app", "bridge", "pi_bridge.py");

function findPython(): string {
  const venvPython = path.join(projectRoot, ".venv", "bin", "python");
  if (fs.existsSync(venvPython)) return venvPython;
  return "python3";
}

function spawnBridge(): ChildProcessWithoutNullStreams {
  const python = findPython();
  const proc = spawn(python, [bridgeScript], {
    cwd: projectRoot,
    stdio: ["pipe", "pipe", "pipe"],
    env: { ...process.env },
  });
  return proc;
}

// ── Main ──────────────────────────────────────────────────────────────────────

class CtrlCTerminal extends ProcessTerminal {
  private onCtrlC: () => void;

  constructor(onCtrlC: () => void) {
    super();
    this.onCtrlC = onCtrlC;
  }

  start(onInput: (data: string) => void, onResize: () => void): void {
    super.start((data: string) => {
      if (data.includes("\u0003") || matchesKey(data, Key.ctrl("c"))) {
        this.onCtrlC();
        return;
      }
      onInput(data);
    }, onResize);
  }
}

async function main() {
  let isShuttingDown = false;
  let bridge: ChildProcessWithoutNullStreams | null = null;

  const shutdown = (code: number = 0) => {
    if (isShuttingDown) return;
    isShuttingDown = true;
    try {
      tui.stop();
    } catch {}
    try {
      if (bridge && bridge.exitCode === null && !bridge.killed) {
        bridge.kill();
      }
    } catch {}
    process.exit(code);
  };

  const terminal = new CtrlCTerminal(() => shutdown(0));
  const tui = new TUI(terminal);

  tui.addChild(new Text(chalk.bold.cyan("Prelude") + chalk.dim(" — crypto research agent")));
  tui.addChild(new Text(chalk.dim("Type your question. /reset to clear history. Ctrl+C to exit.")));
  tui.addChild(new Spacer(1));

  const editor = new Editor(tui, editorTheme);
  const autocomplete = new CombinedAutocompleteProvider(
    [{ name: "reset", description: "Clear conversation history" }],
    projectRoot
  );
  editor.setAutocompleteProvider(autocomplete);
  tui.addChild(editor);
  tui.setFocus(editor);

  tui.start();

  bridge = spawnBridge();
  let bridgeReady = false;
  let isResponding = false;
  let lineBuffer = "";

  const initLoader = new CancellableLoader(
    tui,
    (s: string) => chalk.dim(s),
    (s: string) => chalk.dim(s),
    "Starting agent..."
  );
  const children = tui.children;
  children.splice(children.length - 1, 0, initLoader);
  tui.requestRender();

  bridge.stderr.on("data", (data: Buffer) => {
    const text = data.toString();
    if (text.includes("BRIDGE_READY")) {
      bridgeReady = true;
      tui.removeChild(initLoader);
      tui.requestRender();
    }
  });

  bridge.stdout.on("data", (data: Buffer) => {
    lineBuffer += data.toString();
    const lines = lineBuffer.split("\n");
    lineBuffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      handleBridgeMessage(trimmed);
    }
  });

  bridge.on("close", (code) => {
    if (isShuttingDown) return;
    if (code !== 0) {
      process.stderr.write(`Bridge exited with code ${code}\n`);
    }
    shutdown(code ?? 0);
  });

  let currentLoader: CancellableLoader | null = null;

  function handleBridgeMessage(line: string) {
    let msg: Record<string, unknown>;
    try {
      msg = JSON.parse(line);
    } catch {
      return;
    }

    const t = msg["type"] as string;

    if (t === "tool_call") {
      const name = msg["name"] as string;
      const notice = new Text(chalk.dim("  ") + chalk.yellow("↳ " + name));
      const idx = currentLoader ? children.indexOf(currentLoader) : -1;
      children.splice(idx >= 0 ? idx : children.length - 1, 0, notice);
      tui.requestRender();

    } else if (t === "assistant_message") {
      if (currentLoader) {
        tui.removeChild(currentLoader);
        currentLoader = null;
      }
      const content = (msg["content"] as string) ?? "";
      children.splice(children.length - 1, 0, new Markdown(content, 1, 1, markdownTheme));
      children.splice(children.length - 1, 0, new Spacer(1));
      isResponding = false;
      editor.disableSubmit = false;
      tui.requestRender();

    } else if (t === "error") {
      if (currentLoader) {
        tui.removeChild(currentLoader);
        currentLoader = null;
      }
      children.splice(children.length - 1, 0, new Text(chalk.red("Error: " + (msg["content"] as string))));
      isResponding = false;
      editor.disableSubmit = false;
      tui.requestRender();

    } else if (t === "reset_done") {
      children.splice(3, children.length - 4);
      children.splice(3, 0, new Text(chalk.dim("History cleared.")));
      tui.requestRender();
    }
  }

  function sendToBridge(msg: Record<string, unknown>) {
    if (!bridge) return;
    bridge.stdin.write(JSON.stringify(msg) + "\n");
  }

  editor.onSubmit = (value: string) => {
    if (isResponding) return;
    if (!bridgeReady) {
      children.splice(children.length - 1, 0, new Text(chalk.yellow("Agent is still starting up, please wait...")));
      tui.requestRender();
      return;
    }

    const trimmed = value.trim();
    if (!trimmed) return;

    if (trimmed === "/reset") {
      sendToBridge({ type: "reset" });
      return;
    }

    isResponding = true;
    editor.disableSubmit = true;

    children.splice(children.length - 1, 0, new Text(chalk.cyan("You")));
    children.splice(children.length - 1, 0, new Markdown(trimmed, 1, 0, userMarkdownTheme));
    children.splice(children.length - 1, 0, new Spacer(1));

    currentLoader = new CancellableLoader(
      tui,
      (s: string) => chalk.cyan(s),
      (s: string) => chalk.dim(s),
      "Thinking..."
    );
    children.splice(children.length - 1, 0, currentLoader);
    tui.requestRender();

    sendToBridge({ type: "user_message", content: trimmed });
  };

  process.on("SIGINT", () => shutdown(0));
  process.on("SIGTERM", () => shutdown(0));
}

main().catch((err) => {
  process.stderr.write(String(err) + "\n");
  process.exit(1);
});
