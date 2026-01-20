# Railway Deployment Guide

## Environment Variables

Set these in Railway dashboard:

### Required
- `OPENAI_API_KEY` - Your OpenAI API key
- `ANTHROPIC_API_KEY` - Your Anthropic API key (optional, if using Claude)
- `CEREBRAS_API_KEY` - Your Cerebras API key (optional, if using Cerebras)

### Optional
- `ELEVENLABS_API_KEY` - For text-to-speech features (optional)
- `PORT` - Railway sets this automatically, don't override
- `DATABASE_PATH` - Database file path (default: `data/liminal.db`)
- `LIMINAL_CONFIG_PATH` - Override config.yaml path (optional)

### Frontend (if deploying separately)
- `VITE_API_URL` - Backend API URL (e.g., `https://your-backend.railway.app`)

## Database

SQLite database will be created automatically at `data/liminal.db`. 
Railway provides persistent storage, so data will persist across deployments.

**Important for Data Persistence:**
- Railway's filesystem is persistent by default - your `data/` directory will survive redeployments
- The database path is configurable via `DATABASE_PATH` environment variable (default: `data/liminal.db`)
- All user profiles, sessions, and learning data are stored in this SQLite database
- **No additional configuration needed** - Railway automatically persists the filesystem

## Deployment Steps

1. **Connect Repository**: Link your GitHub repo to Railway
2. **Create Service**: Railway will auto-detect Python
3. **Set Environment Variables**: Add all required API keys
4. **Deploy**: Railway will build and deploy automatically

## Frontend Deployment

For frontend, you have two options:

### Option 1: Deploy separately (Recommended)
1. Create a new Railway service for frontend
2. Set build command: `cd frontend && npm install && npm run build`
3. Set start command: `cd frontend && npm run preview` (or use a static file server)
4. Set `VITE_API_URL` to your backend URL

### Option 2: Serve from backend
Add static file serving in `backend/main.py`:
```python
from fastapi.staticfiles import StaticFiles

app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")
```

## Notes

- Railway automatically sets `PORT` environment variable
- Database path uses `data/` directory which Railway persists
- CORS is set to allow all origins (update for production if needed)
- WebSocket connections work automatically with Railway's proxy
