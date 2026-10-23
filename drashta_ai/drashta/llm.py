"""Model-provider adapter. Returns None in demo mode. Anthropic adapter is UNTESTED against the live API."""
import os, requests

class LLMError(Exception): pass

def is_live(settings):
    return settings.get("provider") == "anthropic" and bool(os.environ.get("ANTHROPIC_API_KEY"))

def generate(settings, system, messages, max_tokens=900):
    if not is_live(settings): return None
    try:
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=40,
            headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": settings["model"], "max_tokens": max_tokens, "system": system, "messages": messages})
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    except Exception as ex:  # never leak keys/URLs/details to users
        raise LLMError(type(ex).__name__)
