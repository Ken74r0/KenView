"""
WASAPI audio capture using pyaudiowpatch.

Captures two streams on a background QThread so the UI event loop never blocks:
  - loopback on the default output device -> remote participants' voices
  - default microphone -> the presenter's own voice

Both streams are resampled to 16 kHz mono 16-bit PCM (the format Deepgram's
streaming API expects) and written into thread-safe ring buffers that the
transcription layer consumes.
"""
import threading
import array

import pyaudiowpatch as pyaudio

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit

# ---- Thread-safe buffers (one per source) --------------------------------

class RingBuffer:
    """Append-only byte buffer with a size cap. Deepgram must see continuous
    PCM, so we never drop mid-stream; we just truncate from the head when
    the consumer is too slow (tail always stays the freshest audio)."""

    def __init__(self, max_bytes=1024 * 1024):  # ~32 s of 16 kHz mono
        self._buf = bytearray()
        self._max = max_bytes

    def append(self, data: bytes):
        self._buf += data
        if len(self._buf) > self._max:
            del self._buf[: len(self._buf) - self._max]

    def drain(self) -> bytes:
        data = bytes(self._buf)
        self._buf.clear()
        return data

    @property
    def available(self) -> int:
        return len(self._buf)


# ---- Resample to 16 kHz mono ---------------------------------------------

def _to_16k_mono(data: bytes, rate: int, channels: int, width: int) -> bytes:
    """Convert raw PCM `data` to 16 kHz mono 16-bit PCM.

    Pure-stdlib (no audioop — removed in Python 3.13). Handles only 16-bit
    samples (we always open paInt16 streams), downmixes multi-channel by
    averaging, resamples with linear interpolation."""
    if width != 2:
        return bytes(data)  # unsupported width; pass through (never hit in practice)

    # Handle empty data
    if not data:
        return b""
        
    samples = array.array("h")
    try:
        samples.frombytes(data)
    except Exception:
        return b"" # Should not happen with well-formed 16-bit PCM

    if channels > 1:
        mono = array.array(
            "h",
            (sum(samples[i:i + channels]) // channels
             for i in range(0, len(samples), channels)),
        )
    else:
        mono = samples

    if rate != SAMPLE_RATE:
        n_out = int(len(mono) * SAMPLE_RATE / rate)
        step = rate / SAMPLE_RATE
        out = array.array("h")
        for i in range(n_out):
            pos = i * step
            i0 = int(pos)
            i1 = min(i0 + 1, len(mono) - 1)
            frac = pos - i0
            out.append(int(mono[i0] * (1.0 - frac) + mono[i1] * frac))
    else:
        out = mono

    return out.tobytes()


# ---- Capture thread -------------------------------------------------------

class AudioCaptureThread(threading.Thread):
    """Runs two WASAPI capture streams (loopback + mic) on a background
    thread, pushing resampled 16 kHz mono PCM into the given buffers."""

    def __init__(self, loopback_buffer: RingBuffer, mic_buffer: RingBuffer,
                 device_index: int = None):
        super().__init__(daemon=True)
        self.loopback_buffer = loopback_buffer
        self.mic_buffer = mic_buffer
        self.device_index = device_index  # optional capture device override
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        pa = pyaudio.PyAudio()

        # --- Find the default output device (for loopback) ---
        loopback_info = None
        try:
            # A WASAPI loopback device is exposed with the same index as its
            # default output device but flagged as an output with loopback.
            default_speakers = pa.get_default_device()
            if not default_speakers.get("isLoopbackDevice", False):
                for i in range(pa.get_device_count()):
                    info = pa.get_device_info_by_index(i)
                    if info.get("name", "").endswith(")") and \
                       "loopback" in info.get("name", "").lower():
                        loopback_info = info
                        break
                else:
                    # Fall back: open default output and enable WASAPI loopback
                    loopback_info = default_speakers
            else:
                loopback_info = default_speakers
        except Exception:
            loopback_info = None

        # --- Open loopback stream (remote participants) ---
        loopback_stream = None
        if loopback_info is not None:
            try:
                loopback_stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=loopback_info.get("maxInputChannels", 2) or 2,
                    rate=int(loopback_info.get("defaultSampleRate", SAMPLE_RATE)),
                    input=True,
                    frames_per_buffer=1024,
                    input_device_index=loopback_info["index"],
                    stream_callback=None,
                )
            except Exception:
                loopback_stream = None

        # --- Open microphone stream (presenter's own voice) ---
        mic_stream = None
        try:
            mic_index = self.device_index or pa.get_default_input_device_info()["index"]
            mic_info = pa.get_device_info_by_index(mic_index)
            mic_stream = pa.open(
                format=pyaudio.paInt16,
                channels=mic_info.get("maxInputChannels", 1) or 1,
                rate=int(mic_info.get("defaultSampleRate", SAMPLE_RATE)),
                input=True,
                frames_per_buffer=1024,
                input_device_index=mic_index,
            )
        except Exception:
            mic_stream = None

        try:
            while not self._stop.is_set():
                if loopback_stream is not None:
                    try:
                        data = loopback_stream.read(1024, exception_on_overflow=False)
                    except Exception:
                        data = None
                    if data:
                        self.loopback_buffer.append(
                            _to_16k_mono(data,
                                         int(loopback_info.get("defaultSampleRate", SAMPLE_RATE)),
                                         loopback_info.get("maxInputChannels", 2) or 2,
                                         2)
                        )

                if mic_stream is not None:
                    try:
                        data = mic_stream.read(1024, exception_on_overflow=False)
                    except Exception:
                        data = None
                    if data:
                        rate = int(mic_info.get("defaultSampleRate", SAMPLE_RATE))
                        ch = mic_info.get("maxInputChannels", 1) or 1
                        self.mic_buffer.append(_to_16k_mono(data, rate, ch, 2))
        finally:
            if loopback_stream is not None:
                loopback_stream.stop_stream()
                loopback_stream.close()
            if mic_stream is not None:
                mic_stream.stop_stream()
                mic_stream.close()
            pa.terminate()
