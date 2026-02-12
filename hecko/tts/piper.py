"""Text-to-speech using Piper, with embedded sound file support.

Synthesizes text to audio and plays it through the speakers.
Supports embedded sound markers in text: [[filename.mp3]] will play that
sound file from the sounds/ directory. Example:
    "[[timer_done.mp3]]Your timer is done![[timer_done.mp3]]"

Usage (standalone test):
    micromamba run -n hecko python -m hecko.tts.piper
"""

import os
import re
import numpy as np
import sounddevice as sd
from piper import PiperVoice, SynthesisConfig

MODELS_DIR = "/Users/jstrout/Data/Hecko/models/piper"
SOUNDS_DIR = "/Users/jstrout/Data/Hecko/sounds"
DEFAULT_VOICE = "en_US-amy-medium"
DEFAULT_LENGTH_SCALE = 0.75  # < 1.0 = faster speech

_voice = None
_sound_cache = {}

# Words that TTS mispronounces: {pattern: replacement}
# Use re.IGNORECASE patterns. Add entries as needed.
_PRONUNCIATION_FIXES = {
    r"\bTucson\b": "Too-sahn",
}


def _fix_pronunciation(text):
    """Apply pronunciation fixes before synthesis."""
    for pattern, replacement in _PRONUNCIATION_FIXES.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text

# Regex to match [[filename.ext]] markers
_SOUND_RE = re.compile(r"\[\[([^\]]+\.\w+)\]\]")


def load_voice(voice_name=DEFAULT_VOICE):
    """Load a Piper voice. Caches on first call.

    Returns:
        A PiperVoice instance.
    """
    global _voice
    if _voice is None:
        model_path = f"{MODELS_DIR}/{voice_name}.onnx"
        config_path = f"{MODELS_DIR}/{voice_name}.onnx.json"
        _voice = PiperVoice.load(model_path, config_path)
    return _voice


def _load_sound(filename):
    """Load a sound file as (int16_array, sample_rate). Caches results."""
    if filename in _sound_cache:
        return _sound_cache[filename]

    path = os.path.join(SOUNDS_DIR, filename)
    if not os.path.exists(path):
        print(f"[tts] Warning: sound file not found: {path}", flush=True)
        return None

    import av
    container = av.open(path)
    stream = container.streams.audio[0]
    frames = []
    for frame in container.decode(stream):
        arr = frame.to_ndarray()
        # Convert to mono if stereo
        if arr.ndim > 1 and arr.shape[0] > 1:
            arr = arr.mean(axis=0)
        elif arr.ndim > 1:
            arr = arr[0]
        frames.append(arr)
    container.close()

    audio_f32 = np.concatenate(frames)
    sample_rate = stream.rate

    # Convert to int16
    audio_i16 = (audio_f32 * 32767).clip(-32768, 32767).astype(np.int16)
    _sound_cache[filename] = (audio_i16, sample_rate)
    return audio_i16, sample_rate


def synthesize(text, voice=None):
    """Synthesize text to a numpy int16 array.

    Args:
        text: String to speak (no sound markers).
        voice: PiperVoice instance, or None to use the cached default.

    Returns:
        (audio, sample_rate): numpy int16 array and its sample rate.
    """
    if voice is None:
        voice = load_voice()

    text = _fix_pronunciation(text)
    cfg = SynthesisConfig(length_scale=DEFAULT_LENGTH_SCALE)
    chunks = list(voice.synthesize(text, syn_config=cfg))
    audio = np.concatenate([c.audio_int16_array for c in chunks])
    sample_rate = chunks[0].sample_rate
    return audio, sample_rate


_output_rate = None


def _get_output_rate():
    """Get the default output device's sample rate (cached)."""
    global _output_rate
    if _output_rate is None:
        dev = sd.query_devices(kind="output")
        _output_rate = int(dev["default_samplerate"])
    return _output_rate


def _resample(audio, from_rate, to_rate):
    """Resample int16 audio using linear interpolation."""
    if from_rate == to_rate:
        return audio
    ratio = to_rate / from_rate
    n_out = int(len(audio) * ratio)
    x_old = np.linspace(0, 1, len(audio))
    x_new = np.linspace(0, 1, n_out)
    resampled = np.interp(x_new, x_old, audio.astype(np.float64))
    return resampled.astype(np.int16)


def _play_audio(audio, sample_rate):
    """Play an int16 audio array and block until done.

    Resamples to the output device's native rate if needed.
    """
    target_rate = _get_output_rate()
    if sample_rate != target_rate:
        audio = _resample(audio, sample_rate, target_rate)
        sample_rate = target_rate
    sd.play(audio, samplerate=sample_rate)
    sd.wait()


def play_sound(filename):
    """Play a sound file from the sounds/ directory. Blocks until done."""
    result = _load_sound(filename)
    if result:
        audio, sr = result
        _play_audio(audio, sr)


def speak(text, voice=None):
    """Synthesize text and play it through the speakers. Blocks until done.

    Supports embedded sound markers like [[timer_done.mp3]]. The text is split
    into segments, each of which is either a sound file or speech, played
    in order.

    Args:
        text: String to speak, optionally with {sound.mp3} markers.
        voice: PiperVoice instance, or None to use the cached default.
    """
    # Split text into segments: sound markers and speech
    parts = _SOUND_RE.split(text)
    # parts alternates: [text, filename, text, filename, text, ...]
    # Even indices are text, odd indices are filenames

    for i, part in enumerate(parts):
        if i % 2 == 1:
            # Sound file
            result = _load_sound(part)
            if result:
                audio, sr = result
                _play_audio(audio, sr)
        else:
            # Speech text
            stripped = part.strip()
            if stripped:
                audio, sr = synthesize(stripped, voice)
                _play_audio(audio, sr)


if __name__ == "__main__":
    import time

    print("Loading Piper voice...")
    t0 = time.time()
    voice = load_voice()
    print(f"Loaded in {time.time() - t0:.1f}s")

    test_phrases = [
        "Hello! I am Hecko, your homebrew assistant.",
        "[[timer_done.mp3]]Your 5 minute timer is done![[timer_done.mp3]]",
        "Timer set for 5 minutes.",
    ]

    for phrase in test_phrases:
        print(f'\nSaying: "{phrase}"')
        t0 = time.time()
        speak(phrase, voice)
        print(f"  ({time.time() - t0:.1f}s)")
