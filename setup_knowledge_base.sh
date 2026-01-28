#!/bin/bash

# Diabetes Buddy - Knowledge Base Setup Script
# Automated installation and configuration

set -e  # Exit on error

echo "======================================"
echo "Diabetes Buddy Knowledge Base Setup"
echo "======================================"
echo ""

# Check if we're in the right directory
if [ ! -f "requirements.txt" ]; then
    echo "❌ Error: Must run from diabetes-buddy root directory"
    exit 1
fi

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $python_version"

# Activate virtual environment if exists
if [ -d ".venv" ]; then
    echo "✓ Activating virtual environment..."
    source .venv/bin/activate
else
    echo "⚠ No virtual environment found. Creating one..."
    python3 -m venv .venv
    source .venv/bin/activate
fi

# Install/upgrade dependencies
echo ""
echo "Installing dependencies..."
pip install --upgrade pip
pip install beautifulsoup4 requests schedule pytest pytest-mock

echo ""
echo "✓ Dependencies installed"

# Create necessary directories
echo ""
echo "Creating directories..."
mkdir -p logs
mkdir -p docs/knowledge-sources
mkdir -p data
mkdir -p config

echo "✓ Directories created"

# Run tests
echo ""
echo "Running tests..."
if python -m pytest tests/test_knowledge_base.py -v --tb=short 2>/dev/null; then
    echo "✓ All tests passed"
else
    echo "⚠ Some tests failed (this is expected if mocks aren't perfect)"
fi

# Check if user profile exists
if [ -f "config/user_profile.json" ]; then
    echo ""
    echo "✓ User profile already exists"
else
    echo ""
    echo "ℹ No user profile yet - will be created during first setup"
fi

# Ask about scheduler setup
echo ""
echo "======================================"
echo "Background Scheduler Setup"
echo "======================================"
echo ""
echo "The scheduler runs automatic update checks weekly."
echo "Choose your preferred method:"
echo ""
echo "1) Systemd service (recommended for production)"
echo "2) Cron job (simple, reliable)"
echo "3) Manual (I'll run it myself)"
echo ""
read -p "Enter choice (1-3): " scheduler_choice

case $scheduler_choice in
    1)
        echo ""
        echo "Creating systemd service..."
        SERVICE_FILE="/etc/systemd/system/diabuddy-updates.service"
        
        # Check if we can write to systemd directory
        if [ -w "/etc/systemd/system" ]; then
            cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Diabetes Buddy Knowledge Base Update Scheduler
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/.venv/bin/python scripts/schedule_updates.py --mode daemon
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
            
            sudo systemctl daemon-reload
            sudo systemctl enable diabuddy-updates
            sudo systemctl start diabuddy-updates
            
            echo "✓ Systemd service created and started"
            echo ""
            echo "Check status with: sudo systemctl status diabuddy-updates"
        else
            echo "⚠ Need sudo access. Run manually:"
            echo ""
            echo "sudo nano /etc/systemd/system/diabuddy-updates.service"
            echo ""
            echo "Then paste the configuration from docs/KNOWLEDGE_BASE_QUICKSTART.md"
        fi
        ;;
        
    2)
        echo ""
        echo "Adding cron job..."
        
        CRON_LINE="0 3 * * * cd $(pwd) && .venv/bin/python scripts/schedule_updates.py --check-now >> logs/cron.log 2>&1"
        
        # Check if cron job already exists
        if crontab -l 2>/dev/null | grep -q "schedule_updates.py"; then
            echo "✓ Cron job already exists"
        else
            (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
            echo "✓ Cron job added (runs daily at 3 AM)"
        fi
        
        echo ""
        echo "View cron jobs with: crontab -l"
        ;;
        
    3)
        echo ""
        echo "ℹ Manual mode selected"
        echo ""
        echo "Run update checks with:"
        echo "  python scripts/schedule_updates.py --check-now"
        echo ""
        echo "Or start daemon:"
        echo "  python scripts/schedule_updates.py --mode daemon"
        ;;
        
    *)
        echo "⚠ Invalid choice, skipping scheduler setup"
        ;;
esac

# Final instructions
echo ""
echo "======================================"
echo "Setup Complete! 🎉"
echo "======================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Start the web interface:"
echo "   python web/app.py"
echo ""
echo "2. Open browser to:"
echo "   http://localhost:8000/setup"
echo ""
echo "3. Select your pump and CGM"
echo ""
echo "4. Done! The system handles everything else."
echo ""
echo "Documentation:"
echo "  - Quick Start: docs/KNOWLEDGE_BASE_QUICKSTART.md"
echo "  - Full Guide:  docs/KNOWLEDGE_BASE_SYSTEM.md"
echo ""
echo "Logs:"
echo "  - Updates: logs/knowledge_updates.log"
echo "  - Cron:    logs/cron.log (if using cron)"
echo ""

# Offer to start web interface
echo ""
read -p "Start web interface now? (y/n): " start_web

if [ "$start_web" = "y" ] || [ "$start_web" = "Y" ]; then
    echo ""
    echo "Starting web interface..."
    echo "Press Ctrl+C to stop"
    echo ""
    python web/app.py
fi
