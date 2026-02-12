# Hecko — Homebrew Echo

A homebrew voice assistant running on an Intel MacBook Pro (macOS 12.x, Darwin 22.6.0).

## Project Overview

Hecko is a local, always-listening voice assistant inspired by Amazon Echo. It uses a wake word to activate, transcribes speech locally, processes commands via custom Python logic, and responds with synthesized speech.

## Architecture

```
Mic (16 kHz mono, via sounddevice)
  → openWakeWord (wake word: "Alexa", ONNX inference)
  → Silero VAD (voice activity detection, direct ONNX — no torch)
  → faster-whisper (STT, `small` model, int8 quantization)
  → Command Router (score/handle pattern)
  → Piper TTS (en_US-amy-medium voice, resampled to 48 kHz for playback)
  → Speaker output (via sounddevice)
```

### Pipeline Flow
1. **Listening**: Mic audio streams continuously to openWakeWord.
2. **Wake**: When wake word is detected, hand off to VAD + recording.
3. **Recording**: Silero VAD detects speech start/end; audio is buffered.
4. **Transcription**: Buffered audio sent to faster-whisper for STT.
5. **Command Processing**: Transcribed text scored by all registered commands; highest score wins.
6. **Response**: Command handler returns text (may include `[[sound.mp3]]` markers); Piper synthesizes speech; audio plays.

## Tech Stack

| Component         | Technology                                              |
|-------------------|---------------------------------------------------------|
| Language          | Python 3.11                                             |
| Environment       | micromamba (`hecko` env)                                |
| Mic input         | sounddevice, 16 kHz mono int16                          |
| Mic selection     | Prefers "External Microphone", falls back to "MacBook Pro Microphone" |
| Wake word         | openWakeWord (`alexa_v0.1`, ONNX)                      |
| VAD               | Silero VAD (direct ONNX via onnxruntime, no torch)      |
| STT               | faster-whisper (`small`, int8, CPU)                     |
| Command handling  | Custom Python score/handle pattern                      |
| TTS               | Piper (`en_US-amy-medium`, length_scale=0.75)           |
| Audio output      | sounddevice (resampled to device native rate)            |
| Weather           | Open-Meteo API (free, no key)                           |

## Command System

Each command module in `hecko/commands/` provides:
- `score(text) -> float` (0.0–1.0): how confident this command matches the input
- `handle(text) -> str`: execute the command, return response text

The router dispatches to the highest-scoring command. Scores are logged for debugging.
Unrecognized input falls back to "I heard you say: ...".

### Current Commands

| Module        | Handles                                           |
|---------------|---------------------------------------------------|
| `greeting.py` | hello, hi, good morning, etc.                    |
| `quit_demo.py`| quit/exit demo (sets flag to exit main loop)     |
| `timer.py`    | set/query/cancel timers (multiple concurrent)     |
| `weather.py`  | current conditions, forecast, rain check (Tucson) |
| `time_cmd.py` | what time/day/date is it                          |
| `reminder.py` | set/query/cancel reminders with time parsing      |

## Project Structure

```
Hecko/
├── run                      # Launch script
├── sounds/
│   ├── timer_done.mp3       # Timer expiry chime
│   └── reminder.mp3         # Reminder chime
├── models/
│   └── piper/
│       ├── en_US-amy-medium.onnx
│       └── en_US-amy-medium.onnx.json
└── hecko/
    ├── __main__.py          # Entry point for `python -m hecko`
    ├── main.py              # Main loop: wake → record → transcribe → command → speak
    ├── audio/
    │   └── mic.py           # Mic input stream with device preference
    ├── wake/
    │   └── detector.py      # openWakeWord wrapper
    ├── vad/
    │   └── silero.py        # Silero VAD (direct ONNX, no torch)
    ├── stt/
    │   └── whisper.py       # faster-whisper wrapper
    ├── tts/
    │   └── piper.py         # Piper TTS + sound effect playback + resampling
    └── commands/
        ├── router.py        # Score-based command dispatch
        ├── greeting.py
        ├── quit_demo.py
        ├── timer.py
        ├── weather.py
        ├── time_cmd.py
        └── reminder.py
```

## Development Guidelines

- **Platform**: Intel Mac (x86_64), macOS Monterey. No ARM/Apple Silicon assumptions.
- **Environment**: micromamba at `/Users/jstrout/.local/bin/micromamba`. Env name: `hecko`.
- **Run**: `./run` or `micromamba run -n hecko python -m hecko`
- **Style**: Keep it simple and pragmatic. No over-engineering or premature abstraction.
- **Testing**: Each module is runnable standalone for debugging (e.g., `python -m hecko.stt.whisper`).
- **Audio format**: 16 kHz, mono, 16-bit PCM is the internal format. TTS resampled to output device rate.
- **Error handling**: Graceful degradation — log errors, keep the main loop running.
- **No LLM**: Command interpretation is custom Python parsing. Keep routing explicit and deterministic.
- **No torch**: Silero VAD uses direct ONNX inference. Torch was removed to avoid OpenMP conflicts with ctranslate2.
- **Sound effects**: Use `[[filename.mp3]]` markers in response text. Files live in `sounds/`.
- **Pronunciation**: Add entries to `_PRONUNCIATION_FIXES` in `tts/piper.py` for mispronounced words.
- **STT quirks**: Whisper outputs varied time formats (e.g., "845 p.m.", "8.50", "8 50 p.m."). Time parsers must handle these.

## Key Decisions Made

- Wake word: `alexa_v0.1` (placeholder until custom "Hey Hecko" model is trained)
- Weather: Open-Meteo API, hardcoded to Tucson (85718)
- Audio library: sounddevice
- TTS speed: length_scale=0.75 (faster than default)
- Sound marker syntax: `[[filename.mp3]]` (avoids f-string conflicts)

## Next Up

- **Wake word bypass**: After certain responses (e.g., greeting's "How can I help you?"), skip the wake word and listen directly for a follow-up command. Design the mechanism for commands to signal this.
- **Grocery list**: Our Groceries API integration
- **Custom wake word**: Train an openWakeWord model for "Hey Hecko"
