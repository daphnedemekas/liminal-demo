# Frontend Setup Guide

## Quick Start

### 1. Start the Backend Server

```bash
# From project root
cd /Users/daphnedemekas/Desktop/liminal-demo
python backend/main.py
```

The backend will start on `http://localhost:8000`

### 2. Start the Frontend Development Server

```bash
# In a new terminal, from project root
cd frontend
npm install  # First time only
npm run dev
```

The frontend will start on `http://localhost:5173` (or another port if 5173 is in use)

### 3. Open in Browser

Visit `http://localhost:5173` in your browser.

You should see the Model Selector screen where you can choose your AI models before starting a conversation.

## Model Selection

The UI allows you to select different models for two roles:

### Interviewer (Asks Questions)
- **Cerebras Llama 3.3 70B** - Fast, natural conversation (default, recommended)
- **Cerebras Llama 3.1 8B** - Very fast, lower cost
- **Claude Sonnet 4** - High quality, slower
- **Claude Haiku 3.5** - Good balance
- **GPT-4o** - OpenAI latest
- **GPT-4o Mini** - OpenAI fast

### Ranker (Analyzes Conversation)
- **Cerebras Llama 3.3 70B** - Fast analysis (default)
- **Claude Sonnet 4** - Best quality (recommended for complex analysis)
- **Claude Haiku 3.5** - Good balance
- **GPT-4o** - OpenAI latest
- **Cerebras Llama 3.1 8B** - Very fast

## Recommended Configurations

### Fastest (Low Cost)
- Interviewer: Cerebras Llama 3.1 8B
- Ranker: Cerebras Llama 3.1 8B

### Balanced (Default)
- Interviewer: Cerebras Llama 3.3 70B
- Ranker: Cerebras Llama 3.3 70B

### Best Quality
- Interviewer: Claude Sonnet 4
- Ranker: Claude Sonnet 4

### Hybrid (Speed + Quality)
- Interviewer: Cerebras Llama 3.3 70B (fast responses)
- Ranker: Claude Sonnet 4 (better analysis)

## API Keys Required

Make sure you have the necessary API keys in your `.env` file:

```bash
# Required for default configuration
CEREBRAS_API_KEY=csk-...

# Optional (only if using these models)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

## Features

- **Model Selection UI**: Choose different models before starting
- **Real-time Chat**: WebSocket-based conversation
- **Audio Mode**: Toggle voice input/output (if configured)
- **Responsive Design**: Works on desktop and mobile

## Troubleshooting

### Backend won't start
- Check that you're in the project root directory
- Ensure all Python dependencies are installed: `pip install -r requirements.txt`
- Check that port 8000 is not already in use

### Frontend won't start
- Make sure you ran `npm install` in the `frontend` directory
- Check that the backend is running on port 8000
- Try deleting `node_modules` and running `npm install` again

### CORS Errors
- The backend is configured to allow all origins for development
- If you still see CORS errors, check that the backend is running

### Model Selection Not Working
- Check backend logs for errors
- Verify API keys are set correctly in `.env`
- Check browser console for any JavaScript errors

### WebSocket Connection Failed
- Ensure backend is running on `http://localhost:8000`
- Check that no firewall is blocking WebSocket connections
- Try refreshing the page

## Development

### Hot Reload
Both the frontend and backend support hot reload:
- Frontend: Vite will automatically reload when you edit `.tsx` or `.css` files
- Backend: You may need to restart manually after changes to Python files

### Building for Production

```bash
cd frontend
npm run build
```

Built files will be in `frontend/dist`

## Architecture

```
Frontend (React + TypeScript)
    ↓ HTTP POST /api/discovery/start (with model_config)
Backend (FastAPI)
    ↓ Creates session with selected models
DiscoveryOrchestrator
    ↓ Uses specified models
LLMClient → Interviewer/Ranker Agents
```

The model configuration is passed from the UI all the way down to the LLM calls!
