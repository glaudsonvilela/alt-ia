"""Restricted news bot: plan, retrieve, verify, and present public headlines.

The stages follow Sherlock's planning/review pattern. This adapter has one
capability: reading public news metadata from the Altside Research Lab.
"""

import json
import re
import threading
import time
import urllib.request
from datetime import datetime, time as clock_time, timezone
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo


RESEARCH_URL = "https://altside-macro-research-theta.vercel.app"
LOCAL_TIME = ZoneInfo("America/Sao_Paulo")
NEWS_WORDS = re.compile(r"\b(news|not[ií]cias?|manchetes|resumo do dia)\b", re.I)
ASSETS = {
    "BTC": ("bitcoin", "btc"), "ETH": ("ethereum", "eth", "ether", "weth"),
    "SOL": ("solana", "sol"), "HYPE": ("hyperliquid", "hype"),
    "BNB": ("bnb", "binance coin"), "XRP": ("xrp", "ripple"),
    "AAVE": ("aave",), "USDC": ("usdc",), "USDT": ("usdt", "tether"),
    "ENA": ("ethena", "ena"), "LINK": ("chainlink", "link"),
    "AVAX": ("avalanche", "avax"), "ADA": ("cardano", "ada"),
    "DOGE": ("dogecoin", "doge"), "UNI": ("uniswap", "uni"),
}
NEWS_CONTEXT_REPLY = re.compile(r"^\s*(?:e\s+)?(?:sobre|da|do|de|e|a|o|quero\s+saber\s+sobre|me\s+fale\s+de|mostre\s+(?:a|o|de))\b", re.I)
OTHER_TASK = re.compile(r"\b(simul\w*|swap|pool|capital|faixa|ticks?|slippage|pre[cç]o|quanto|ganh\w*|perd\w*|subir|cair|lending|empr[eé]stim\w*|colateral|garantia|fator\s+de\s+sa[uú]de|liquida[cç][aã]o)\b", re.I)
_cache = {}
_cache_lock = threading.Lock()


def plan(text, previous=None, topic=None):
    """Search only when the user asks for headlines or switches to an asset."""
    explicit = bool(NEWS_WORDS.search(text))
    contextual = previous == "news" and len(text.split()) <= 12 and not OTHER_TASK.search(text)
    if not explicit and not contextual:
        return None
    lowered = text.casefold()
    fresh = re.search(r"\b(?:mais|outras|novas|[uú]ltimas)\s+(?:not[ií]cias?|manchetes)\b|\b(?:atualiz\w*|mostr\w*|traz\w*|busc\w*|pesquis\w*)\s+(?:as?\s+)?(?:not[ií]cias?|manchetes)\b|\b(?:hoje|resumo do dia)\b", lowered, re.I)
    for symbol, aliases in ASSETS.items():
        lookup = (*aliases, "hyper", "hyperevm") if symbol == "HYPE" else aliases
        if any(re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", lowered, re.I) for alias in lookup):
            if previous == "news" and symbol == topic and not fresh:
                return None
            return {"scope": "asset", "asset": symbol, "aliases": aliases}
    match = re.search(r"\b(?:not[ií]cias?|news|manchetes)\s+(?:de|do|da|sobre|para)\s+(?:(?:a|o)\s+)?(?:(?:moeda|ativo|token)\s+)?([\w-]{2,30})", lowered, re.I)
    if not match and contextual and (NEWS_CONTEXT_REPLY.search(text) or len(text.split()) <= 3):
        match = re.search(r"\b(?:sobre|da|do|de|e|a|o)\s+(?:(?:a|o)\s+)?([\w-]{2,30})", lowered, re.I)
        if not match and len(text.split()) == 1 and len(text.strip()) <= 6:
            match = re.fullmatch(r"([\w-]{2,30})", lowered)
    if match and match.group(1) not in ("hoje", "ontem", "dia", "mercado", "cripto", "crypto", "defi", "agora", "outra", "outro", "moeda", "ativo", "token", "obrigado", "valeu", "essa", "essas", "esse", "esses", "isso", "primeira", "segunda", "terceira", "noticia", "notícia", "noticias", "notícias", "resumo"):
        asset = match.group(1).upper()
        return {"scope": "asset", "asset": asset, "aliases": (asset.casefold(),)}
    if previous == "news" and not fresh:
        return None
    if previous == "news" and topic in ASSETS and fresh and re.search(r"\b(?:mais|outras|novas|[uú]ltimas)\b", lowered, re.I):
        return {"scope": "asset", "asset": topic, "aliases": ASSETS[topic]}
    if explicit:
        return {"scope": "daily"}
    return None


def _load(path, body=None, ttl=180):
    now = time.monotonic()
    key = (path, body)
    with _cache_lock:
        old = _cache.get(key)
        if old and now - old[0] < ttl:
            return old[1]
    headers = {"Accept": "application/json", "User-Agent": "Alt-IA-News/1.0"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(RESEARCH_URL + path, body.encode() if body is not None else None,
                                     headers, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(request, timeout=35 if body is not None else 15) as response:
        raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError("Feed de notícias muito grande")
        data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Feed de notícias inválido")
    if path == "/api/state":
        data = {"news": data.get("news") or {}, "defiNews": data.get("defiNews") or {}}
    elif path == "/api/analise-ativo":
        data = {"itens": [item for item in data.get("itens", []) if isinstance(item, dict)
                          and item.get("tipo") == "noticia" and item.get("origem") != "basecamp" and not item.get("interno")]}
    with _cache_lock:
        _cache[key] = (now, data)
    return data


def _date(value):
    if not isinstance(value, str):
        return None
    try:
        if len(value) == 10:
            return datetime.combine(datetime.fromisoformat(value).date(), clock_time(12), LOCAL_TIME).astimezone(timezone.utc)
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _article(item, kind):
    if not isinstance(item, dict):
        return None
    title = item.get("title") if kind == "feed" else item.get("titulo")
    url = item.get("url")
    source = item.get("source") if kind == "feed" else item.get("casa")
    summary = item.get("summary") if kind == "feed" else item.get("previa")
    raw_date = item.get("publishedAt") if kind == "feed" else item.get("data")
    published = _date(raw_date)
    if kind == "feed" and not published and isinstance(url, str):
        match = re.search(r"/(20\d\d)/(\d\d)/(\d\d)/|(?:^|[-/])(20\d\d)-(\d\d)-(\d\d)(?:[-/]|$)", url)
        if match:
            parts = match.group(1, 2, 3) if match.group(1) else match.group(4, 5, 6)
            published = _date("-".join(parts))
    if not isinstance(title, str) or not isinstance(url, str) or not published:
        return None
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.hostname == "app.basecamp.com" or item.get("interno"):
        return None
    clean_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return {"title": title.strip()[:230], "url": clean_url[:600],
            "source": str(source or parsed.hostname)[:65], "summary": str(summary or "").strip()[:260],
            "published_at": published.isoformat(), "time_known": isinstance(raw_date, str) and len(raw_date) > 10}


def _review(items, aliases=None, today=None):
    """Sherlock-style review gate: public news, valid dates/URLs, relevance and dedupe."""
    selected, seen = [], set()
    now = datetime.now(timezone.utc)
    for item in items:
        if not item:
            continue
        published = _date(item["published_at"])
        if not published or (published - now).total_seconds() > 3600:
            continue
        if today and published.astimezone(LOCAL_TIME).date() != today:
            continue
        if aliases and not any(re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", item["title"].casefold(), re.I) for alias in aliases):
            continue
        key = re.sub(r"[^\w]", "", item["title"].casefold())[:90]
        if key in seen:
            continue
        seen.add(key)
        selected.append(item)
    selected.sort(key=lambda item: item["published_at"], reverse=True)
    return selected


def _pick_daily(items):
    crypto = re.compile(r"\b(cripto|crypto|bitcoin|ethereum|solana|defi|onchain|stablecoin|blockchain|hyperliquid|aave|usdc|btc|eth|sol)\b", re.I)
    crypto_sources = ("coindesk", "the block", "wublockchain", "checkonchain", "decrypt", "alea research", "cointelegraph")
    relevant = [item for item in items if crypto.search(item["title"] + " " + item["summary"])
                or item["source"].casefold().startswith(crypto_sources)]
    chosen = relevant[:4]
    chosen_urls = {item["url"] for item in chosen}
    chosen += [item for item in items if item["url"] not in chosen_urls][:3]
    return chosen[:7]


def _present(plan_value, selected, count, today):
    date_label = today.strftime("%d/%m/%Y")
    if plan_value["scope"] == "daily":
        if not selected:
            return {"reply": f"🗞️ Ainda não há notícias publicadas hoje ({date_label}) no feed do Research Lab. Vou conferir novamente quando você pedir.", "follow_up": "Quer consultar as notícias de uma moeda específica?", "news": [], "mode": "news", "news_topic": ""}
        intro = f"🗞️ Resumo de hoje ({date_label}): o Research Lab reuniu {count} notícia{'s' if count != 1 else ''} até agora. Separei destaques de cripto e macro, com fontes e datas."
        question = "Quer que eu filtre as notícias de uma moeda específica?"
        selected = _pick_daily(selected)
    else:
        asset = plan_value["asset"]
        if not selected:
            return {"reply": f"🗞️ Não encontrei notícias recentes de {asset} no acervo público do Research Lab.", "follow_up": "Quer ver o resumo geral de hoje?", "news": [], "mode": "news", "news_topic": asset}
        intro = f"🗞️ Notícias de {asset}: encontrei {count} resultado{'s' if count != 1 else ''} no acervo público. Separei as manchetes mais recentes."
        question = f"Quer que eu analise o possível impacto dessas notícias em uma pool de {asset}?"
    return {"reply": intro, "follow_up": question, "news": selected[:7], "news_source": "Altside Research Lab", "mode": "news", "news_topic": plan_value.get("asset", "")}


def run(text, previous=None, topic=None):
    decision = plan(text, previous, topic)
    if decision is None:
        return None
    if decision["scope"] == "need_asset":
        return {"reply": "🗞️ Claro! Posso filtrar as notícias para você.", "follow_up": "De qual moeda você quer notícias?", "news": [], "mode": "news", "news_topic": ""}
    today = datetime.now(LOCAL_TIME).date()
    if decision["scope"] == "daily":
        feed = _load("/api/state", ttl=180)
        articles = (feed.get("news") or {}).get("articles") or []
        defi = (feed.get("defiNews") or {}).get("articles") or []
        items = [_article(item, "feed") for item in [*articles, *defi]]
        selected = _review(items, today=today)
    else:
        body = json.dumps({"ativo": decision["asset"], "etapa": "buscar"}, ensure_ascii=False)
        result = _load("/api/analise-ativo", body, ttl=600)
        # Only the public 'noticia' items can cross this boundary. Basecamp,
        # research houses, previews of internal documents and analyses cannot.
        news = [item for item in result.get("itens", []) if isinstance(item, dict)
                and item.get("tipo") == "noticia" and item.get("origem") != "basecamp" and not item.get("interno")]
        selected = _review([_article(item, "search") for item in news], aliases=decision["aliases"])
    return _present(decision, selected, len(selected), today)
