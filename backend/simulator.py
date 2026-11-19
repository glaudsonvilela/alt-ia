"""Read-only Altside simulation adapter. The Rust engine owns all financial math."""

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import quote


ALTSIDE_BASE = os.environ.get("ALTSIDE_API_BASE_URL", "https://app.bigbanana.io").rstrip("/")
PUBLIC_URL = "https://app.bigbanana.io/"
AMOUNT = r"(\d+(?:[.,]\d+)?)"
SWAP_RE = re.compile(r"\b(?:swap|trocar|troca|converter|convers[aã]o)\b", re.I)
POOL_RE = re.compile(r"\b(?:pool|pools|liquidez)\b", re.I)
TOKEN_RE = re.compile(r"\b(USDC|WETH|ETH|WBTC|BTC|USDT|CBBTC|USDG|KHYPE|UBTC|WHYPE|SOL|HYPE)\b", re.I)


class SimulationUnavailable(Exception):
    pass


class SimulationInputError(Exception):
    pass


def _json_request(path, payload=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        ALTSIDE_BASE + path,
        data=body,
        headers={"User-Agent": "curl/8.0", "Accept": "application/json", "Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            if int(response.headers.get("Content-Length", "0")) > 1_000_000:
                raise SimulationUnavailable("Resposta do simulador acima do limite.")
            raw_body = response.read(1_000_001)
            if len(raw_body) > 1_000_000:
                raise SimulationUnavailable("Resposta do simulador acima do limite.")
            result = json.loads(raw_body)
            if not isinstance(result, dict):
                raise SimulationUnavailable("Resposta inválida do simulador.")
            return result
    except urllib.error.HTTPError as error:
        # The engine may reject stale data or an unavailable RPC. Never invent a quote.
        if error.code in (409, 422):
            raise SimulationUnavailable("O motor Altside não conseguiu validar esta prévia com os dados atuais.") from error
        raise SimulationUnavailable("O motor Altside está indisponível no momento.") from error
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise SimulationUnavailable("Não foi possível consultar o motor Altside agora.") from error


def _decimal(text):
    value = text.replace(",", ".")
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    if not number.is_finite() or number <= 0 or number > Decimal("10000000"):
        return None
    return format(number, "f")


def _amount_for(text, token):
    token_pattern = re.escape(token)
    match = re.search(rf"{AMOUNT}\s*{token_pattern}\b", text, re.I)
    if not match:
        match = re.search(rf"\b{token_pattern}\s*(?:de\s*)?{AMOUNT}", text, re.I)
    return _decimal(match.group(1)) if match else None


def _slippage(text):
    match = re.search(r"(?:slippage|derrapagem)\s*(?:de|:|=)?\s*" + AMOUNT + r"\s*%", text, re.I)
    if not match:
        return 20
    value = _decimal(match.group(1))
    if value is None or Decimal(value) > 5:
        return None
    return int(Decimal(value) * 100)


def _source(raw, kind):
    source = raw.get("source") or {}
    if raw.get("read_only") is not True or source.get("canonical") is not True:
        raise SimulationUnavailable("O motor não confirmou uma prévia canônica de leitura.")
    block = source.get("block_number")
    if not isinstance(block, int) or block <= 0:
        raise SimulationUnavailable("O motor não informou um bloco de origem válido.")
    captured = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "engine": "Altside · Rust",
        "block_number": block,
        "block_timestamp": source.get("block_timestamp") if kind == "pool" else None,
        "captured_at": captured,
        "canonical": True,
        "validity": "Prévia válida para o bloco consultado; preços e liquidez podem mudar.",
    }


def pool_options():
    catalog = _json_request("/markets/pools")
    options = []
    for pool in catalog.get("pools", []):
        if pool.get("capabilities", {}).get("simulation_engine") != "canonical_entry_preview":
            continue
        try:
            option = {
                "id": pool["id"],
                "pair": pool["display_pair"],
                "network": pool["network"]["name"],
                "protocol": pool["protocol"]["name"],
                "base_symbol": pool["base_token"]["symbol"],
                "quote_symbol": pool["quote_token"]["symbol"],
                "tick_spacing": int(pool["tick_spacing"]),
            }
        except (KeyError, TypeError, ValueError):
            continue
        if option["tick_spacing"] > 0 and re.fullmatch(r"[a-z0-9:.-]{1,120}", option["id"]):
            options.append(option)
    return options[:20]


def _run_pool(pool, amount, range_ticks, bps):
    if range_ticks < pool["tick_spacing"] * 2 or range_ticks > 50000:
        raise SimulationInputError(f"A faixa desta pool precisa ter entre {pool['tick_spacing'] * 2} e 50000 ticks.")
    raw = _json_request(f"/simulate/pools/{quote(pool['id'], safe=':')}/entry", {"capital_quote": amount, "range_ticks": range_ticks, "slippage_bps": bps})
    if raw.get("simulation_type") != "canonical_concentrated_liquidity_entry_preview" or raw.get("pool_id") != pool["id"]:
        raise SimulationUnavailable("O motor retornou uma prévia de pool inesperada.")
    allocation = (raw.get("allocation") or {}).get("formatted") or {}
    base_symbol = pool["base_symbol"]
    quote_symbol = pool["quote_symbol"]
    sim = {
        "kind": "pool",
        "title": f"Entrada {pool['pair']}",
        "subtitle": f"{pool['network']} · {pool['protocol']}",
        "metrics": [
            {"label": "Capital", "value": f"{amount} {quote_symbol}"},
            {"label": f"{base_symbol} necessário", "value": f"{allocation.get('base_required')} {base_symbol}"},
            {"label": f"{quote_symbol} necessário", "value": f"{allocation.get('quote_required')} {quote_symbol}"},
            {"label": "Capital não usado", "value": f"{allocation.get('unused_quote')} {quote_symbol}"},
        ],
        "source": _source(raw, "pool"),
        "assumptions": [f"Faixa: {range_ticks} ticks", f"Slippage: {bps / 100:g}%", "Prévia de entrada; rendimento futuro não estimado."],
        "url": PUBLIC_URL,
    }
    if any("None" in metric["value"] for metric in sim["metrics"]):
        raise SimulationUnavailable("O motor retornou uma alocação incompleta.")
    return {"reply": "O motor Altside calculou a alocação de entrada para esta pool. A faixa e os custos assumidos estão abaixo.", "simulation": sim}


def simulate_pool_request(request):
    if not isinstance(request, dict) or set(request) != {"kind", "pool_id", "capital_quote", "range_ticks", "slippage_bps"} or request.get("kind") != "pool":
        raise SimulationInputError("Parâmetros da simulação inválidos.")
    pool = next((option for option in pool_options() if option["id"] == request["pool_id"]), None)
    if pool is None:
        raise SimulationInputError("Pool indisponível para esta prévia.")
    amount = request["capital_quote"]
    if not isinstance(amount, str) or not re.fullmatch(r"\d+(?:[.,]\d{1,18})?", amount):
        raise SimulationInputError("Informe um capital decimal válido.")
    amount = _decimal(amount)
    if amount is None:
        raise SimulationInputError("Informe um capital maior que zero e até 10 milhões.")
    ticks = request["range_ticks"]
    bps = request["slippage_bps"]
    if type(ticks) is not int or type(bps) is not int or not 0 <= bps <= 500:
        raise SimulationInputError("Faixa ou slippage inválidos.")
    return _run_pool(pool, amount, ticks, bps)


def _swap(text):
    assets = [m.group(1).upper() for m in TOKEN_RE.finditer(text)]
    assets = ["WETH" if value == "ETH" else value for value in assets]
    if len(assets) < 2:
        return {"reply": "Para simular o swap, informe o token de entrada, o de saída e o valor. Exemplo: simule swap de 100 USDC para WETH."}
    token_in, token_out = assets[:2]
    if {token_in, token_out} != {"USDC", "WETH"}:
        return {"reply": "A cotação de swap conectada ao motor Altside agora cobre apenas USDC ↔ WETH na Ethereum. Informe um desses pares para uma prévia verificável."}
    amount = _amount_for(text, "ETH" if token_in == "WETH" and re.search(r"\bETH\b", text, re.I) else token_in)
    if amount is None:
        return {"reply": f"Qual valor de {token_in} devo simular? Exemplo: simule swap de 100 {token_in} para {token_out}."}
    bps = _slippage(text)
    if bps is None:
        return {"reply": "Informe uma tolerância de slippage entre 0% e 5%."}
    raw = _json_request("/simulate/swap-quote", {"token_in": token_in, "token_out": token_out, "amount_in": amount, "slippage_bps": bps})
    if raw.get("quote_type") != "uniswap_v3_exact_input_single":
        raise SimulationUnavailable("O motor retornou um tipo de cotação inesperado.")
    incoming, output = raw.get("input") or {}, raw.get("output") or {}
    route = raw.get("route") or {}
    if incoming.get("asset") != token_in or output.get("asset") != token_out:
        raise SimulationUnavailable("Os ativos da resposta não correspondem ao pedido.")
    sim = {
        "kind": "swap",
        "title": f"Swap {token_in} → {token_out}",
        "subtitle": f"{route.get('network', 'Ethereum')} · {route.get('protocol', 'Uniswap v3')}",
        "metrics": [
            {"label": "Entrada", "value": f"{incoming.get('amount')} {token_in}"},
            {"label": "Saída estimada", "value": f"{output.get('expected_amount')} {token_out}"},
            {"label": "Mínimo com slippage", "value": f"{output.get('minimum_amount')} {token_out}"},
            {"label": "Taxa da pool", "value": str(route.get("fee_percent", "—"))},
        ],
        "source": _source(raw, "swap"),
        "assumptions": [f"Slippage: {bps / 100:g}%", "Gas não incluído na saída estimada."],
        "url": PUBLIC_URL,
    }
    if any("None" in metric["value"] for metric in sim["metrics"]):
        raise SimulationUnavailable("O motor retornou uma cotação incompleta.")
    return {"reply": "O motor Altside calculou esta prévia de swap com dados canônicos. Confira os valores e o bloco de origem abaixo.", "simulation": sim}


def _pool(text):
    if re.search(r"\b(comparar|compare|comparação)\b", text, re.I):
        return {"reply": "Posso simular a entrada em uma pool por vez nesta etapa. Diga o par, a rede e o capital; depois envie a segunda pool para comparar as prévias."}
    pools = pool_options()
    tokens = {"WETH" if m.group(1).upper() == "ETH" else m.group(1).upper() for m in TOKEN_RE.finditer(text)}
    if len(tokens) < 2:
        return {"reply": "Vamos configurar sua entrada na pool. Escolha o par, o capital e a faixa na janela de simulação.", "input_request": {"kind": "pool"}}
    candidates = [p for p in pools if {p["base_symbol"].upper(), p["quote_symbol"].upper()} == tokens]
    lower = text.lower()
    if "base" in lower:
        candidates = [p for p in candidates if p["network"].lower().startswith("base")]
    elif "ethereum" in lower or "mainnet" in lower:
        candidates = [p for p in candidates if "ethereum" in p["network"].lower()]
    if "aerodrome" in lower:
        candidates = [p for p in candidates if "aerodrome" in p["protocol"].lower()]
    if "uniswap" in lower:
        candidates = [p for p in candidates if "uniswap" in p["protocol"].lower()]
    if not candidates:
        return {"reply": "Não encontrei esse par nas pools com prévia canônica. Escolha uma das pools disponíveis na janela de simulação.", "input_request": {"kind": "pool"}}
    if len(candidates) > 1:
        return {"reply": "Encontrei mais de uma pool para esse par. Escolha o protocolo na janela de simulação.", "input_request": {"kind": "pool"}}
    pool = candidates[0]
    quote_symbol = pool["quote_symbol"]
    amount = _amount_for(text, quote_symbol)
    tick_match = re.search(r"(\d{2,6})\s*ticks?\b", text, re.I)
    range_ticks = int(tick_match.group(1)) if tick_match else max(1200, pool["tick_spacing"] * 2)
    bps = _slippage(text)
    if amount is None or tick_match is None or bps is None or range_ticks < pool["tick_spacing"] * 2 or range_ticks > 50000:
        return {"reply": "Complete o capital, a faixa e o slippage na janela para calcular a prévia desta pool.", "input_request": {
            "kind": "pool", "pool_id": pool["id"], "capital_quote": amount or "", "range_ticks": range_ticks if range_ticks <= 50000 else 1200, "slippage_bps": bps if bps is not None else 20,
        }}
    return _run_pool(pool, amount, range_ticks, bps)


def handle_simulation(text):
    if SWAP_RE.search(text):
        return _swap(text)
    if POOL_RE.search(text) and re.search(r"\b(simular|simule|simulação|entrar|entrada|investir|alocar|comparar|compare)\b", text, re.I):
        return _pool(text)
    return None
