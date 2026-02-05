```markdown
# Diabetes Buddy – Copilot / Claude Sonnet Project Instructions

You are working in my local `~/diabetes-buddy` repo on Arch Linux.

## Environment – CRITICAL

Before running ANY Python command, ALWAYS do:

```bash
cd ~/diabetes-buddy
source venv/bin/activate
```

Never assume the venv is already active.

## Allowed Files for Web UI Work

When fixing web UI / rendering / streaming issues, you may ONLY edit:

- `web/index.html`
- `web/static/app.js`
- `web/static/styles.css`

Do NOT touch:

- Any `vscode-file://` or editor‑internal paths
- VS Code extension files
- Global system files outside this repo

## General Rules

- No code should be pasted back into the chat; modify files directly.
- Prefer adding small automated tests (CLI or headless) over asking me to use DevTools.
- I will only:
  - Hard‑refresh the browser
  - Say what I see (e.g., “still one big paragraph”)

You must own all debugging and validation steps that can be done from within this repo and the terminal.
```