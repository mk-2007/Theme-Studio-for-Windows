"""Sanitizing text that comes from outside (file names, window titles, settings) before it is shown."""
from __future__ import annotations

import re

# C0/C1 controls, bidi overrides/isolates (Trojan-Source style tricks), zero-width and BOM characters
_BAD = re.compile("[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff\ufff9-\ufffb]")
_SPACES = re.compile(r"\s+")


def clean_label(text: object, maxlen: int = 120) -> str:
    """Return a display-safe single-line string: no control/bidi/zero-width characters, bounded length."""
    if not isinstance(text, str):
        return ""
    text = _SPACES.sub(" ", _BAD.sub("", text)).strip()
    if len(text) > maxlen:
        text = text[: maxlen - 1] + "\u2026"
    return text


def has_hidden_chars(text: str) -> bool:
    return bool(_BAD.search(text))
