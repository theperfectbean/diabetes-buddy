# VS Code + GitHub Copilot Setup - Quick Start

Get Diabetes Buddy working with GitHub Copilot in VS Code in 5 minutes.

## Prerequisites

- VS Code installed
- GitHub Copilot subscription
- Python 3.8+

## Step 1: Install MCP Extension

Open VS Code and install the MCP extension:

**Method A: Command Palette**
1. Press `Ctrl+Shift+P` (Windows/Linux) or `Cmd+Shift+P` (macOS)
2. Type: `Extensions: Install Extensions`
3. Search for: `Model Context Protocol` or `MCP`
4. Click Install

**Method B: Terminal**
```bash
code --install-extension modelcontextprotocol.mcp
```

## Step 2: Open Project in VS Code

```bash
cd /home/gary/diabetes-buddy
code .
```

The `.vscode/settings.json` is already configured! It will:
- Use the workspace Python interpreter
- Load GEMINI_API_KEY from your environment
- Connect the MCP server to Copilot

## Step 3: Set API Key

Make sure your API key is available:

**Option A: Use .env file** (Already set up)
```bash
# Already exists in .env file
GEMINI_API_KEY=your-key-here
```

**Option B: Export in terminal**
```bash
export GEMINI_API_KEY="your-key-here"
```

**Option C: Add to VS Code settings**
Edit `.vscode/settings.json` and replace:
```json
"GEMINI_API_KEY": "${env:GEMINI_API_KEY}"
```
with:
```json
"GEMINI_API_KEY": "your-actual-key-here"
```

## Step 4: Reload VS Code

1. Press `Ctrl+Shift+P` (or `Cmd+Shift+P`)
2. Type: `Developer: Reload Window`
3. Press Enter

## Step 5: Test with Copilot Chat

1. Open Copilot Chat: `Ctrl+Alt+I` (or `Cmd+Opt+I`)
2. Type one of these commands:

```
@workspace use diabetes-buddy to explain what Ease-off mode is
```

```
@workspace search theory for exercise advice
```

```
@workspace use search_ypsomed to find cartridge instructions
```

## Expected Output

You should see:
```
Classification: CAMAPS (95% confidence)
Safety Status: INFO

Answer: "Ease-off" is a setting within the CamAPS FX app designed to...
(CamAPS FX User Manual, Page 40)

---
**Disclaimer:** This is educational information only...
```

## Troubleshooting

### "MCP server not found"
```bash
# Verify MCP extension is installed
code --list-extensions | grep mcp

# If not installed, install it
code --install-extension modelcontextprotocol.mcp
```

### "Python not found"
```bash
# Activate venv first
source .venv/bin/activate

# Or update settings.json with absolute path
"command": "/home/gary/diabetes-buddy/.venv/bin/python"
```

### "GEMINI_API_KEY not set"
```bash
# Check if .env exists
cat .env

# Or set it directly in terminal
export GEMINI_API_KEY="your-key"

# Then reload VS Code
```

### Test Server Manually
```bash
# Test the MCP server directly
python mcp_server.py

# You should see:
# 🔧 Initializing Diabetes Buddy agents...
# ✅ Agents ready!
# (waits for input)
```

Press Ctrl+C to exit.

### Check MCP Logs

1. In VS Code: View → Output (`Ctrl+Shift+U`)
2. Select "MCP: diabetes-buddy" from dropdown
3. Look for connection errors

## Available Commands

Use these in Copilot Chat (`@workspace` prefix):

| Command | Description |
|---------|-------------|
| `use diabetes-buddy to [question]` | Ask any diabetes question |
| `use search_theory to [query]` | Search Think Like a Pancreas |
| `use search_camaps to [query]` | Search CamAPS FX manual |
| `use search_ypsomed to [query]` | Search Ypsomed pump manual |
| `use search_libre to [query]` | Search Libre 3 CGM manual |
| `use get_knowledge_sources` | List all available sources |

## Tips

### Faster Queries
First query processes PDFs (3-5 min). Subsequent queries are fast (3-5s).

### Use Specific Commands
More specific = better results:
```
❌ "tell me about Ease-off"
✅ "@workspace use diabetes-buddy to explain what Ease-off mode is"
```

### Reference Sources
```
@workspace use search_camaps to find Boost mode settings
```

### Combine Multiple Sources
```
@workspace compare what theory says about exercise with CamAPS recommendations
```

## Next Steps

- See [MCP_SETUP.md](MCP_SETUP.md) for detailed configuration
- See [README.md](README.md) for full documentation
- Run `python verify_install.py` to check installation

---

**You're ready!** Open Copilot Chat and start asking diabetes questions. 🎉
