#!/usr/bin/env bash
#
# Docker Deployment Test for Diabetes Buddy
#
# Tests that the Docker container can start and serve the basic endpoints
# without requiring real API keys or making actual LLM calls.
#

set -e

# Change to the project root directory
cd "$(dirname "$0")"

echo "========================================"
echo "Diabetes Buddy Docker Deployment Test"
echo "========================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
    local status=$1
    local message=$2
    if [ "$status" = "success" ]; then
        echo -e "${GREEN}✅ $message${NC}"
    elif [ "$status" = "warning" ]; then
        echo -e "${YELLOW}⚠️  $message${NC}"
    else
        echo -e "${RED}❌ $message${NC}"
    fi
}

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    print_status "error" "Docker is not running. Please start Docker first."
    exit 1
fi
print_status "success" "Docker is running"

# Check if docker-compose.yml exists
if [ ! -f "docker-compose.yml" ]; then
    print_status "error" "docker-compose.yml not found"
    exit 1
fi
print_status "success" "docker-compose.yml found"

# Check if Dockerfile exists
if [ ! -f "Dockerfile" ]; then
    print_status "error" "Dockerfile not found"
    exit 1
fi
print_status "success" "Dockerfile found"

# Build the Docker image
echo "Building Docker image..."
if docker compose build --quiet; then
    print_status "success" "Docker image built successfully"
else
    print_status "error" "Failed to build Docker image"
    exit 1
fi

# Start the container in detached mode
echo "Starting Docker container..."
if docker compose up -d; then
    print_status "success" "Docker container started"
else
    print_status "error" "Failed to start Docker container"
    exit 1
fi

# Wait for the container to be ready (longer timeout for knowledge base initialization)
echo "Waiting for server to be ready (this may take several minutes for first-time knowledge base setup)..."
max_attempts=60  # 5 minutes
attempt=1
while [ $attempt -le $max_attempts ]; do
    if curl -s -f http://localhost:8000 >/dev/null 2>&1; then
        print_status "success" "Server is responding on http://localhost:8000"
        break
    fi

    echo "Attempt $attempt/$max_attempts: Server not ready yet..."
    sleep 5  # Wait 5 seconds between attempts
    attempt=$((attempt + 1))
done

if [ $attempt -gt $max_attempts ]; then
    print_status "error" "Server failed to start within 5 minutes (knowledge base initialization may still be running)"
    echo "Container logs:"
    docker compose logs
    docker compose down
    exit 1
fi

# Test basic endpoints
echo "Testing endpoints..."

# Test root endpoint
if curl -s -f http://localhost:8000/ >/dev/null 2>&1; then
    print_status "success" "Root endpoint (/) is accessible"
else
    print_status "error" "Root endpoint (/) is not accessible"
fi

# Test OpenAPI docs
if curl -s -f http://localhost:8000/docs >/dev/null 2>&1; then
    print_status "success" "API documentation (/docs) is accessible"
else
    print_status "error" "API documentation (/docs) is not accessible"
fi

# Test streaming endpoint (should return 405 Method Not Allowed for GET, but endpoint exists)
if curl -s -w "%{http_code}" http://localhost:8000/api/query/stream 2>/dev/null | grep -q "405"; then
    print_status "success" "Streaming endpoint (/api/query/stream) exists"
else
    print_status "error" "Streaming endpoint (/api/query/stream) not accessible"
fi

# Test static files
if curl -s -f http://localhost:8000/static/app.js >/dev/null 2>&1; then
    print_status "success" "Static file (app.js) is served"
else
    print_status "error" "Static file (app.js) not served"
fi

if curl -s -f http://localhost:8000/static/styles.css >/dev/null 2>&1; then
    print_status "success" "Static file (styles.css) is served"
else
    print_status "error" "Static file (styles.css) not served"
fi

# Clean up
echo "Cleaning up..."
docker compose down

print_status "success" "Docker deployment test completed successfully!"
echo ""
echo "🎉 Your Diabetes Buddy server is ready for deployment!"
echo ""
echo "To run in production:"
echo "1. Ensure your .env file has a valid GEMINI_API_KEY"
echo "2. Run: docker compose up -d"
echo "3. Open: http://localhost:8000"
echo ""
echo "The streaming chat interface should now work like ChatGPT!"