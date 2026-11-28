"""Bounded conversation transport and account-bound retrieval continuity."""
from scenario_tokens import issue, verify


def validate_messages(raw):
    if not isinstance(raw, list) or not 1 <= len(raw) <= 40:
        raise ValueError("Histórico inválido")
    messages = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Mensagem inválida")
        role, text = item.get("role"), item.get("content")
        maximum = 16000 if role == "assistant" else 4000
        if role not in ("user", "assistant") or not isinstance(text, str) or not 1 <= len(text) <= maximum:
            raise ValueError("Mensagem inválida")
        messages.append({"role": role, "content": text})
    if messages[-1]["role"] != "user" or sum(len(m["content"]) for m in messages) > 60000:
        raise ValueError("Histórico muito longo")
    return messages


def research_state(result, email, secret):
    if not result or not result.get("sources"):
        return ""
    return issue({"purpose": "knowledge", "account": email,
                  "question": result["question"],
                  "source_ids": [item["key"] for item in result["sources"]]}, secret)


def read_research_state(token, email, secret):
    state = verify(token, secret)
    if not state or state.get("purpose") != "knowledge" or state.get("account") != email:
        return None
    return state
