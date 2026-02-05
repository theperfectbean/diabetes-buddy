# Docker Deployment Guide

Run Diabetes Buddy in a container for easy deployment and sharing.

## Quick Start

### 1. Create your `.env` file

```bash
cp .env.example .env
```

Edit `.env` and add your Gemini API key:
```
GEMINI_API_KEY=your-actual-api-key-here
```

### 2. Start with Docker Compose

```bash
docker compose up -d
```

### 3. Access the web interface

Open http://localhost:8000

## Commands

```bash
# Start in background
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down

# Rebuild after code changes
docker compose up -d --build

# Remove everything (including cached embeddings)
docker compose down -v
```

## First Run

The first startup takes 3-5 minutes because ChromaDB needs to:
1. Extract text from all PDF manuals
2. Generate embeddings via Gemini API
3. Store vectors in the local database

Subsequent starts are fast (~5 seconds) because embeddings are cached in a Docker volume.

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Google Gemini API key |

### Ports

| Port | Service |
|------|---------|
| 8000 | Web interface |

### Volumes

| Volume | Purpose |
|--------|---------|
| `diabetes-buddy-chromadb` | Persists ChromaDB embeddings |

## Production Deployment

### Using Docker directly

```bash
# Build the image
docker build -t diabetes-buddy .

# Run with API key
docker run -d \
  --name diabetes-buddy \
  -p 8000:8000 \
  -e GEMINI_API_KEY="your-key" \
  -v diabetes-buddy-chromadb:/app/.cache/chromadb \
  --restart unless-stopped \
  diabetes-buddy
```

### With reverse proxy (nginx)

Example nginx configuration:

```nginx
server {
    listen 80;
    server_name diabetes.example.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### With HTTPS (Caddy)

```
diabetes.example.com {
    reverse_proxy localhost:8000
}
```

Caddy automatically handles SSL certificates.

## Updating

```bash
# Pull latest code
git pull

# Rebuild and restart
docker compose up -d --build
```

## Troubleshooting

### Container won't start

Check logs:
```bash
docker compose logs diabetes-buddy
```

Common issues:
- Missing `GEMINI_API_KEY` environment variable
- Port 8000 already in use

### Slow first query

Normal - ChromaDB is processing PDFs on first run. Wait 3-5 minutes.

### Out of memory

ChromaDB embedding generation needs ~1GB RAM. Increase Docker memory limit if needed.

### Reset embeddings

To force re-processing of PDFs:
```bash
docker compose down -v
docker compose up -d
```

## Health Check

The container includes a health check that verifies the API is responding:

```bash
# Check container health
docker inspect diabetes-buddy --format='{{.State.Health.Status}}'

# Should return: healthy
```

## Image Size

- Base image: ~150MB (python:3.12-slim)
- Dependencies: ~700MB (includes ChromaDB, PyPDF2, etc.)
- Application + PDFs: ~50MB
- **Total: ~900MB**

## Security Notes

1. **Never commit `.env` files** - they contain your API key
2. **Use secrets management** in production (Docker secrets, Vault, etc.)
3. **Enable HTTPS** when exposing to the internet
4. **Rate limiting** is built-in (10 req/min per IP)
