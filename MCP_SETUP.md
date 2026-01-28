# MCP Server Setup for Diabetes Buddy

This guide shows how to use Diabetes Buddy from VS Code with GitHub Copilot via the Model Context Protocol (MCP).

## Quick Setup for VS Code

### 1. Install MCP Extension

Install the MCP extension for VS Code:
```bash
# Using VS Code command palette (Ctrl+Shift+P / Cmd+Shift+P)
# Search: "Extensions: Install Extensions"
# Search for: "MCP" or "Model Context Protocol"
```

Or install manually:
```bash
code --install-extension modelcontextprotocol.mcp
```

### 2. Configure MCP Server in VS Code

Open VS Code settings (`.vscode/settings.json` in your workspace or global settings):

**Option A: Workspace Settings** (Recommended)
Create `.vscode/settings.json` in your project:

```json
{
  "mcp.servers": {
    "diabetes-buddy": {
      "command": "python",
      "args": ["/home/gary/diabetes-buddy/mcp_server.py"],
      "env": {
        "GEMINI_API_KEY": "your-gemini-api-key-here"
      }
    }
  }
}
```

**Option B: Global Settings**
1. Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on macOS)
2. Type "Preferences: Open User Settings (JSON)"
3. Add the MCP configuration above

**Important:** Replace `/home/gary/diabetes-buddy/mcp_server.py` with the actual absolute path to your installation.

**Important:** Replace `your-gemini-api-key-here` with your actual Gemini API key.

### 3. Reload VS Code

Reload the window:
- Press `Ctrl+Shift+P` (or `Cmd+Shift+P`)
- Type "Developer: Reload Window"
- Press Enter

### 4. Verify Installation with Copilot

The Diabetes Buddy tools should now be available to GitHub Copilot Chat:

1. Open Copilot Chat (Ctrl+Alt+I or Cmd+Opt+I)
2. Type: `@workspace use diabetes-buddy to explain what Ease-off mode is`
3. Copilot will use the MCP tools to answer

Available tools in Copilot Chat:
- 🔨 `diabetes_query` - Ask diabetes questions with safety auditing
- 📚 `search_theory` - Search Think Like a Pancreas
- 🤖 `search_camaps` - Search CamAPS FX manual
- 💉 `search_ypsomed` - Search Ypsomed pump manual  
- 📊 `search_libre` - Search Libre 3 CGM manual
- ℹ️ `get_knowledge_sources` - List available sources

## Usage Examples with GitHub Copilot

Once installed, use Copilot Chat to query the diabetes knowledge base:

### Example 1: General Query
```
You: @workspace use diabetes-buddy to explain what Ease-off mode is

Copilot: [Uses diabetes_query tool]
Classification: CAMAPS (95% confidence)
Safety Status: INFO

Answer: "Ease-off" is a setting within the CamAPS FX app designed to deliver 
less insulin than the app would normally calculate. It can be used by people 
of any age when they require less insulin than usual...
(CamAPS FX User Manual, Page 40)

---
**Disclaimer:** This is educational information only. Always consult your 
healthcare provider before making changes to your diabetes management routine.
```

### Example 2: Search Specific Manual
```
You: @workspace search the Ypsomed manual for cartridge change instructions

Copilot: [Uses search_ypsomed tool]
Result 1 (92% confidence, Page 91):
To change your pump cartridge on a mylife YpsoPump, follow these steps...
```

### Example 3: Compare Information
```
You: @workspace what does Think Like a Pancreas say about exercise?

Copilot: [Uses search_theory tool]
Result 1 (89% confidence, Page 156):
Exercise increases insulin sensitivity and can cause blood sugar to drop...
```

## Available Tools

### `diabetes_query`
**Purpose:** General diabetes questions with full safety auditing  
**Input:** `question` (string)  
**Output:** Classified answer with source citations and safety status

### `search_theory`
**Purpose:** Search Think Like a Pancreas directly  
**Input:** `query` (string)  
**Output:** Relevant quotes with page numbers

### `search_camaps`
**Purpose:** Search CamAPS FX manual directly  
**Input:** `query` (string)  
**Output:** Relevant quotes with page numbers

### `search_ypsomed`
**Purpose:** Search Ypsomed pump manual directly  
**Input:** `query` (string)  
**Output:** Relevant quotes with page numbers

### `search_libre`
**Purpose:** Search Libre 3 CGM manual directly  
**Input:** `query` (string)  
**Output:** Relevant quotes with page numbers

### `get_knowledge_sources`
**Purpose:** List all available knowledge sources  
**Input:** None  
**Output:** Source descriptions and coverage areas

## Safety Features
 in Copilot
1. Verify MCP extension is installed: `code --list-extensions | grep mcp`
2. Check that the path in `settings.json` is correct and absolute
3. Reload VS Code window: `Ctrl+Shift+P` → "Developer: Reload Window"
4. Check VS Code Output panel: View → Output → Select "MCP" from dropdown

### Connection Errors
1. Ensure Python 3.8+ is in your PATH: `python --version`
2. Verify dependencies are installed: `pip install -r requirements.txt`
3. Check that `GEMINI_API_KEY` is set in settings.json or .env file
4. Test server manually: `python /home/gary/diabetes-buddy/mcp_server.py`

### Copilot Not Using Tools
1. Use explicit syntax: `@workspace use diabetes-buddy to [query]`
2. Try referencing specific tools: `@workspace use search_theory to find...`
3. Ensure MCP server is running (check VS Code Output panel)

### Slow Responses
**First-time setup:** If using ChromaDB backend, first query per source takes 1-2 minutes to process PDFs and create embeddings. Subsequent queries are fast (3-5s).

**File API mode:** Each query takes 13-17s. Consider switching to ChromaDB backend for better performance.

### Check Logs
View MCP server output in VS Code:
1. View → Output (Ctrl+Shif, use the venv's Python:

```json
{
  "mcp.servers": {
    "diabetes-buddy": {
      "command": "/home/gary/diabetes-buddy/.venv/bin/python",
      "args": ["/home/gary/diabetes-buddy/mcp_server.py"
### Slow Responses
**First-time setup:** If using ChromaDB backend, first query per source takes 1-2 minutes to process PDFs and create embeddings. Subsequent queries are fast (3-5s).

**File API mode:** Each query takes 13-17s. Consider switching to ChromaDB backend for better performance.

### Check Logs
View MCP server output in Claude Desktop's Developer Console:
- **macOS**: `~/Library/Logs/Claude/mcp*.log`
- **Linux**: `~/.config/Claude/logs/mcp*.log`

## Configuration Options

### Using a Virtual Environment

If your project uses a venv:

```json
{
  "mcpServers": {
    "diabetes-buddy": {
      "command": "/home/gary/diabetes-buddy/.venv/bin/python",
      "args": [
        "/home/gary/diabetes-buddy/mcp_server.py"
      ],
      "env": {
        "GEMINI_API_KEY": "your-key-here"
      }
    }
  }
}
```

### Using ChromaDB Backend

The MCP server automatically uses the ChromaDB backend if available (much faster). No configuration needed - it will detect and use it automatically.

### Custom Cache Directory

Set a custom cache locatiVS Code settings.json (secure, local file)
- All queries are processed locally except Gemini API calls
- No data is sent to third parties beyond Google's Gemini API
- Safety auditing happens locally before responses are returned
- MCP server runs as a subprocess, isolated from VS Code

## Updates

To update Diabetes Buddy:

```bash
cd /home/gary/diabetes-buddy
git pull
pip install -r requirements.txt --upgrade
```

Reload VS Code window to apply updates: `Ctrl+Shift+P` → "Developer: Reload Window"nd Google's Gemini API
- Safety auditing happens locally before responses are returned

## Updates

To update Diabetes Buddy:

```bash
cd /home/gary/diabetes-buddy
git pull
pip install -r requirements.txt --upgrade
```

Restart Claude Desktop to load updates.

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review Claude Desktop logs
3. Run `python mcp_server.py` manually to test
4. Check project documentation at `/docs/`
