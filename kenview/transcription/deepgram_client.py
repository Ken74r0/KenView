"""
Deepgram real-time transcription over WebSocket.

Opens a WebSocket to Deepgram's Realtime API and streams buffered 16 kHz
mono PCM audio to it. Transcripts (finalized utterances) are pushed to a
callback so the higher layer can run question detection on them.
"""
import asyncio
import json
import threading
import websockets

DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"

class DeepgramClient:
    def __init__(self, api_key: str, on_final_text, loop: asyncio.AbstractEventLoop):
        """
        api_key     : Deepgram API key
        on_final_text: callable(str) called on each finalized transcript chunk
        loop        : the running asyncio event loop (the QThread's loop)
        """
        self.api_key = api_key
        self.on_final_text = on_final_text
        self.loop = loop
        self.ws = None
        self._buffer = b""
        self._ready = threading.Event()

    # ---- Public API (called from other threads) --------------------------

    def feed(self, pcm_bytes: bytes):
        """Queue PCM bytes for the websocket (thread-safe via the loop)."""
        if self.ws is not None:
            asyncio.run_coroutine_threadsafe(
                self.ws.send(pcm_bytes), self.loop
            )

    # ---- WebSocket lifecycle (runs on the loop) ---------------------------

    async def run(self, audio_queue: asyncio.Queue):
        """Main loop: connect, then stream framed-sent audio and read results."""
        url = (
            f"{DEEPGRAM_WS_URL}?encoding=linear16&sample_rate=16000&channels=1"
            "&interim_results=true&endpointing=300&vad_events=true"
        )
        headers = {"Authorization": f"Token {self.api_key}"}

        async with websockets.connect(url, extra_headers=headers) as ws:
            self.ws = ws
            self._ready.set()
            # Two concurrent tasks: sender and receiver
            sender = asyncio.create_task(self._send_loop(audio_queue))
            receiver = asyncio.create_task(self._recv_loop())
            await asyncio.gather(sender, receiver)

    async def _send_loop(self, audio_queue: asyncio.Queue):
        while True:
            data = await audio_queue.get()
            if data is None:  # sentinel => stop
                break
            # Deepgram expects a 16-byte JSON message frame first, then audio
            meta = b'{"type":"KeepAlive"}'
            await self.ws.send(meta)
            await self.ws.send(data)

    async def _recv_loop(self):
        async for raw in self.ws:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            # Look at the transcript channel for finalized alternatives
            if msg.get("type") == "Results":
                channel = msg.get("channel", {}).get("alternatives", [{}])[0]
                transcript = channel.get("transcript", "")
                is_final = bool(msg.get("is_final"))
                if transcript and is_final:
                    self.on_final_text(transcript.strip())
            elif msg.get("type") == "Finalize" or msg.get("type") == "SpeechFinal":
                pass  # VAD boundary; could be used for natural pause detection
