"""Gemini Flash verification of a crowd-sourced correction. Advisory only:
an admin still approves. Output is stored on suggestions.agent_* columns."""

from __future__ import annotations

import json
import os

PROMPT = """Anda adalah verifikator koreksi teks peraturan OJK Indonesia.
Bandingkan teks saat ini dan teks usulan. Tentukan apakah usulan tersebut
akurat dan layak diterapkan.

Teks saat ini:
{current}

Teks usulan:
{suggested}

Alasan pengguna:
{reason}

Jawab HANYA dengan JSON:
{{"decision": "approve|reject|uncertain", "confidence": 0.0-1.0,
  "modified_content": "teks final atau null", "explanation": "alasan singkat"}}
"""


def verify_suggestion(
    current: str, suggested: str, reason: str | None = None
) -> dict:
    import google.generativeai as genai

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = PROMPT.format(
        current=current, suggested=suggested, reason=reason or "(tidak ada)"
    )
    response = model.generate_content(prompt)
    return _parse(response.text)


def _parse(text: str) -> dict:
    """Pull the JSON object out of the model reply; fall back to uncertain."""
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        data = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return {
            "decision": "uncertain",
            "confidence": 0.0,
            "modified_content": None,
            "explanation": "Tidak dapat mengurai respons agen.",
        }
    return {
        "decision": data.get("decision", "uncertain"),
        "confidence": float(data.get("confidence", 0.0)),
        "modified_content": data.get("modified_content"),
        "explanation": data.get("explanation", ""),
    }
