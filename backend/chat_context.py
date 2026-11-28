"""Bounded conversation transport and account-bound retrieval continuity."""
from scenario_tokens import issue, verify
import re
import unicodedata


def confirmed_web_task(token, email, secret, messages):
    """Only an answer to a server-issued offer can authorize a main-chat handoff."""
    state = read_research_state(token, email, secret)
    if not state or not state.get('web_offer') or len(messages) < 2:
        return None
    previous_answer = re.sub(r'\n\[Arquivos mostrados nesta resposta: [\s\S]*\]$', '', messages[-2]['content']).rstrip()
    if messages[-2]['role'] != 'assistant' or not previous_answer.endswith(state['web_offer']['question']):
        return None
    text = unicodedata.normalize('NFKD', messages[-1]['content'].lower())
    text = ''.join(c for c in text if not unicodedata.combining(c)).strip(' .!,?')
    if not re.fullmatch(r'(?:sim(?:[, ]+(?:pode|por favor|quero))?|pode(?: sim| procurar| buscar| abrir| pesquisar)?|quero sim|ok|claro|prossiga|(?:abra|abre) o agente|(?:pode )?(?:procurar|pesquisar|buscar) na (?:web|internet))', text):
        return None
    return state['web_offer']['task']


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
    if not result or not (result.get("sources") or result.get('web_offer')):
        return ""
    return issue({"purpose": "knowledge", "account": email,
                  "question": result["question"],
                  "source_ids": [item["key"] for item in result["sources"]],
                  "web_offer": result.get('web_offer')}, secret)


def read_research_state(token, email, secret):
    state = verify(token, secret)
    if not state or state.get("purpose") != "knowledge" or state.get("account") != email:
        return None
    return state
