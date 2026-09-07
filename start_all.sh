#!/bin/bash
# Startup script for all services
# Starts engine service, operation system, evaluation service, collectors, and queue worker

echo "Starting Disaster Management System..."

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Start evaluation service (local)
cd "$SCRIPT_DIR/evaluation_service"
# Load API keys from .env (gitignored). Create it from .env.example.
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
else
    echo "WARNING: .env not found. Copy .env.example to .env and fill in your API keys."
fi
source "$SCRIPT_DIR/.venv/bin/activate"
python app.py &
EVAL_PID=$!
echo "Evaluation service started: PID $EVAL_PID"

# Wait a moment for services to initialize
sleep 3

echo ""
echo "Evaluation service started successfully!"
echo "Evaluation service: PID $EVAL_PID"
echo ""
echo "To stop service, run: kill $EVAL_PID"
