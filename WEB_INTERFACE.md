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
    "safety": true
  }
}
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
