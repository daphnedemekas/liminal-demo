#!/bin/bash

# Launch script for Liminal Demo Backend and Frontend
# This script helps you start both services easily

set -e

echo "🚀 Liminal Demo Launch Script"
echo "=============================="
echo ""

# Check if backend is already running
if lsof -ti:8000 > /dev/null 2>&1; then
    echo "✅ Backend is already running on port 8000"
    echo "   To restart, kill the existing process first:"
    echo "   lsof -ti:8000 | xargs kill"
    echo ""
else
    echo "📦 Starting backend server..."
    cd "$(dirname "$0")"
    python3 backend/main.py &
    BACKEND_PID=$!
    echo "   Backend started (PID: $BACKEND_PID)"
    echo "   Backend will be available at http://localhost:8000"
    echo ""
    sleep 2
fi

# Check if frontend is already running
if lsof -ti:5173 > /dev/null 2>&1; then
    echo "✅ Frontend is already running on port 5173"
    echo "   To restart, kill the existing process first:"
    echo "   lsof -ti:5173 | xargs kill"
    echo ""
else
    echo "📦 Starting frontend development server..."
    cd "$(dirname "$0")/frontend"
    
    # Check if node_modules exists
    if [ ! -d "node_modules" ]; then
        echo "   Installing frontend dependencies..."
        npm install
    fi
    
    npm run dev &
    FRONTEND_PID=$!
    echo "   Frontend started (PID: $FRONTEND_PID)"
    echo "   Frontend will be available at http://localhost:5173"
    echo ""
fi

echo "✨ Services are running!"
echo ""
echo "📱 Open your browser to:"
echo "   http://localhost:5173"
echo ""
echo "To stop all services, press Ctrl+C or run:"
echo "   lsof -ti:8000,5173 | xargs kill"
echo ""

# Wait for user interrupt
wait



