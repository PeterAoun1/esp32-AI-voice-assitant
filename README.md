# ESP32 AI Voice Assistant (Kids Companion Robot)

Cloud voice robot for kids + parent digital twin monitoring.

**AI stack:** Groq (Whisper STT + Llama chat) + ElevenLabs (TTS)

## Project structure

```
backend/          # Python server
  app.py          # FastAPI routes + digital twin page
  ai_services.py  # Groq STT/LLM + ElevenLabs TTS
  features.py     # Alphabet / count-to-20 modes + safety alerts
  database.py     # SQLite logs for parents (not for the AI)
  config.py       # Settings from .env
src/
  main.ino        # ESP32 firmware
  server.py       # Optional launcher -> backend.app
data/             # Created at runtime (parent_logs.db)
temp_audio/       # Temporary wav files
```

## Features

- Robot **starts** the chat: offers a fairy tale, counting, or alphabet
- Voice chat via Groq + ElevenLabs
- Learning modes: **alphabet** and **count to 20** + **story**
- Bad-word + sensitive-topic detection (shown on twin)
- Parent digital twin at `http://SERVER_IP:8888/`
- SQLite chat history for parents only (AI does **not** re-read chats)

## Setup

1. Copy `.env.example` to `.env` and add your keys:

```bash
copy .env.example .env
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run from the project root:

```bash
python -m backend.app
```

4. Open the parent twin: `http://localhost:8888/`

5. Flash `src/main.ino` (set WiFi + server IP). On boot the ESP32 calls `/welcome` first.

## Voice flow

1. Robot greets normally: "Hi! ... How are you today?"
2. Child talks freely (Groq AI replies)
3. If the child does not choose an activity, robot gently offers story / count / alphabet
4. If they pick one, that activity starts
