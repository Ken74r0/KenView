"""
LLM question detection + answer drafting.

Uses the OpenAI-compatible /chat/completions schema against the user's
configured base URL (routed through their Omniroute proxy) with a Bearer
token API key. No provider is hardcoded.
"""
import json
import threading
import requests


def _chat_completion(base_url: str, api_key: str, messages, model="gpt-4o-mini",
                     temperature=0.2):
    """One OpenAI-compatible chat completion call. Returns content string."""
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return ""


class QuestionDetector:
    """Takes a recent transcript window + reference doc, asks the LLM whether
    the latest utterance is a question directed at the presenter, and if so
    drafts a concise answer grounded in the reference material."""

    SYSTEM_PROMPT = (
        "You are KenView, an in-meeting cotrained assistant embedded in a "
        "presenter's screen. You receive a live transcript of a meeting plus "
        "a reference document the presenter is speaking from.\n\n"
        "Decide whether the LATEST user utterance is a question posed to the "
        "presenter. If it is NOT a clear question, respond with the single "
        "token JSON: {\"is_question\": false}.\n\n"
        "If it IS a question, respond with JSON {\"is_question\": true, "
        "\"answer\": \"...\"} where answer is a concise, naturally-worded "
        "draft the presenter can read aloud, grounded in the "
        "reference document when relevant. If the reference does not answer "
        "it, give a brief general answer or suggest what to say.\n\n"
        "Reply with ONLY the JSON object, no markdown, no commentary."
    )

    def __init__(self, base_url: str, api_key: str, reference_text: str = "", model="gpt-4o-mini"):
        self.base_url = base_url
        self.api_key = api_key
        self.reference_text = reference_text
        self.model = model

    def analyze(self, transcript_window: str) -> dict:
        """Returns {is_question: bool, answer: str}."""
        reference = self.reference_text.strip()
        ref_block = f"\nREFERENCE DOCUMENT:\n{reference[:8000]}\n" if reference else "\n(no reference loaded)\n"

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"RECENT TRANSCRIPT:\n{transcript_window}\n"
                f"{ref_block}\n"
                "Analyze the content above."
            )},
        ]
        try:
            raw = _chat_completion(self.base_url, self.api_key, messages, self.model)
        except Exception:
            return {"is_question": False, "answer": ""}

        try:
            out = json.loads(raw.strip().strip("`").strip())
            if not isinstance(out, dict):
                return {"is_question": False, "answer": ""}
            return {
                "is_question": bool(out.get("is_question", False)),
                "answer": str(out.get("answer", "")),
            }
        except Exception:
            return {"is_question": False, "answer": ""}
