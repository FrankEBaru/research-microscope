"""Display casing. Normalized (lowercase) forms are for matching only (RRM-51).

RRM_CASE=raw restores the pre-RRM-51 text as generated.
"""

import os
import re

_FIRST = re.compile(r"^(\W*)(\S+)", re.UNICODE)


def enabled():
    return os.environ.get("RRM_CASE", "").strip().lower() != "raw"


def is_identifier(token):
    """NeRF, iPhone, mip-NeRF, word2vec, GPT-4: their casing is the name."""
    token = str(token or "")
    if any(ch.isdigit() for ch in token):
        return True
    # Per hyphen part: «In-Context» is title case, «mip-NeRF» is a name.
    return any(any(ch.isupper() for ch in part[1:]) for part in token.split("-"))


def cap_first(text):
    """Upper-case the first letter only when it is lowercase and the first word is not an identifier."""
    text = str(text or "")
    if not enabled():
        return text
    match = _FIRST.match(text)
    if not match:
        return text
    lead, word = match.groups()
    if not word[:1].isalpha() or not word[:1].islower() or is_identifier(word):
        return text
    at = len(lead)
    return text[:at] + text[at].upper() + text[at + 1:]
