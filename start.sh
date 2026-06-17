#!/bin/bash
# Start Cord AI

# Check for API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "Error: ANTHROPIC_API_KEY is not set."
  echo "Run: export ANTHROPIC_API_KEY=your_key_here"
  exit 1
fi

echo "Starting Cord AI..."

# Start backend
cd "$(dirname "$0")/backend"
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "Backend running (PID $BACKEND_PID) at http://localhost:8000"

# Start frontend
cd "$(dirname "$0")/frontend"
npm run dev -- --port 3000 &
FRONTEND_PID=$!
echo "Frontend running (PID $FRONTEND_PID) at http://localhost:3000"

echo ""
echo "Cord AI is ready at http://localhost:3000"
echo "Press Ctrl+C to stop both servers."

# Wait and cleanup
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Stopped.'" EXIT
wait
