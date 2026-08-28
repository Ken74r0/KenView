# KenView

Windowed AI meeting assistant that shows live transcriptions and generates real-time answers during screen shares. Built with Python, PyQt6, and Deepgram.

## What it does

- **WASAPI loopback** captures remote participants' voices from system audio
- **Microphone capture** takes the presenter's own voice
- **Deepgram WebSocket** transcribes audio in real time at 16 kHz
- **OpenAI-compatible LLM** detects questions and drafts answers on the fly
- **Capture-excluded overlay** stays visible to the presenter but is hidden from screen shares (Windows 10 build 19041+, via `SetWindowDisplayAffinity`)
- **Reference docs** (.txt/.md/.pdf/.docx) ground answers in material the presenter is speaking from

## Screenshare behaviour

On Windows, the overlay window calls `SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)`. When you share your screen in Zoom, Teams, or Google Meet, the KenView overlay appears black or invisible to remote viewers. Linux and Wayland do **not** support this OS-level exclusion; there, screen-share apps may capture the overlay like any other window.

## Requirements

- Windows 10 build 19041 or later (capture exclusion requires Win32 API)
- Python 3.10 – 3.13
- Microphone + speakers/headphones
- Deepgram API key (free tier works)
- OpenAI-compatible API endpoint with Bearer auth (OpenAI, Ollama, LM Studio, Omniroute, etc.)

## Quick start

```powershell
# Clone the repo
git clone https://github.com/Ken74r0/KenView.git
cd KenView

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

On first run, KenView creates:
- `%APPDATA%\KenView\settings.json` — base URL, Deepgram key, reference file path + text
- Windows Credential Manager entry `KenView` — the LLM API key (encrypted, tied to your user account)

## Configuration

Open the **Control Panel** window to set:

| Field | Purpose |
|-------|---------|
| LLM Base URL | Root URL of an OpenAI-compatible API (e.g. `https://api.openai.com/v1`, `http://localhost:11434/v1` for Ollama) |
| LLM API Key | Bearer token for the `/chat/completions` endpoint |
| Deepgram API Key | Token for Deepgram's real-time `/v1/listen` WebSocket |
| Reference document | Upload a .txt, .md, .pdf, or .docx file that KenView reads when drafting answers |

### Example endpoints

```text
OpenAI:         https://api.openai.com/v1
Ollama:         http://localhost:11434/v1
LM Studio:      http://localhost:1234/v1
Omniroute:      https://your-proxy/v1  (user's existing setup)
```

## Overlay controls

| Action | How |
|--------|-----|
| Drag | Click and hold anywhere on the panel |
| Pin answer | Click **📌 pin** to keep a drafted answer on screen |
| Dismiss answer | Click **✕ dismiss** |
| Change opacity | Use the slider in the Control Panel (10 % – 100 %) |
| Move to monitor | Pick a display from the Monitor dropdown |
| Hide / show | Toggle from the Control Panel or close the overlay (it relaunches on next start) |

The status badge in the overlay header shows:
- Green “Hidden from screen share ✓” — capture exclusion active
- Red warning — running on Linux, old Windows, or without the required build

## Architecture

```
KenView-py/
├── main.py                        # entry point; wires Engine → UI
├── requirements.txt
└── kenview/
    ├── store.py                   # settings.json + keyring (Windows Credential Manager)
    ├── engine.py                  # QThread pipeline: capture → Deepgram → LLM
    ├── native/
    │   └── display_affinity.py    # ctypes wrapper for SetWindowDisplayAffinity
    ├── context/
    │   └── document_loader.py     # text extraction (.txt/.md/.pdf/.docx)
    ├── audio/
    │   └── capture.py             # WASAPI loopback + mic; resample to 16 kHz mono PCM
    ├── transcription/
    │   ├── deepgram_client.py     # WebSocket to Deepgram /v1/listen
    │   └── llm_client.py          # OpenAI-compatible /chat/completions question detection
    └── ui/
        ├── overlay_window.py      # frameless, transparent, always-on-top panel
        └── control_panel.py       # settings form + engine start/stop
```

### Audio pipeline

1. `AudioCaptureThread` opens two `pyaudiowpatch` streams (loopback + mic)
2. Raw PCM is downmixed and resampled to **16 kHz mono 16-bit** using pure stdlib `array` (no `audioop`, compatible with Python 3.13)
3. PCM bytes are drained into a `RingBuffer` and relayed to the Deepgram WebSocket via an `asyncio.Queue`
4. Finalized transcripts accumulate in a rolling 12-utterance window
5. Every ~6 seconds (or at a VAD boundary), the window is sent to the LLM with:
   - System prompt asking it to classify the utterance as a question
   - Reference document context (first 8000 chars)
6. If a question is detected, the overlay shows a drafted answer the presenter can read aloud

### LLM request format

All calls use the OpenAI-compatible schema against the configured base URL:

```http
POST {base_url}/chat/completions
Authorization: Bearer {api_key}
Content-Type: application/json

{
  "model": "gpt-4o-mini",
  "messages": [
    {"role": "system", "content": "You are KenView..."},
    {"role": "user",   "content": "RECENT TRANSCRIPT: ..."}
  ],
  "temperature": 0.2
}
```

No provider is hardcoded. Change `base_url` in settings to route through any OpenAI-compatible proxy.

## Dependencies

| Package | Purpose |
|---------|---------|
| PyQt6 | Frameless overlay + control panel UI |
| pyaudiowpatch | WASAPI loopback + microphone capture on Windows |
| websockets | Deepgram real-time WebSocket client |
| requests | HTTP calls to the LLM endpoint |
| keyring | Encrypted API key storage (Windows Credential Manager) |
| pypdf | PDF text extraction (install if needed) |
| python-docx | DOCX text extraction (install if needed) |

## Troubleshooting

**Overlay not hidden from screen share**
- Confirm you are on Windows 10 build 19041 or later (`winver`)
- Check the status badge: red = exclusion unavailable (Linux, old Windows, or driver issue)
- Close and reopen the overlay after starting a call; some apps (Zoom/Teams) re-enumerate windows at call start

**No audio captured**
- Ensure neither the microphone nor the output device is muted in Windows Sound settings
- Check that `pyaudiowpatch` installed correctly (`pip install pyaudiowpatch`)
- WASAPI loopback may fail on very old audio drivers; the capture thread degrades gracefully and logs the error

**Deepgram connection fails**
- Verify the Deepgram API key is set in the Control Panel
- Check firewall rules allow outbound TCP 443 to `api.deepgram.com`
- Engine status in the overlay reports connection state

**LLM returns empty or malformed answers**
- Confirm the Base URL ends with `/v1` (or use the exact root your proxy expects)
- Confirm the API key has `/chat/completions` access
- The detector expects strict JSON (`{"is_question": true, "answer": "..."}`); providers that wrap responses in markdown may fail to parse — adjust the system prompt if needed

## Roadmap

- [ ] PDF/DOCX parsing via `pypdf` / `python-docx`
- [ ] Per-utterance VAD pause detection instead of fixed 6-second window
- [ ] Multi-monitor hot-switching without relaunch
- [ ] export transcript + answers to Markdown after a session