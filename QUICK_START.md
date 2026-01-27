# Quick Start Guide

## Current Status

✅ **Backend is already running** on port 8000
- You can access it at: http://localhost:8000
- The API is responding correctly

## Starting the Services

### Option 1: Use the Launch Script (Easiest)

```bash
./launch.sh
```

This will:
- Check if backend is running (it already is!)
- Start the frontend if not running
- Show you the URLs to access

### Option 2: Manual Start

#### Backend (already running, but if you need to restart):

```bash
# Stop existing backend (if needed)
lsof -ti:8000 | xargs kill

# Start backend
python3 backend/main.py
```

The backend will run on: **http://localhost:8000**

#### Frontend:

```bash
cd frontend

# Install dependencies (first time only)
npm install

# Start development server
npm run dev
```

The frontend will run on: **http://localhost:5173** (or next available port)

## Access the Application

Once both are running:
1. Open your browser to: **http://localhost:5173**
2. The frontend will connect to the backend automatically

## Troubleshooting

### Port Already in Use

If you get "port already in use" errors:

```bash
# Check what's using port 8000
lsof -ti:8000

# Kill the process (replace PID with actual process ID)
kill <PID>

# Or kill all processes on that port
lsof -ti:8000 | xargs kill
```

### Backend Won't Start

1. **Check dependencies:**
   ```bash
   pip3 install -r requirements.txt
   pip3 install -r backend/requirements.txt
   ```

2. **Check API keys:**
   - The backend will work without API keys for basic functionality
   - For full functionality, you may need:
     - `OPENAI_API_KEY` (for OpenAI models)
     - `ANTHROPIC_API_KEY` (for Claude models)
     - `CEREBRAS_API_KEY` (for Cerebras models)
     - `ELEVENLABS_API_KEY` (for audio features)

3. **Check database:**
   - The database will be created automatically at `data/liminal.db`
   - Make sure the `data/` directory exists and is writable

### Frontend Won't Start

1. **Install dependencies:**
   ```bash
   cd frontend
   npm install
   ```

2. **Check Node version:**
   ```bash
   node --version  # Should be 18+
   ```

3. **Clear cache and reinstall:**
   ```bash
   cd frontend
   rm -rf node_modules package-lock.json
   npm install
   ```

### Frontend Can't Connect to Backend

1. **Verify backend is running:**
   ```bash
   curl http://localhost:8000/
   ```

2. **Check frontend config:**
   - The frontend is configured to connect to `http://localhost:8000`
   - This is set in `frontend/src/config.ts`
   - Vite proxy is configured in `frontend/vite.config.ts`

3. **Check browser console:**
   - Open browser DevTools (F12)
   - Look for connection errors in the Console tab

## Current Running Services

To see what's currently running:

```bash
# Check backend
lsof -ti:8000 && echo "Backend is running on port 8000" || echo "Backend is not running"

# Check frontend  
lsof -ti:5173 && echo "Frontend is running on port 5173" || echo "Frontend is not running"
```

## Stop All Services

```bash
# Stop backend
lsof -ti:8000 | xargs kill

# Stop frontend
lsof -ti:5173 | xargs kill

# Or stop both at once
lsof -ti:8000,5173 | xargs kill
```



