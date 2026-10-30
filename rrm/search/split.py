"""One Meta chat completion that splits a question into 3-6 subtopics.

POST https://api.meta.ai/v1/chat/completions
https://dev.meta.ai/docs/protocols/chat-completions
Reply text is choices[0].message.content. response_format is the json_schema
on https://dev.meta.ai/docs/api-reference/chat-completions/schemas.
No tools and no second call. max_completion_tokens also counts reasoning
tokens, so the cap is above the ~200 visible tokens we ask for.
"""

import json
import os
import re
import urllib.error
import urllib.request
from collections import OrderedDict

API_URL = "https://api.meta.ai/v1/chat/completions"
MODEL = "muse-spark-1.3-contributor"
MAX_COMPLETION_TOKENS = 1024

_DOI = re.compile(r"^(?:doi:\s*)?10\.\d{4,9}/\S+$", re.I)
_ARXIV = re.compile(
    r"^(?:arxiv:\s*)?(?:[a-z][a-z.-]*(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})(v\d+)?$",
    re.I,
)
_PROMPT = (
    "Split the research question or claim into 3 to 6 distinct subtopics for a "
    "scientific paper search. Each subtopic is one short standalone phrase. "
    'Reply as JSON {"subtopics": ["...", "..."]}.'
)
CACHE = OrderedDict()
# Set only when a completion actually returns. A skipped or cached query leaves the previous value.
LAST_USAGE = None


def usage_of(payload):
    """Token counts from a chat-completions body, or None when the body has none."""
    if not isinstance(payload, dict):
        return None
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None
    out = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            out[key] = value
    return out or None


def skip_split(query):
    """Keyword lists of at most six words, and a bare DOI or arXiv id."""
    text = " ".join(query.split())
    if not text or _DOI.match(text) or _ARXIV.match(text):
        return True
    return len(text.split()) <= 6 and "?" not in text


def parse_subtopics(text):
    if not text:
        return []
    raw = text.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return []
        data = json.loads(raw[start : end + 1])
    items = data.get("subtopics", []) if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return [item.strip() for item in items if isinstance(item, str) and item.strip()][:6]


def message_text(payload):
    """choices[0].message.content, or empty when the choice has no text."""
    if not isinstance(payload, dict):
        raise RuntimeError("muse response is not an object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise RuntimeError("muse response has no choices")
    message = choices[0].get("message") or {}
    if not isinstance(message, dict):
        raise RuntimeError("muse response has no message")
    return message.get("content") or ""


def post_chat(body, timeout=90):
    """One chat completion against the Meta Model API.

    The key is MODEL_API_KEY from the environment. It is sent as a header and
    is not logged here. Returns the decoded JSON body. Sets LAST_USAGE when
    the body carries token counts.
    """
    key = os.environ.get("MODEL_API_KEY")
    if not key:
        raise RuntimeError("MODEL_API_KEY is not set")
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"muse http {exc.code}: {detail}") from None
    global LAST_USAGE
    LAST_USAGE = usage_of(payload)
    return payload


def _complete(query):
    payload = post_chat({
        "model": MODEL,
        "messages": [
            {"role": "developer", "content": _PROMPT},
            {"role": "user", "content": query},
        ],
        "reasoning_effort": "low",
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "subtopics",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"subtopics": {"type": "array", "items": {"type": "string"}}},
                    "required": ["subtopics"],
                },
            },
        },
    })
    return message_text(payload)


def split_query(query, complete=None, cache=None):
    """Subtopics, or [] when the query is keywords or an id. One completion."""
    if skip_split(query):
        return []
    key = " ".join(query.split())
    store = CACHE if cache is None else cache
    if key in store:
        store.move_to_end(key)
        return list(store[key])
    topics = parse_subtopics((complete or _complete)(key))
    if topics:
        store[key] = list(topics)
        store.move_to_end(key)
        while len(store) > 128:
            store.popitem(last=False)
    return topics
