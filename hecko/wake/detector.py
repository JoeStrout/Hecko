"""Wake word detector using openWakeWord.

Listens to the mic stream and fires a callback when the wake word is detected.

openWakeWord expects 1280-sample (80ms) chunks of 16 kHz int16 audio.

Usage (standalone test):
    micromamba run -n hecko python -m hecko.wake.detector
"""

import numpy as np
from openwakeword.model import Model

# openWakeWord requires exactly 1280 samples per prediction call
OWW_CHUNK_SIZE = 1280

# Default detection threshold (0.0–1.0). Tunable per environment.
DEFAULT_THRESHOLD = 0.5

# Default wake word model
DEFAULT_MODEL = "alexa_v0.1"


class WakeWordDetector:
    """Wraps openWakeWord for streaming wake word detection."""

    def __init__(self, model_name=DEFAULT_MODEL, threshold=DEFAULT_THRESHOLD):
        self.model_name = model_name
        self.threshold = threshold
        self.model = Model(
            wakeword_models=[model_name],
            inference_framework="onnx",
        )
        self._buffer = np.array([], dtype=np.int16)

    def reset(self):
        """Clear internal audio buffer and model state."""
        self._buffer = np.array([], dtype=np.int16)
        self.model.reset()

    def process(self, audio_chunk):
        """Feed audio and check for wake word.

        Args:
            audio_chunk: numpy int16 array of any length (16 kHz mono).

        Returns:
            float or None: The detection score if it exceeds threshold,
            otherwise None.
        """
        self._buffer = np.concatenate([self._buffer, audio_chunk])

        score = None
        while len(self._buffer) >= OWW_CHUNK_SIZE:
            frame = self._buffer[:OWW_CHUNK_SIZE]
            self._buffer = self._buffer[OWW_CHUNK_SIZE:]
            prediction = self.model.predict(frame)
            s = prediction[self.model_name]
            if s >= self.threshold:
                score = s

        return score


if __name__ == "__main__":
    import time
    from hecko.audio.mic import open_mic_stream, SAMPLE_RATE

    print(f"Listening for wake word '{DEFAULT_MODEL}' "
          f"(threshold={DEFAULT_THRESHOLD})...")
    print("Say 'Alexa' to trigger. Ctrl+C to quit.\n")

    detector = WakeWordDetector()
    last_trigger = 0

    def on_audio(data, overflow):
        global last_trigger
        score = detector.process(data)
        if score is not None:
            now = time.time()
            if now - last_trigger > 2:  # debounce: ignore repeats within 2s
                print(f"  >>> WAKE WORD DETECTED (score={score:.3f})")
                last_trigger = now
                detector.reset()

    stream, dev_idx = open_mic_stream(on_audio)
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        stream.stop()
        stream.close()
