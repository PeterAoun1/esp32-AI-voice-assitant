"""
Load settings from environment variables / .env file.
Stack: Groq (speech + LLM) + ElevenLabs (voice).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root = folder that contains backend/
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# Folders used by the server
TEMP_DIR = ROOT_DIR / "temp_audio"
DATA_DIR = ROOT_DIR / "data"
TEMP_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

REPLY_WAV = TEMP_DIR / "reply.wav"
DATABASE_PATH = DATA_DIR / "parent_logs.db"

# Groq (Whisper STT + Llama chat)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
GROQ_CHAT_MODEL = os.getenv("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile")

# ElevenLabs (TTS for the ESP32 speaker)
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")  # Rachel
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5")

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8888"))
