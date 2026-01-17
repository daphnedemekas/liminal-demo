# Liminal Discovery System - Web Interface

A minimal web/mobile interface for the Liminal curiosity discovery system with text and audio support.

## Features

- **Discovery Phase**: Natural conversation to identify what you're curious about
- **Learning Phase**: Personalized lesson targeting your specific confusion
- **Text/Audio Switching**: Toggle between typing and speaking at any time
- **Minimal UI**: Clean, distraction-free interface
- **Mobile-Friendly**: Works on phone browsers

## Setup

### Prerequisites

- Python 3.9+
- Node.js 18+
- API Keys:
  - `ANTHROPIC_API_KEY` (Claude API)
  - `ELEVENLABS_API_KEY` (Text-to-speech)

### 1. Environment Variables

Create a `.env` file in the project root:

```bash
ANTHROPIC_API_KEY=your_anthropic_key_here
ELEVENLABS_API_KEY=your_elevenlabs_key_here
```

### 2. Backend Setup

```bash
# Install backend dependencies
cd backend
pip install -r requirements.txt

# Start backend server
python main.py
```

The backend will run on `http://localhost:8000`

### 3. Frontend Setup

In a new terminal:

```bash
# Install frontend dependencies
cd frontend
npm install

# Start frontend development server
npm run dev
```

The frontend will run on `http://localhost:5173`

## Usage

1. Open `http://localhost:5173` in your browser
2. You'll see an opening question from the discovery phase
3. **Text mode**: Type your response and click "Send"
4. **Audio mode**: Click the 🎤 icon, then click "Hold to Speak" and talk
5. After 5-8 exchanges, the system identifies your topic
6. Click "Start Learning" to begin the personalized lesson
7. The learning phase will:
   - Assess what you understand
   - Identify your specific confusion
   - Explain it clearly

## Architecture

```
┌─────────────────────────────────────────┐
│           React Frontend                │
│  (Text/Audio UI + WebSocket Client)    │
└──────────────┬──────────────────────────┘
               │ WebSocket
               ↓
┌─────────────────────────────────────────┐
│          FastAPI Backend                │
│  (Session Manager + Audio Service)      │
└──────────────┬──────────────────────────┘
               │
      ┌────────┴────────┐
      ↓                 ↓
┌─────────────┐   ┌──────────────┐
│   Claude    │   │  ElevenLabs  │
│   Sonnet    │   │     TTS      │
└─────────────┘   └──────────────┘
```

## Audio Support

### Text-to-Speech (ElevenLabs)
- All assistant responses are converted to speech
- Audio auto-plays in audio mode
- Uses Eleven Turbo V2 model for speed

### Speech-to-Text (Browser Web Speech API)
- Browser-native, no API cost
- Works in Chrome, Safari, Edge
- Click "Hold to Speak" to record

## API Endpoints

### REST
- `POST /api/discovery/start` - Create new session
- `POST /api/learning/start` - Start learning phase

### WebSocket
- `WS /ws/discovery/{session_id}` - Discovery conversation
- `WS /ws/learning/{session_id}` - Learning conversation

## Development

### Backend Structure
```
backend/
├── main.py                    # FastAPI app
├── api/                       # (not used - WebSocket in main)
├── services/
│   ├── session_manager.py     # Session state management
│   ├── audio_service.py       # ElevenLabs integration
│   └── learning_engine.py     # Learning phase logic
└── models/
    └── api_models.py          # Pydantic models
```

### Frontend Structure
```
frontend/
├── src/
│   ├── components/
│   │   ├── App.tsx             # Main app with phase management
│   │   ├── DiscoveryChat.tsx   # Discovery phase UI
│   │   ├── LearningChat.tsx    # Learning phase UI
│   │   ├── TransitionScreen.tsx # Topic reveal screen
│   │   ├── MessageBubble.tsx   # Chat bubble component
│   │   └── AudioToggle.tsx     # Mode switcher
│   ├── hooks/
│   │   ├── useWebSocket.ts     # WebSocket connection
│   │   ├── useAudio.ts         # Audio playback/recording
│   │   └── useSpeechRecognition.ts # Browser speech-to-text
│   ├── services/
│   │   └── api.ts              # API client
│   └── styles/
│       └── minimal.css         # Minimal styling
└── package.json
```

## Troubleshooting

### Backend won't start
- Check that `ANTHROPIC_API_KEY` and `ELEVENLABS_API_KEY` are set
- Ensure port 8000 is not already in use
- Install dependencies: `pip install -r backend/requirements.txt`

### Frontend won't connect
- Make sure backend is running on port 8000
- Check browser console for errors
- Try refreshing the page

### Audio not working
- **TTS**: Check that `ELEVENLABS_API_KEY` is valid
- **STT**: Use Chrome/Safari/Edge (Firefox may not support Web Speech API)
- **Permissions**: Allow microphone access when prompted

### WebSocket connection fails
- Check that Vite proxy is configured correctly (vite.config.ts)
- Ensure backend WebSocket endpoint is running
- Check browser console for connection errors

## Production Deployment

### Option 1: Single Container
```bash
# Build frontend
cd frontend
npm run build

# Serve static files from FastAPI
# (Add static file mounting in main.py)

# Deploy to fly.io, render.com, etc.
```

### Option 2: Separate Services
- **Frontend**: Deploy to Vercel/Netlify
- **Backend**: Deploy to Railway/Render
- Update API URLs in frontend

## License

MIT
