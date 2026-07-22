"""
AI helpers using Groq + ElevenLabs (no Azure).

- Speech-to-Text: Groq Whisper
- Chat / safety LLM: Groq Llama
- Text-to-Speech: ElevenLabs -> 8-bit WAV for ESP32 DAC
"""

import logging
import struct
import wave
from pathlib import Path

import requests
from groq import Groq

from backend import config
from backend.features import system_prompt_for_mode

log = logging.getLogger("VoiceAssistant")

groq_client = Groq(api_key=config.GROQ_API_KEY)


def speech_to_text(file_path: Path) -> str:
    """Convert a WAV file into text using Groq Whisper."""
    try:
        log.info("Speech-to-Text via Groq Whisper...")
        with open(file_path, "rb") as file:
            transcription = groq_client.audio.transcriptions.create(
                file=(file_path.name, file.read()),
                model=config.GROQ_STT_MODEL,
                response_format="text",
            )
        # SDK may return a plain string or an object with .text
        if isinstance(transcription, str):
            text = transcription.strip()
        else:
            text = str(getattr(transcription, "text", transcription)).strip()
        return text or "Can you tell me a short story?"
    except Exception as e:
        log.error(f"STT error: {e}")
        return "Can you tell me a short story?"


def ask_llm(prompt: str, mode: str) -> str:
    """
    Ask Groq Llama for a short kids-friendly reply.
    NOTE: we only send THIS message (no chat history) to save credits/tokens.
    """
    try:
        log.info(f"Groq chat ({config.GROQ_CHAT_MODEL}) mode={mode}")
        response = groq_client.chat.completions.create(
            model=config.GROQ_CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt_for_mode(mode)},
                {"role": "user", "content": prompt},
            ],
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log.error(f"LLM error: {e}")
        if mode == "alphabet":
            return "Let's start with A, B, C. A for apple, B for ball, C for cat. Can you say A, B, C with me?"
        if mode == "count":
            return "Let's count together! One, two, three, four, five. What comes after five?"
        if mode == "story":
            return (
                "Once upon a time, a little star wanted to become a fairy. "
                "Do you want to hear what happens next?"
            )
        return (
            "Once upon a time, a kind dragon shared cookies with its friends. The end! "
            "Want to count to 20 or learn the alphabet next?"
        )


def text_to_speech_8bit(text: str, output_path: Path) -> None:
    """
    ElevenLabs returns 16-bit PCM at 16 kHz.
    We convert it to 8-bit unsigned WAV for the ESP32 DAC.
    """
    url = (
        f"https://api.elevenlabs.io/v1/text-to-speech/"
        f"{config.ELEVENLABS_VOICE_ID}?output_format=pcm_16000"
    )
    headers = {
        "Accept": "audio/pcm",
        "Content-Type": "application/json",
        "xi-api-key": config.ELEVENLABS_API_KEY,
    }
    payload = {
        "text": text,
        "model_id": config.ELEVENLABS_MODEL_ID,
    }

    log.info("Requesting TTS from ElevenLabs...")
    response = requests.post(url, json=payload, headers=headers, timeout=60)
    if response.status_code != 200:
        raise RuntimeError(f"ElevenLabs error ({response.status_code}): {response.text}")

    pcm_16bit = response.content
    num_samples = len(pcm_16bit) // 2
    samples_16 = struct.unpack(f"<{num_samples}h", pcm_16bit)
    samples_8 = bytes([((s + 32768) >> 8) for s in samples_16])

    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(1)
        wav_file.setframerate(16000)
        wav_file.writeframes(samples_8)

    log.info(f"Saved reply audio: {output_path}")
