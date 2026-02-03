#!/bin/bash
# Start both backend and frontend

echo "Starting Envisage..."

cd "$(dirname "$0")"

# Init DB (creates tables if missing)
mkdir -p data
python3 -c "
from backend.database import Base, get_session_factory
engine = get_session_factory().kw.get('bind') or get_session_factory()().get_bind()
Base.metadata.create_all(engine)
print('Database initialized.')
"

# Start backend
python3 -m uvicorn backend.main:app --reload --port 8000 &
BACKEND_PID=$!

# Start frontend
cd frontend
npm run dev &
FRONTEND_PID=$!

echo ""
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop both"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
