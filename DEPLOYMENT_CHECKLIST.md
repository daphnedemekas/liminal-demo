# Railway Deployment Checklist ✅

## Pre-Deployment Verification

### ✅ Code Changes Made
- [x] Port configuration uses `PORT` env var (Railway provides this)
- [x] Database path uses `DATABASE_PATH` env var
- [x] All orchestrators pass database path correctly
- [x] Frontend API URLs use `VITE_API_URL` env var
- [x] WebSocket URLs automatically convert http/https to ws/wss
- [x] CORS configured (currently allows all origins)

### ✅ Files Created
- [x] `railway.json` - Railway configuration
- [x] `Procfile` - Process file for Railway
- [x] `RAILWAY_DEPLOY.md` - Deployment documentation

### ✅ Dependencies
- [x] `requirements.txt` (root) - Core dependencies
- [x] `backend/requirements.txt` - Backend-specific dependencies
- [x] `frontend/package.json` - Frontend dependencies
- [x] All missing packages installed (react-markdown, recharts)

## Railway Environment Variables to Set

### Required
```
OPENAI_API_KEY=your_key_here
```

### Optional (but recommended)
```
ANTHROPIC_API_KEY=your_key_here
CEREBRAS_API_KEY=your_key_here
ELEVENLABS_API_KEY=your_key_here
DATABASE_PATH=data/liminal.db
```

### Frontend (if deploying separately)
```
VITE_API_URL=https://your-backend.railway.app
```

## Deployment Steps

1. **Push to GitHub** (if not already)
   ```bash
   git add .
   git commit -m "Prepare for Railway deployment"
   git push
   ```

2. **Connect to Railway**
   - Go to Railway dashboard
   - New Project → Deploy from GitHub
   - Select your repository

3. **Configure Service**
   - Railway will auto-detect Python
   - Set environment variables (see above)
   - Deploy!

4. **Get Your URL**
   - Railway will provide a URL like `https://your-app.railway.app`
   - Use this for `VITE_API_URL` if deploying frontend separately

## Potential Issues & Solutions

### Issue: Database not persisting
**Solution**: Railway provides persistent storage. The `data/` directory will persist.

### Issue: WebSocket connections failing
**Solution**: Railway's proxy handles WebSocket upgrades automatically. Ensure you're using `wss://` for HTTPS.

### Issue: Frontend can't connect to backend
**Solution**: Set `VITE_API_URL` to your Railway backend URL (with https://)

### Issue: Port already in use
**Solution**: Railway sets `PORT` automatically. Don't override it.

### Issue: Missing dependencies
**Solution**: Ensure both `requirements.txt` and `backend/requirements.txt` are in the repo.

## Testing After Deployment

1. Check backend health: `https://your-backend.railway.app/`
2. Test WebSocket connection
3. Test database operations (create user, start session)
4. Verify frontend can connect (if deployed separately)

## Notes

- SQLite works fine on Railway (persistent storage)
- CORS is currently open (`allow_origins=["*"]`) - consider restricting for production
- Audio features require `ELEVENLABS_API_KEY` but are optional
- The app will work without audio features if key is not set
