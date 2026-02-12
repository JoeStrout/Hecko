"""Hecko — Homebrew Echo main loop.

Listens for the wake word, records a command, transcribes it, and responds.

Usage:
    micromamba run -n hecko python -m hecko.main
"""

import time
from hecko.audio.mic import open_mic_stream
from hecko.wake.detector import WakeWordDetector
from hecko.vad.silero import load_vad_model, SpeechRecorder
from hecko.stt.whisper import load_model as load_whisper, transcribe
from hecko.tts.piper import speak, play_sound
from hecko.commands import router
from hecko.commands import greeting, quit_demo, timer, weather, time_cmd, reminder, grocery, music, math_cmd

# How long to wait for speech after wake word before playing the prompt
_PRE_SPEECH_TIMEOUT = 0.5  # seconds
# How long to keep listening after the prompt sound
_PROMPTED_LISTEN_SECONDS = 6


def log(msg):
    print(msg, flush=True)


def main():
    log("Loading wake word model...")
    t0 = time.time()
    wake = WakeWordDetector()
    log(f"  wake word ready ({time.time() - t0:.1f}s)")

    log("Loading VAD model...")
    t1 = time.time()
    vad_model = load_vad_model()
    log(f"  VAD ready ({time.time() - t1:.1f}s)")

    log("Loading whisper model...")
    t1 = time.time()
    whisper = load_whisper()
    log(f"  whisper ready ({time.time() - t1:.1f}s)")

    log("Loading TTS voice...")
    t1 = time.time()
    from hecko.tts.piper import load_voice
    load_voice()
    log(f"  TTS ready ({time.time() - t1:.1f}s)")

    # Register commands
    router.register(greeting)
    router.register(quit_demo)
    router.register(timer)
    router.register(weather)
    router.register(time_cmd)
    router.register(reminder)
    router.register(grocery)
    router.register(music)
    router.register(math_cmd)

    # Wire up timer/reminder announcements to TTS
    def announce(text):
        log(f"  [announce] {text}")
        speak(text)

    timer.set_announce_callback(announce)
    reminder.set_announce_callback(announce)

    log(f"All models loaded in {time.time() - t0:.1f}s")
    log(f"Wake word: {wake.model_name}")
    log("Listening... say 'Alexa' to begin.\n")

    # Shared state between the main loop and the mic callback
    state = {"mode": "wake"}  # "wake" or "recording"
    recorder = None
    last_wake = 0
    record_start = 0
    prompted = False  # True after we played listening.mp3
    needs_duck = False  # set by audio callback, handled by main loop

    def on_audio(data, overflow):
        nonlocal recorder, last_wake, needs_duck

        if state["mode"] == "wake":
            score = wake.process(data)
            if score is not None:
                now = time.time()
                if now - last_wake > 2:
                    last_wake = now
                    log("  Wake word detected! Listening for command...")
                    needs_duck = True
                    wake.reset()
                    recorder = SpeechRecorder(vad_model)
                    state["mode"] = "recording"
                    # Process this chunk as speech too
                    recorder.process(data)

        elif state["mode"] == "recording":
            recorder.process(data)

    stream, dev_idx = open_mic_stream(on_audio)

    try:
        while True:
            if state["mode"] == "recording" and recorder:
                # Duck Spotify volume on first poll after wake word
                if needs_duck:
                    needs_duck = False
                    music.duck_volume()

                # Check for pre-speech silence: wake word fired but no speech yet
                if not prompted and not recorder.speech_started:
                    elapsed = time.time() - last_wake
                    if elapsed >= _PRE_SPEECH_TIMEOUT:
                        log("  No speech yet, playing prompt...")
                        prompted = True
                        # Create fresh recorder BEFORE playing sound, so audio
                        # captured during playback goes to the new recorder
                        recorder = SpeechRecorder(
                            vad_model, max_seconds=_PROMPTED_LISTEN_SECONDS)
                        record_start = time.time()
                        play_sound("listening.mp3")

                if recorder.done:
                    audio = recorder.get_result()
                    state["mode"] = "wake"
                    recorder = None
                    was_prompted = prompted
                    prompted = False

                    if audio is not None and len(audio) > 1600:  # at least 100ms
                        play_sound("processing.mp3")
                        log("  Transcribing...")
                        t0 = time.time()
                        text = transcribe(audio, whisper)
                        elapsed = time.time() - t0
                        log(f"  [{elapsed:.1f}s] \"{text}\"")

                        if text:
                            response, scores = router.dispatch(text)
                            if scores:
                                score_str = ", ".join(
                                    f"{name}={s:.2f}" for name, s in scores)
                                log(f"  Scores: {score_str}")
                            log(f"  Response: \"{response}\"")
                            speak(response)

                            if quit_demo.quit_requested:
                                log("\nQuit requested. Goodbye!")
                                break
                        else:
                            log("  (no speech detected)")
                    else:
                        if was_prompted:
                            log("  (no command after prompt)")
                        else:
                            log("  (too short, ignoring)")

                    # Restore Spotify volume
                    music.restore_volume()

                    log("\nListening...\n")

            time.sleep(0.05)

    except KeyboardInterrupt:
        log("\nShutting down.")
    finally:
        stream.stop()
        stream.close()


if __name__ == "__main__":
    main()
