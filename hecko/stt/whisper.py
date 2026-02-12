"""Speech-to-text using faster-whisper.

Transcribes int16 audio (16 kHz mono) to text using a CTranslate2-optimized
Whisper model.

Usage (standalone test — transcribes from mic via VAD):
    micromamba run -n hecko python -m hecko.stt.whisper
"""

import os
import numpy as np

# Workaround for OpenMP duplicate library conflict (torch + ctranslate2 on macOS)
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from faster_whisper import WhisperModel

DEFAULT_MODEL_SIZE = "small"
DEFAULT_COMPUTE_TYPE = "int8"

_model = None


def load_model(model_size=DEFAULT_MODEL_SIZE, compute_type=DEFAULT_COMPUTE_TYPE):
    """Load the Whisper model. Caches on first call.

    Returns:
        A faster_whisper.WhisperModel instance.
    """
    global _model
    if _model is None:
        _model = WhisperModel(model_size, device="cpu", compute_type=compute_type)
    return _model


def transcribe(audio, model=None):
    """Transcribe int16 audio to text.

    Args:
        audio: numpy int16 array (16 kHz mono).
        model: WhisperModel instance, or None to use the cached default.

    Returns:
        str: The transcribed text (stripped), or empty string if nothing detected.
    """
    if model is None:
        model = load_model()

    # faster-whisper expects float32 normalized to [-1, 1]
    audio_f32 = audio.astype(np.float32) / 32768.0

    segments, _ = model.transcribe(
        audio_f32,
        language="en",
        vad_filter=True,  # filter out non-speech segments
    )
    text = " ".join(s.text for s in segments).strip()
    return text


if __name__ == "__main__":
    import time
    from hecko.audio.mic import open_mic_stream, SAMPLE_RATE
    from hecko.vad.silero import load_vad_model, SpeechRecorder

    print("Loading models...")
    vad_model = load_vad_model()
    whisper_model = load_model()
    print("Models loaded.\n")

    print("Speak a phrase, then pause. Will transcribe after you stop.")
    print("Ctrl+C to quit.\n")

    recorder = SpeechRecorder(vad_model)

    def on_audio(data, overflow):
        recorder.process(data)

    stream, _ = open_mic_stream(on_audio)
    try:
        while not recorder.done:
            time.sleep(0.05)
    finally:
        stream.stop()
        stream.close()

    audio = recorder.get_result()
    if audio is not None:
        duration = len(audio) / SAMPLE_RATE
        print(f"Recorded {duration:.2f}s, transcribing...")
        t0 = time.time()
        text = transcribe(audio, whisper_model)
        elapsed = time.time() - t0
        print(f"  [{elapsed:.1f}s] \"{text}\"")
    else:
        print("No audio captured.")
