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
- `DATABASE_PATH` - SQLite database file path (default: `data/liminal.db`)
  - **Important**: Add a persistent volume mounted at `/data` in Railway Settings → Volumes
  - This ensures your database persists across deployments
- `LIMINAL_CONFIG_PATH` - Override config.yaml path (optional)

### Frontend (if deploying separately)
- `VITE_API_URL` - Backend API URL (e.g., `https://your-backend.railway.app`)

## Database

SQLite database is used for all deployments. The database will be created automatically at the path specified by `DATABASE_PATH` (default: `data/liminal.db`).

**Important for Data Persistence on Railway:**

1. **Add a Persistent Volume**:
   - Go to your Railway service → Settings tab
   - Scroll to "Volumes" section
   - Click "Add Volume"
   - Mount path: `/data`
   - Click Add

2. **Set DATABASE_PATH**:
   - In your service Variables, set: `DATABASE_PATH=/data/liminal.db`
   - This ensures the database is stored in the persistent volume

3. **Tables Created Automatically**: The app will create all tables on first run using SQLAlchemy

**Why a Persistent Volume?**
- Railway's default filesystem is ephemeral - files can be lost on redeploy
- Mounting a volume at `/data` ensures your database persists across deployments
- All user profiles, sessions, and learning data are stored in this SQLite database

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
