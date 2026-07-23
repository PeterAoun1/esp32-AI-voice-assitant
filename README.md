# ESP32 AI Voice Assistant

An AI-powered voice assistant built with an ESP32 that enables natural voice interactions using Microsoft Azure AI services. The system records speech, processes it in the cloud, generates an AI response, converts it back to speech, and plays it through a speaker. :contentReference[oaicite:0]{index=0}

## Features

- Voice recording using an INMP441 I2S microphone
- Speech-to-Text with Azure Speech Services
- AI-generated responses using Azure OpenAI
- Text-to-Speech audio playback
- Wi-Fi communication between the ESP32 and a FastAPI server
- Sensitive-topic detection for parental monitoring
- Modular architecture designed for future expansion

## Hardware

- ESP32
- INMP441 I2S Microphone
- OLED Display
- PAM8403 Audio Amplifier
- 8Ω Speaker
- Power Bank

## Software Stack

- Arduino (C++)
- Python
- FastAPI
- Microsoft Azure Speech Services
- Azure OpenAI
- REST API

## System Architecture

```text
Child
   │
   ▼
ESP32 + INMP441
   │
   ▼
FastAPI Server
   │
   ├── Azure Speech-to-Text
   ├── Azure OpenAI
   └── Azure Text-to-Speech
   │
   ▼
ESP32
   │
   ▼
Speaker
```

## How It Works

1. The user speaks into the microphone.
2. The ESP32 records and uploads the audio to the FastAPI server.
3. Azure Speech Services converts the audio into text.
4. Azure OpenAI generates a context-aware response.
5. Azure Speech Services converts the response back into audio.
6. The ESP32 downloads the generated audio and plays it through the speaker. :contentReference[oaicite:1]{index=1}

## Repository Structure

```text
.
├── diagrams/      # System architecture and diagrams
├── docs/          # Project documentation
├── src/           # ESP32 firmware and FastAPI server
└── README.md
```

## Future Improvements

- Animated OLED facial expressions
- Continuous conversation mode
- Push-to-talk activation
- Conversation history database
- Educational learning modules
- Enhanced parental dashboard

## Contributors

- Peter Aoun
- Rudy Karim
- Jean-Paul Achkouti :contentReference[oaicite:2]{index=2}

## License

This project was developed for educational purposes as part of an engineering project at the École Supérieure d'Ingénieurs de Beyrouth (ESIB).
