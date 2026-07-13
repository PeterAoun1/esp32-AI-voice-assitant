import os
import wave
import logging
import asyncio
import uuid
import struct
import traceback
import azure.cognitiveservices.speech as speechsdk
from openai import AzureOpenAI
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
'''
  don t forget to add the api keys
'''
TEMP_DIR = "temp_audio"
os.makedirs(TEMP_DIR, exist_ok=True)
REPLY_FILE_PATH = os.path.join(TEMP_DIR, "reply.wav")

app = FastAPI()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("VoiceAssistant")


def _speech_to_text_sync(file_path: str) -> str:
    """
    Uses your Azure Speech SDK configuration to parse incoming ESP32 recorded audio.
    """
    try:
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SERVICE_REGION)
        audio_config = speechsdk.audio.AudioConfig(filename=file_path)
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
        
        log.info("Processing Speech-To-Text via Azure Cloud...")
        result = recognizer.recognize_once_async().get()
        
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            return result.text
        elif result.reason == speechsdk.ResultReason.NoMatch:
            return "Hi, tell me the full story of Rapunzel."  # Fallback gracefully if silence recorded
        elif result.reason == speechsdk.ResultReason.Canceled:
            log.warning(f"STT Canceled: {result.cancellation_details.reason}. Details: {result.cancellation_details.error_details}")
            return "Hi, tell me the full story of Rapunzel."
    except Exception as e:
        log.error(f"STT Error: {e}")
        return "Hi, tell me the full story of Rapunzel."

def _ask_llm_sync(prompt: str) -> str:
    """
    Sends the user prompt directly to your Azure OpenAI gpt-4o-mini deployment resource.
    """
    try:
        log.info(f"Contacting Azure OpenAI ({AZURE_OPENAI_MODEL})...")
        response = ai_client.chat.completions.create(
            model=AZURE_OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a ai voice assitant for kids tal in a calm reassuring way. Keep answers brief so they fit on a small device buffer."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log.error(f"LLM Processing Error: {e}")
        # Secure static backup option if Azure deployment quota or endpoint limits are saturated
        return "Once upon a time, a girl named Rapunzel with long golden hair was locked in a tall tower by an old witch. She let down her hair to let the witch climb. A prince found her, they escaped, and lived happily ever after."

def _generate_8bit_tts_sync(text: str, output_path: str):
    """
    Downloads structural 16-bit master linear PCM datasets from your Azure Speech subscription,
    then transforms the payload layout arrays directly into Unsigned 8-bit matrices.
    """
    temp_azure_wav = os.path.join(TEMP_DIR, f"azure_{uuid.uuid4().hex}.wav")
    try:
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SERVICE_REGION)
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm
        )
        
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
        log.info("Requesting 16-bit source WAV block from Azure Cloud (France Central)...")
        result = synthesizer.speak_text_async(text).get()
        
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            with open(temp_azure_wav, "wb") as f:
                f.write(result.audio_data)
            
            with wave.open(temp_azure_wav, 'rb') as src_wav:
                n_frames = src_wav.getnframes()
                raw_frames = src_wav.readframes(n_frames)
            
            # Translate 16-bit signed to 8-bit unsigned
            unsigned_8bit_bytes = bytearray()
            for i in range(0, len(raw_frames), 2):
                signed_16bit_sample = struct.unpack('<h', raw_frames[i:i+2])[0]
                unsigned_8bit_sample = int(((signed_16bit_sample + 32768) >> 8) & 0xFF)
                unsigned_8bit_bytes.append(unsigned_8bit_sample)
            
            with wave.open(output_path, "wb") as dst_wav:
                dst_wav.setnchannels(1)      
                dst_wav.setsampwidth(1)      
                dst_wav.setframerate(16000)  
                dst_wav.writeframes(unsigned_8bit_bytes)
                
            log.info(f"Successfully processed audio stream matrix. Exported asset: {output_path}")
            
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = result.cancellation_details
            raise Exception(f"Azure Studio rejected generation sequence: {cancellation_details.reason} - {cancellation_details.error_details}")

    except Exception as e:
        log.error(f"Pipeline failure inside TTS conversion engine: {str(e)}")
        raise e
    finally:
        if os.path.exists(temp_azure_wav):
            try:
                os.remove(temp_azure_wav)
            except:
                pass

@app.post("/process_voice")
async def process_voice(request: Request):
    try:
        audio_bytes = await request.body()
        if not audio_bytes or len(audio_bytes) < 100:
            return Response(content="FAIL: Raw input payload missing or corrupted.", status_code=400)

        unique_id = str(uuid.uuid4())
        filename = os.path.join(TEMP_DIR, f"input_{unique_id}.wav")

        with wave.open(filename, "wb") as wav_file:
            wav_file.setnchannels(1)      
            wav_file.setsampwidth(2)      
            wav_file.setframerate(16000)  
            wav_file.writeframes(audio_bytes)

        log.info(f"Saved recording locally: {filename} ({len(audio_bytes)} bytes)")

        # Full execution sequence
        user_text = await asyncio.to_thread(_speech_to_text_sync, filename)
        log.info(f"[STT RESULT] User said: {user_text}")

        ai_response = await asyncio.to_thread(_ask_llm_sync, user_text)
        log.info(f"[LLM RESULT] AI response: {ai_response}")

        await asyncio.to_thread(_generate_8bit_tts_sync, ai_response, REPLY_FILE_PATH)
        return Response(content="SUCCESS", media_type="text/plain")

    except Exception as main_ex:
        detailed_error = f"Pipeline Error: {str(main_ex)}\n{traceback.format_exc()}"
        log.error(detailed_error)
        return Response(content=detailed_error, status_code=500, media_type="text/plain")

@app.get("/reply.wav")
async def get_reply_audio():
    if os.path.exists(REPLY_FILE_PATH):
        return FileResponse(REPLY_FILE_PATH, media_type="audio/wav")
    return Response(content="Error: File asset not present.", status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888)
