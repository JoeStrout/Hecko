"""Microphone input stream for Hecko.

Provides a continuous 16 kHz mono audio stream from the preferred input device.

Usage (standalone test):
    micromamba run -n hecko python -m hecko.audio.mic
"""

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
BLOCK_SIZE = 1600  # 100ms chunks at 16 kHz

# Preferred input devices, in priority order (substring match on device name)
PREFERRED_DEVICES = [
    "eMeet Luna",
    "External Microphone",
    "MacBook Pro Microphone",
]


def list_input_devices():
    """Print available input devices."""
    devices = sd.query_devices()
    print("Available input devices:")
    for i, d in enumerate(devices):
        if d["max_input_channels"] > 0:
            print(f"  [{i}] {d['name']} (inputs: {d['max_input_channels']}, "
                  f"default SR: {d['default_samplerate']})")


def find_preferred_device():
    """Find the best available input device based on PREFERRED_DEVICES priority.

    Returns the device index, or None to use the system default.
    """
    devices = sd.query_devices()
    for preferred in PREFERRED_DEVICES:
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0 and preferred in d["name"]:
                return i
    return None


def open_mic_stream(callback, device=None, block_size=BLOCK_SIZE):
    """Open a mic input stream.

    Args:
        callback: Called with (audio_data, overflow) for each block.
                  audio_data is a numpy int16 array of shape (block_size,).
        device: Input device index, or None for default.
        block_size: Samples per block (default 1600 = 100ms at 16kHz).

    Returns:
        (stream, device): The sounddevice.InputStream (already started) and
        the device index used (int or None if system default).
    """
    def _sd_callback(indata, frames, time_info, status):
        if status:
            print(f"[mic] {status}")
        # indata is (frames, channels) float32 or int16 depending on dtype
        audio = indata[:, 0].copy()
        callback(audio, bool(status.input_overflow if status else False))

    if device is None:
        device = find_preferred_device()

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
        blocksize=block_size,
        device=device,
        callback=_sd_callback,
    )
    stream.start()
    return stream, device


if __name__ == "__main__":
    import time

    list_input_devices()

    dev = find_preferred_device()
    if dev is not None:
        print(f"\nSelected: [{dev}] {sd.query_devices(dev)['name']}")
    else:
        print("\nUsing system default input device")

    print(f"Recording 5 seconds at {SAMPLE_RATE} Hz...")

    chunks = []

    def on_audio(data, overflow):
        chunks.append(data)
        if overflow:
            print("[mic] overflow!")

    stream, _ = open_mic_stream(on_audio)
    try:
        time.sleep(5)
    finally:
        stream.stop()
        stream.close()

    audio = np.concatenate(chunks)
    duration = len(audio) / SAMPLE_RATE
    peak = np.max(np.abs(audio))
    rms = np.sqrt(np.mean(audio.astype(np.float64) ** 2))

    print(f"\nCaptured {duration:.2f}s ({len(audio)} samples)")
    print(f"Peak amplitude: {peak}")
    print(f"RMS amplitude:  {rms:.1f}")

    if peak < 100:
        print("\n⚠ Very low signal — check that the mic is enabled and not muted.")
    else:
        print("\nMic capture looks good!")
