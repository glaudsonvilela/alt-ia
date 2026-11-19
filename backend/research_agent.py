"""Search and review public web evidence for Alt-IA's optional research mode."""

import html
import ipaddress
import json
import os
import re
import urllib.parse
import urllib.request


SEARCH_URL = os.environ.get("ALT_IA_SEARCH_URL", "http://172.17.0.1:8888/search")


def _plain(value, limit):
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", value))).strip()[:limit]


def _public_url(value):
    if not isinstance(value, str) or len(value) > 700:
        return False
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return False
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith((".local", ".internal")) or host == "app.basecamp.com":
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return True


def search_web(user_text, topic, previous_query=""):
    """Plan a query, retrieve snippets, and keep distinct public sources."""
    prompt = _plain(user_text, 500)
    if not prompt:
        raise ValueError("Pesquisa vazia")
    prior = _plain(previous_query, 180)
    elliptical = len(prompt.split()) <= 6 and bool(re.search(r"\b(?:isso|essa|esse|ela|ele|mais|detalh\w*|compar\w*|riscos?|vantagens?|e\s+(?:os|as|se)|por que|como)\b", prompt, re.I))
    query = f"{prior} {prompt}" if prior and elliptical else prompt
    query = query[:500]
    search_query = query
    if topic == "strategies":
        search_query += " estratégia DeFi análise riscos dados"
    params = {"q": search_query, "format": "json", "language": "pt-BR", "safesearch": "1"}
    url = f"{SEARCH_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Alt-IA Research/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = response.read(400_001)
    if len(payload) > 400_000:
        raise ValueError("Resultado da pesquisa muito grande")
    results = json.loads(payload).get("results", [])
    if not isinstance(results, list):
        raise ValueError("Pesquisa inválida")
    sources = []
    seen = set()
    stop = {"sobre", "quais", "qual", "como", "para", "poucas", "palavras", "explique", "citar", "cite", "fontes", "fonte", "riscos", "risco", "estrategia", "estratégia", "pesquise", "pesquisar", "quero", "saber", "isso", "essa", "esse", "mais", "detalhes", "compare", "porque", "investigar"}
    terms = [term for term in re.findall(r"[\wÀ-ÿ-]{4,}", prompt.lower()) if term not in stop]
    priority_terms = [term for term in terms if any(char.isdigit() for char in term)]
    for item in results:
        if not isinstance(item, dict) or not _public_url(item.get("url")):
            continue
        title = _plain(item.get("title"), 220)
        summary = _plain(item.get("content"), 550)
        if not title or not summary:
            continue
        haystack = f"{title} {summary}".lower()
        if priority_terms and not all(term in haystack for term in priority_terms):
            continue
        if not priority_terms and terms and not any(term in haystack for term in terms):
            continue
        source_url = item["url"]
        signature = (urllib.parse.urlsplit(source_url).hostname, re.sub(r"\W+", "", title.lower())[:80])
        if signature in seen:
            continue
        seen.add(signature)
        sources.append({"title": title, "summary": summary, "url": source_url,
                        "source": urllib.parse.urlsplit(source_url).hostname[:80]})
        if len(sources) == 7:
            break
    sources.sort(key=lambda item: (0 if item["source"] in ("ethereum.org", "eips.ethereum.org")
                                    or item["source"].startswith("docs.") else 1))
    return {"query": query, "sources": sources}
