# Peter — Hardware Setup Guide

This file is for **Peter** (ESP32 hardware side).  
Follow it after pulling Jean-Paul’s branch so the robot + digital twin work together.

---

## 1) Pull the project

```bash
git clone https://github.com/PeterAoun1/esp32-AI-voice-assitant.git
cd esp32-AI-voice-assitant
git checkout last-jp
git pull origin last-jp
```

If you already have the repo:

```bash
cd esp32-AI-voice-assitant
git fetch origin
git checkout last-jp
git pull origin last-jp
```

---

## 2) What changed (short)

Same robot workflow as before:

1. ESP32 records the child’s voice  
2. Sends audio to the PC server (`POST /process_voice`)  
3. Downloads the reply (`GET /reply.wav`)  
4. Plays it on the speaker  

Extra features on this branch:

- Friendly welcome at boot (`POST /welcome`) then normal conversation loop  
- Story / count-to-20 / alphabet if the child wants  
- Parent digital twin at `http://PC_IP:8888/`  
- Safety alerts (bad words / sensitive topics) marked in red with `!`  
- Click a red chat to open the full conversation  
- AI stack: **Groq** (speech + chat) + **ElevenLabs** (voice) — not Azure  

---

## 3) PC server setup (do this first)

### 3.1 Create `.env`

Copy the example file:

```bash
copy .env.example .env
```

Edit `.env` and put real keys:

```env
GROQ_API_KEY=your_groq_key_here
ELEVENLABS_API_KEY=your_elevenlabs_key_here
ELEVENLABS_VOICE_ID=pNInz6obpgDQGcFmaJgB
ELEVENLABS_MODEL_ID=eleven_turbo_v2_5
HOST=0.0.0.0
PORT=8888
```

Ask Jean-Paul for the keys if you don’t have them.

### 3.2 Install Python packages

From the project root:

```bash
pip install -r requirements.txt
```

### 3.3 Start the server

From the project root (important):

```bash
python -m backend.app
```

You should see something like:

```text
Uvicorn running on http://0.0.0.0:8888
```

### 3.4 Open the digital twin

On the same PC:

- http://localhost:8888/

From phone / another device on the same Wi‑Fi:

- http://YOUR_PC_IP:8888/

---

## 4) Find your PC IP (ESP32 needs this)

On Windows PowerShell:

```powershell
ipconfig
```

Use the IPv4 of your Wi‑Fi adapter, for example:

```text
192.168.1.23
```

ESP32 and PC must be on the **same Wi‑Fi**.

---

## 5) Flash the ESP32 (`src/main.ino`)

Open `src/main.ino` and set:

```cpp
const char* ssid = "YOUR_WIFI_NAME";
const char* password = "YOUR_WIFI_PASSWORD";

const char* welcomeUrl = "http://192.168.1.23:8888/welcome";
const char* serverUrl = "http://192.168.1.23:8888/process_voice";
const char* downloadUrl = "http://192.168.1.23:8888/reply.wav";
```

Replace `192.168.1.23` with **your real PC IP**.

Pins are unchanged from before:

| Signal | GPIO |
|--------|------|
| I2S WS | 27 |
| I2S SCK | 26 |
| I2S SD | 33 |
| DAC playback | GPIO 25 |

Record time is still **5 seconds** (`RECORD_TIME`).

Flash with Arduino IDE / PlatformIO as usual.

---

## 6) Runtime flow (what you should hear / see)

1. ESP32 connects to Wi‑Fi  
2. Calls `/welcome` → robot says a normal hi (“How are you today?”)  
3. ESP32 listens (~5 seconds)  
4. Child talks  
5. Server: Groq STT → Groq reply → ElevenLabs voice  
6. ESP32 plays reply  
7. Loop continues (listen → reply → listen…)  

If the child doesn’t choose an activity, the AI may gently offer:

- story  
- count (to 20)  
- alphabet  

Parent twin updates live every 5 seconds.

---

## 7) Parent twin — what to check

- **Chat log**: all conversations saved in SQLite (`data/parent_logs.db`)  
- **Red chat + `!`**: sensitive / bad-word alert  
- **Click the red chat**: full conversation for that session  
- AI does **not** re-read chat history (saves API credits)

---

## 8) Quick test without overthinking

1. Start server: `python -m backend.app`  
2. Open http://localhost:8888/  
3. Power the ESP32  
4. Hear welcome greeting  
5. Speak during listening window  
6. Hear reply  
7. Refresh twin → see the chat appear  

---

## 9) Common problems

| Problem | Fix |
|--------|-----|
| ESP32 can’t reach server | Same Wi‑Fi? Correct PC IP in `main.ino`? Windows Firewall allowing port 8888? |
| `/welcome` or `/process_voice` fails | Is `python -m backend.app` running from project root? |
| Empty / wrong voice | Check `GROQ_API_KEY` and `ELEVENLABS_API_KEY` in `.env` |
| Twin empty | Normal until at least one exchange; refresh http://localhost:8888/ |
| Import errors | Run `pip install -r requirements.txt` again |

---

## 10) Useful endpoints

| Method | URL | Used by |
|--------|-----|---------|
| POST | `/welcome` | ESP32 boot greeting |
| POST | `/process_voice` | ESP32 voice turn |
| GET | `/reply.wav` | ESP32 downloads speech |
| GET | `/` | Parent digital twin |
| GET | `/conversation/{id}` | Full convo for a flagged chat |
| GET | `/alerts` | JSON safety alerts |

---

## 11) Project map (don’t get lost)

```text
backend/           <- run this server
  app.py           <- routes + twin page
  ai_services.py   <- Groq + ElevenLabs
  features.py      <- story/count/alphabet + safety
  database.py      <- SQLite for parents
  config.py        <- reads .env
src/main.ino       <- flash this to ESP32
src/server.py      <- optional launcher only
.env               <- your secrets (do not commit)
peter_readme.md    <- this file
```

---

## 12) Do not commit

- `.env` (API keys)  
- `data/parent_logs.db` (local chat logs)  

---

If something breaks, check:

1. Server terminal logs  
2. ESP32 Serial Monitor at 115200  
3. Twin page at http://PC_IP:8888/  

That’s enough to pull and run with the hardware.
