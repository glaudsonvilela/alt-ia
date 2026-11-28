"""Stream only the public answer, never provider reasoning or document IDs."""
import json
import re
import time


def answer_prefix(buffer):
    match = re.search(r'"answer"\s*:\s*', buffer)
    if not match or not buffer[match.end():].startswith('"'):
        return ""
    value = buffer[match.end():]
    try:
        result, _ = json.JSONDecoder().raw_decode(value)
        return result if isinstance(result, str) else ""
    except ValueError:
        # A token can stop inside an escape (including a unicode surrogate).
        for cut in range(7):
            candidate = value if cut == 0 else value[:-cut]
            try:
                result = json.loads(candidate + '"')
                if result and 0xD800 <= ord(result[-1]) <= 0xDBFF:
                    result = result[:-1]
                return result
            except ValueError:
                continue
    return ""


def consume_stream(upstream, on_text, structured, deadline):
    content, emitted, finish, usage = "", "", None, None
    last_emit = 0
    for line in upstream:
        if time.monotonic() > deadline:
            raise TimeoutError("Tempo da resposta excedido")
        if not line.startswith(b"data:"):
            continue
        raw = line[5:].strip()
        if raw == b"[DONE]":
            break
        value = json.loads(raw)
        if value.get("error"):
            raise ValueError("Geração interrompida")
        if value.get("usage"):
            usage = value["usage"]
        for choice in value.get("choices") or []:
            delta = choice.get("delta") or {}
            if isinstance(delta.get("content"), str):
                content += delta["content"]
            if len(content) > 160000:
                raise ValueError("Resposta muito longa")
            finish = choice.get("finish_reason") or finish
        visible = answer_prefix(content) if structured else content
        now = time.monotonic()
        if visible.startswith(emitted) and len(visible) > len(emitted) and now - last_emit > .09:
            on_text(visible[len(emitted):])
            emitted, last_emit = visible, now
    visible = answer_prefix(content) if structured else content
    if visible.startswith(emitted) and len(visible) > len(emitted):
        on_text(visible[len(emitted):])
    if finish not in {"stop", "eos"} or not content.strip():
        raise ValueError("Resposta incompleta")
    return {"choices": [{"finish_reason": finish, "message": {"content": content}}], "usage": usage}
