import wave
import struct
import requests
from flask import Flask, request, send_file
from groq import Groq

# --- CONFIGURATION ---
GROQ_API_KEY = ""  
ELEVENLABS_API_KEY = "" 

# Rachel Default Voice ID

VOICE_ID = "pNInz6obpgDQGcFmaJgB" 

# Initialize Groq client
groq_client = Groq(api_key=GROQ_API_KEY)
app = Flask(__name__)

@app.route('/process_voice', methods=['POST'])
def process_voice():
    print("\n1. Receiving raw audio from ESP32...")
    raw_audio = request.data
    
    # Save input from ESP32 into WAV format
    input_filename = "user_input.wav"
    with wave.open(input_filename, "wb") as wav_file:
        wav_file.setnchannels(1)      # Mono
        wav_file.setsampwidth(2)      # 16-bit
        wav_file.setframerate(16000)  # 16kHz
        wav_file.writeframes(raw_audio)

    print("2. Transcribing audio via Groq Whisper API...")
    try:
        with open(input_filename, "rb") as file:
            transcription = groq_client.audio.transcriptions.create(
                file=(input_filename, file.read()),
                model="whisper-large-v3-turbo",
                response_format="text"
            )
        user_text = transcription.strip()
        print(f"3. User said: {user_text}")
    except Exception as e:
        print(f"Groq Transcription Error: {e}")
        return "Transcription Error", 500

    print("4. Generating conversational reply via Groq Llama 3...")
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful voice assistant communicating with a child i want u to be calm and talk in a helpful warm way don t make the asnwers too long."
                },
                {
                    "role": "user",
                    "content": user_text
                }
            ],
            model="llama-3.3-70b-versatile",
        )
        reply_text = chat_completion.choices[0].message.content
        print(f"5. Groq Assistant says: {reply_text}")
    except Exception as e:
        print(f"Groq Chat Error: {e}")
        return "Chat Generation Error", 500

    print("6. Fetching realistic voice from ElevenLabs API...")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}?output_format=pcm_16000"
    headers = {
        "Accept": "audio/pcm",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }
    data = {
        "text": reply_text,
        "model_id": "eleven_turbo_v2_5"
    }
    
    eleven_response = requests.post(url, json=data, headers=headers)
    if eleven_response.status_code != 200:
        print(f"ElevenLabs Error ({eleven_response.status_code}): {eleven_response.text}")
        return "ElevenLabs Error", 500

    pcm_16bit_data = eleven_response.content

    print("7. Converting 16-bit PCM -> 8-bit DAC WAV...")
    num_samples = len(pcm_16bit_data) // 2
    samples_16 = struct.unpack(f'<{num_samples}h', pcm_16bit_data)
    
    # Scale down 16-bit signed (-32768 to 32767) to 8-bit unsigned (0 to 255)
    samples_8 = bytes([((s + 32768) >> 8) for s in samples_16])

    # Save as 8-bit unsigned WAV file for ESP32 DAC
    with wave.open("reply.wav", "wb") as wav_file:
        wav_file.setnchannels(1)      # Mono
        wav_file.setsampwidth(1)      # 8-bit unsigned
        wav_file.setframerate(16000)  # 16kHz
        wav_file.writeframes(samples_8)

    print("Done! Audio ready for download.")
    return "OK", 200

@app.route('/reply.wav', methods=['GET'])
def get_reply():
    return send_file("reply.wav", mimetype="audio/wav")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8888)
