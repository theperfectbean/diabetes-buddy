# Web Interface Quick Start

## Running the Web App

### Start the Server

```bash
cd /home/gary/diabetes-buddy
source .venv/bin/activate
python web/app.py
```

The server will start on **http://localhost:8000**

### Access the Chat Interface

Open your browser and go to: **http://localhost:8000**

## Features

### Core Features
- **Real-time Chat** - Ask diabetes questions instantly
- **Auto-classification** - Questions routed to relevant knowledge sources
- **Safety Auditing** - All responses checked for dangerous content
- **Source Citations** - Know exactly where information comes from
- **Responsive Design** - Works on desktop, tablet, and mobile

### New Features (v1.2) - Data Analysis

#### Data Analysis Tab
- **Upload Glooko Exports**: Drag & drop or click to upload ZIP files
- **Time in Range Gauge**: Visual semicircle gauge showing TIR percentage
- **Key Metrics Dashboard**: Average glucose, std deviation, CV%, total readings
- **Glucose Distribution Bar**: Color-coded below/in-range/above breakdown
- **Pattern Detection**: Dawn phenomenon, post-meal spikes, nocturnal hypos
- **Research Questions**: Click to send pattern-based questions to chat
- **Analysis History**: Browse and reload previous analyses

#### Tab Navigation
- Click "Chat" or "Data Analysis" tabs in the header
- Tabs persist state when switching between views
- Questions from data analysis automatically switch to chat

### New Features (v1.1)

#### Dark Mode
- Click the moon/sun icon in the header to toggle
- Persists your preference in localStorage
- Respects system preference (`prefers-color-scheme`)

#### Conversation History
- Chat history persists across page refreshes
- Stores last 50 messages in localStorage
- Click "New Chat" to start fresh

#### Export Conversations
- Click "Export" button in header
- Choose format: plain text or JSON
- Downloads chat with timestamps and metadata

#### Copy to Clipboard
- Each response has a "Copy" button
- Copies the full answer text
- Shows "Copied!" confirmation

#### Suggested Questions
- Welcome screen shows 3 example questions
- Click any suggestion to ask it instantly
- Helps new users understand capabilities

#### Improved Loading States
- Skeleton loading animation while processing
- "Searching knowledge base..." status message
- Smooth transitions

#### Accessibility
- ARIA labels throughout
- Keyboard navigation (Tab, Escape)
- Focus trap in modals
- Colorblind-friendly severity indicators (icons + borders)

## API Endpoints

### POST /api/query
Send a diabetes management question

**Request:**
```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "How do I change my pump cartridge?"}'
```

**Response:**
```json
{
  "query": "How do I change my pump cartridge?",
  "classification": "ypsomed",
  "confidence": 0.95,
  "severity": "INFO",
  "answer": "To change your pump cartridge...",
  "sources": [
    {
      "source": "Ypsomed Pump Manual",
      "page": 91,
      "excerpt": "...",
      "confidence": 0.92,
      "full_excerpt": "..."
    }
  ],
  "disclaimer": "This is educational information only..."
}
```

**Rate Limits:** 10 requests per minute per IP

**Validation:**
- Query must be 3-2000 characters
- Empty queries return 400 error
- Rate limit exceeded returns 429 error

### GET /api/sources
List all available knowledge sources

```bash
curl http://localhost:8000/api/sources
```

### GET /api/health
Health check endpoint

```bash
curl http://localhost:8000/api/health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "Diabetes Buddy Web API",
  "version": "1.0.0",
  "agents": {
    "triage": true,
    "safety": true,
    "glooko": true
  }
}
```

### Glooko Data Analysis Endpoints

#### POST /api/upload-glooko
Upload a Glooko export ZIP file for analysis

```bash
curl -X POST http://localhost:8000/api/upload-glooko \
  -F "file=@glooko_export.zip"
```

**Response:**
```json
{
  "success": true,
  "message": "File uploaded successfully",
  "filename": "glooko_export_20250128_143022.zip",
  "file_path": "/home/gary/diabetes-buddy/data/glooko/glooko_export_20250128_143022.zip",
  "records_found": {
    "glucose_readings": 19381,
    "insulin_records": 85,
    "carb_entries": 100,
    "activity_logs": 0,
    "notes": 0
  }
}
```

**Limits:**
- Maximum file size: 50MB
- Only ZIP files accepted
- Must contain CSV files from Glooko export

#### GET /api/glooko-analysis/latest
Get the most recent analysis results

```bash
curl http://localhost:8000/api/glooko-analysis/latest
```

**Response:**
```json
{
  "success": true,
  "analysis_date": "2025-01-28T14:30:22.123456",
  "file_analyzed": "glooko_export_20250128_143022.zip",
  "metrics": {
    "total_glucose_readings": 19381,
    "date_range_days": 90,
    "average_glucose": 142.5,
    "std_deviation": 45.2,
    "coefficient_of_variation": 31.8,
    "time_in_range_percent": 68.4,
    "time_below_range_percent": 3.2,
    "time_above_range_percent": 28.4
  },
  "patterns": [
    {
      "type": "dawn_phenomenon",
      "description": "Elevated glucose 3am-8am",
      "confidence": 0.72,
      "affected_readings": 1245,
      "recommendation": "Consider adjusting overnight basal rate"
    }
  ],
  "research_queries": [
    {
      "query": "What causes dawn phenomenon and how can CamAPS FX handle it?",
      "pattern_type": "dawn_phenomenon",
      "priority": "high"
    }
  ],
  "warnings": []
}
```

#### GET /api/glooko-analysis/history
List all available analyses

```bash
curl http://localhost:8000/api/glooko-analysis/history
```

**Response:**
```json
{
  "history": [
    {
      "id": "analysis_20250128_143022",
      "date": "2025-01-28T14:30:22.123456",
      "file": "glooko_export_20250128_143022.zip",
      "time_in_range": 68.4,
      "patterns_found": 3
    }
  ],
  "total": 1
}
```

#### POST /api/glooko-analysis/run
Run analysis on a specific file or most recent upload

```bash
# Analyze most recent file
curl -X POST http://localhost:8000/api/glooko-analysis/run

# Analyze specific file
curl -X POST "http://localhost:8000/api/glooko-analysis/run?filename=glooko_export_20250128_143022.zip"
```

#### GET /api/glooko-analysis/{analysis_id}
Get a specific analysis by ID

```bash
curl http://localhost:8000/api/glooko-analysis/analysis_20250128_143022
```

### API Documentation
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## UI Components

### Header
- **Title**: "Diabetes Buddy"
- **Theme Toggle**: Moon/sun icon for dark mode
- **Export**: Download conversation
- **New Chat**: Clear history and start fresh

### Chat Area
- User messages (right-aligned, purple)
- Assistant responses (left-aligned, with citations)
- Severity indicators (INFO/WARNING/BLOCKED with icons)
- Copy button on each response

### Sidebar (Desktop only)
- Lists all knowledge sources
- Think Like a Pancreas
- CamAPS FX User Manual
- Ypsomed Pump Manual
- FreeStyle Libre 3 Manual

### Input Area
- Text input with placeholder
- Send button (shows arrow on mobile)
- Input validation with error messages

### Data Analysis Tab

#### Upload Section
- Drag & drop zone for ZIP files
- Click to open file browser
- Progress bar during upload
- Automatic analysis after upload

#### Dashboard
- **TIR Gauge**: Semicircle gauge showing time-in-range percentage
  - Green: 70%+ (good)
  - Orange: 50-70% (warning)
  - Red: <50% (needs attention)
- **Key Metrics**: Grid showing average glucose, std deviation, CV%, readings
- **Distribution Bar**: Horizontal bar with below/in-range/above percentages

#### Patterns Section
- Cards for each detected pattern
- Confidence indicator (high/medium/low)
- Description and recommendations
- Color-coded border by confidence

#### Research Questions
- Clickable buttons for each suggested question
- Priority badges (high/medium/low)
- Click sends question to chat tab

#### History
- List of previous analyses
- TIR badge with color indicator
- Pattern count
- Click to reload analysis

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Enter | Send message |
| Escape | Close modal |
| Tab | Navigate focusable elements |

## Troubleshooting

### Port 8000 Already in Use
```bash
# Find and kill the process
lsof -i :8000
kill -9 <PID>

# Or use a different port
python -c "import uvicorn; from web.app import app; uvicorn.run(app, port=8001)"
```

### Server Not Responding
```bash
# Check if server is running
curl http://localhost:8000/api/health

# Check logs in terminal where server is running
```

### Rate Limit Exceeded
- Wait 60 seconds before retrying
- Rate limit resets per minute

### Dark Mode Not Working
- Check if JavaScript is enabled
- Clear localStorage: `localStorage.clear()`
- Refresh page

### History Not Loading
- Check browser's localStorage quota
- Clear old data: `localStorage.removeItem('diabuddy_history_...')`

### Glooko Upload Failed
- Ensure file is a valid ZIP from Glooko export
- Check file size is under 50MB
- Try downloading a fresh export from Glooko

### Analysis Shows No Data
- Check Glooko export contains CGM/glucose data
- Verify date range in export covers recent data
- Check server logs for parsing errors:
  ```bash
  # Look for parsing warnings in terminal
  ```

### Patterns Not Detected
- Requires sufficient data (ideally 7+ days)
- Very stable glucose may not trigger patterns
- Check if glucose data is in expected format

## Performance

- **First query:** 3-5 seconds (ChromaDB indexes PDFs on first run)
- **Subsequent queries:** 3-5 seconds
- **API latency:** ~100ms for health checks
- **Rate limit:** 10 requests/minute per IP

## Security Features

- **Input validation**: Min 3, max 2000 characters
- **Rate limiting**: Prevents abuse
- **CORS**: Configured for localhost only
- **Safety auditing**: Blocks dangerous medical advice
- **No cookies**: Uses localStorage only

## Browser Support

- Chrome/Chromium 80+
- Firefox 75+
- Safari 13+
- Edge 80+

## Mobile Support

- Responsive design with breakpoints at 768px and 480px
- Touch-friendly buttons
- Send button shows arrow icon on small screens
- iOS zoom prevention (16px font on input)
