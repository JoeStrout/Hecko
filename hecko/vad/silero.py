"""Voice Activity Detection using Silero VAD (direct ONNX, no torch).

After wake word detection, this module records audio until the user stops
speaking. It buffers incoming audio into 512-sample frames (required by
Silero at 16 kHz) and tracks speech start/end based on probability thresholds.

Usage (standalone test):
    micromamba run -n hecko python -m hecko.vad.silero
"""

import numpy as np
import onnxruntime as ort

# Silero requires exactly 512 samples per call at 16 kHz
SILERO_CHUNK_SIZE = 512

# Path to the ONNX model (bundled with openwakeword)
MODEL_PATH = None  # resolved lazily

# How long to wait for silence before ending recording
DEFAULT_SILENCE_MS = 800

# Maximum recording length (seconds) to prevent runaway recordings
MAX_RECORD_SECONDS = 15

_session = None


def _find_model():
    """Find the silero_vad.onnx model file."""
    import openwakeword
    import os
    pkg_dir = os.path.dirname(openwakeword.__file__)
    path = os.path.join(pkg_dir, "resources", "models", "silero_vad.onnx")
    if os.path.exists(path):
        return path
    raise FileNotFoundError(f"silero_vad.onnx not found at {path}")


def load_vad_model():
    """Load the Silero VAD ONNX session. Caches on first call.

    Returns:
        An onnxruntime.InferenceSession.
    """
    global _session
    if _session is None:
        path = _find_model()
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        _session = ort.InferenceSession(path, sess_options=opts)
    return _session


class SileroVAD:
    """Low-level stateful wrapper around the Silero ONNX model."""

    def __init__(self, session, sample_rate=16000):
        self.session = session
        self.sr = np.array(sample_rate, dtype=np.int64)
        self.h = np.zeros((2, 1, 64), dtype=np.float32)
        self.c = np.zeros((2, 1, 64), dtype=np.float32)

    def reset(self):
        self.h = np.zeros((2, 1, 64), dtype=np.float32)
        self.c = np.zeros((2, 1, 64), dtype=np.float32)

    def __call__(self, audio_frame):
        """Run VAD on a single 512-sample float32 frame.

        Returns:
            float: Speech probability (0.0–1.0).
        """
        x = audio_frame.reshape(1, -1).astype(np.float32)
        output, self.h, self.c = self.session.run(
            None, {"input": x, "sr": self.sr, "h": self.h, "c": self.c}
        )
        return float(output[0][0])


class SpeechRecorder:
    """Records speech after wake word, using Silero VAD to detect end-of-speech.

    Feed audio chunks via process(). When speech ends (or max duration is hit),
    get_result() returns the recorded audio.
    """

    def __init__(self, session, threshold=0.5, silence_ms=DEFAULT_SILENCE_MS,
                 max_seconds=MAX_RECORD_SECONDS, sample_rate=16000):
        self.sample_rate = sample_rate
        self.max_samples = int(max_seconds * sample_rate)
        self.threshold = threshold
        # Number of consecutive non-speech frames needed to end recording
        frame_ms = (SILERO_CHUNK_SIZE / sample_rate) * 1000  # 32ms
        self._silence_frames_needed = int(silence_ms / frame_ms)
        self._vad = SileroVAD(session, sample_rate)
        self._buffer = np.array([], dtype=np.int16)
        self._recorded = []
        self._total_samples = 0
        self._done = False
        self._speech_started = False
        self._silence_frames = 0

    def reset(self):
        """Reset for a new recording."""
        self._buffer = np.array([], dtype=np.int16)
        self._recorded = []
        self._total_samples = 0
        self._done = False
        self._speech_started = False
        self._silence_frames = 0
        self._vad.reset()

    @property
    def done(self):
        return self._done

    @property
    def speech_started(self):
        return self._speech_started

    def process(self, audio_chunk):
        """Feed audio data. Call repeatedly with mic chunks.

        Args:
            audio_chunk: numpy int16 array (16 kHz mono).
        """
        if self._done:
            return

        self._recorded.append(audio_chunk)
        self._total_samples += len(audio_chunk)

        # Check max duration
        if self._total_samples >= self.max_samples:
            self._done = True
            return

        # Buffer and process in 512-sample frames
        self._buffer = np.concatenate([self._buffer, audio_chunk])
        while len(self._buffer) >= SILERO_CHUNK_SIZE and not self._done:
            frame = self._buffer[:SILERO_CHUNK_SIZE]
            self._buffer = self._buffer[SILERO_CHUNK_SIZE:]

            prob = self._vad(frame.astype(np.float32) / 32768.0)

            if prob >= self.threshold:
                self._speech_started = True
                self._silence_frames = 0
            elif self._speech_started:
                self._silence_frames += 1
                if self._silence_frames >= self._silence_frames_needed:
                    self._done = True

    def get_result(self):
        """Return the recorded audio as a single numpy int16 array, or None."""
        if not self._recorded:
            return None
        return np.concatenate(self._recorded)


if __name__ == "__main__":
    import time
    from hecko.audio.mic import open_mic_stream, SAMPLE_RATE

    print("Loading Silero VAD model (ONNX)...")
    session = load_vad_model()

    print("Speak now! Recording will stop when you pause.")
    print(f"(Max {MAX_RECORD_SECONDS}s, silence threshold {DEFAULT_SILENCE_MS}ms)\n")

    recorder = SpeechRecorder(session)

    def on_audio(data, overflow):
        recorder.process(data)

    stream, dev_idx = open_mic_stream(on_audio)
    try:
        while not recorder.done:
            time.sleep(0.05)
    finally:
        stream.stop()
        stream.close()

    audio = recorder.get_result()
    if audio is not None:
        duration = len(audio) / SAMPLE_RATE
        peak = np.max(np.abs(audio))
        print(f"\nRecorded {duration:.2f}s ({len(audio)} samples), peak={peak}")
        if peak < 100:
            print("Warning: very low signal.")
        else:
            print("Recording captured OK.")
    else:
        print("No audio recorded.")
