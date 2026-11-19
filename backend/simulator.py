"""Read-only Altside simulation adapter. The Rust engine owns all financial math."""

import json
import math
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN, localcontext
from urllib.parse import quote
from scenarios import _money, pool_price_scenarios
from historical import PERIOD_INTERVAL, replay_pool_history


ALTSIDE_BASE = os.environ.get("ALTSIDE_API_BASE_URL", "https://app.bigbanana.io").rstrip("/")
PUBLIC_URL = "https://app.bigbanana.io/"
AMOUNT = r"(\d+(?:[.,]\d+)?)"
SWAP_RE = re.compile(r"\b(?:swap|trocar|troca|converter|convers[aã]o)\b", re.I)
POOL_RE = re.compile(r"\b(?:pool|pools|liquidez)\b", re.I)
HISTORY_RE = re.compile(r"\b(?:hist[oó]ric[oa]|passad[oa]|backtest|retroativ[oa]|[uú]ltimos?\s+\d+\s+dias?)\b", re.I)
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
    block = source.get("slot", source.get("block_number"))
    if not isinstance(block, int) or block <= 0:
        raise SimulationUnavailable("O motor não informou um bloco de origem válido.")
    captured = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "engine": raw.get("display_engine", "Altside · Rust"),
        "block_number": block,
        "source_label": "Slot" if "slot" in source else "Bloco",
        "block_timestamp": source.get("block_timestamp") if kind == "pool" else None,
        "captured_at": captured,
        "canonical": True,
        "validity": "Prévia válida para o estado consultado; preços e liquidez podem mudar.",
    }


def pool_options():
    catalog = _json_request("/markets/pools")
    options = []
    for pool in catalog.get("pools", []):
        engine = pool.get("capabilities", {}).get("simulation_engine")
        if engine not in ("canonical_entry_preview", "robinhood_usdg_entry_preview", "hyperevm_analytical_preview", "orca_entry_preview", "legacy_weth_usdc"):
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
                "base_is_token0": pool["base_token"]["address"].lower() == pool["token0"]["address"].lower(),
                "token0_decimals": int(pool["token0"]["decimals"]),
                "token1_decimals": int(pool["token1"]["decimals"]),
                "simulation_available": True,
                "chart_available": True,
                "simulation_engine": engine,
            }
        except (KeyError, TypeError, ValueError):
            continue
        if (option["tick_spacing"] > 0 and 0 <= option["token0_decimals"] <= 36 and 0 <= option["token1_decimals"] <= 36
                and re.fullmatch(r"[A-Za-z0-9:.-]{1,120}", option["id"])):
            options.append(option)
    return options[:20]


def pool_chart(pool_id, interval):
    if interval not in ("15m", "1h", "4h", "1d"):
        raise SimulationInputError("Intervalo do gráfico inválido.")
    pool = next((item for item in pool_options() if item["id"] == pool_id), None)
    if pool is None:
        raise SimulationInputError("Pool indisponível para esta prévia.")
    if not pool["chart_available"]:
        raise SimulationUnavailable("O histórico de velas desta rede ainda não está conectado ao Altside.")
    sol_usdc = pool["simulation_engine"] == "orca_entry_preview" and pool["base_symbol"] == "SOL" and pool["quote_symbol"] == "USDC"
    path = f"/markets/orca-chart?interval={interval}" if sol_usdc else f"/markets/pool-chart?pool_id={quote(pool_id, safe='')}&interval={interval}"
    raw = _json_request(path)
    expected_schema = "altside_orca_chart_v1" if sol_usdc else "altside_pool_chart_v1"
    expected_id = "orca" if sol_usdc else pool_id
    if (raw.get("schema") != expected_schema or raw.get("pool_id") != expected_id
            or raw.get("interval") != interval or raw.get("source") != "geckoterminal"
            or not isinstance(raw.get("candles"), list) or not 1 <= len(raw["candles"]) <= 300):
        raise SimulationUnavailable("O histórico desta pool ainda está sendo preparado.")
    candles = []
    previous = 0
    for item in raw["candles"]:
        if not isinstance(item, dict):
            raise SimulationUnavailable("O histórico da pool retornou dados inválidos.")
        time = item.get("time")
        values = [item.get(key) for key in ("open", "high", "low", "close")]
        if (type(time) is not int or time <= previous or any(type(value) not in (float, int) or not math.isfinite(value) or value <= 0 for value in values)
                or values[2] > min(values[0], values[3]) or values[1] < max(values[0], values[3])):
            raise SimulationUnavailable("O histórico da pool retornou dados inválidos.")
        previous = time
        candles.append({"time": time, "open": values[0], "high": values[1], "low": values[2], "close": values[3]})
    return {"pool_id": pool_id, "interval": interval, "candles": candles,
            "stale": raw.get("stale") is True, "fetched_at_unix": raw.get("fetched_at_unix"), "source": "GeckoTerminal via Altside"}


def pool_snapshot(pool_id, known_pool=None):
    pool = known_pool if known_pool is not None and known_pool["id"] == pool_id else next((item for item in pool_options() if item["id"] == pool_id), None)
    if pool is None:
        raise SimulationInputError("Pool indisponível para esta prévia.")
    raw = _json_request(f"/markets/pools/{quote(pool_id, safe=':')}/snapshot")
    source, state, price = raw.get("source") or {}, raw.get("state") or {}, raw.get("price") or {}
    tick = state.get("tick")
    block = source.get("slot") if pool["simulation_engine"] == "orca_entry_preview" else source.get("block_number")
    if (raw.get("snapshot_type") != "altside_selected_pool_live_snapshot" or raw.get("pool_id") != pool_id
            or source.get("canonical") is not True or type(tick) is not int or type(block) is not int or block <= 0):
        raise SimulationUnavailable("O motor não retornou um estado canônico válido para esta pool.")
    return {
        "pool_id": pool_id,
        "current_tick": tick,
        "tick_spacing": pool["tick_spacing"],
        "block_number": block,
        "source_label": "Slot" if pool["simulation_engine"] == "orca_entry_preview" else "Bloco",
        "price": {"quote_per_base": price.get("quote_per_base") if price.get("status") == "available" else None,
                  "base_symbol": pool["base_symbol"], "quote_symbol": pool["quote_symbol"]},
    }


def _run_pool(pool, amount, range_ticks, bps, explicit_ticks=None):
    if not pool["simulation_available"]:
        raise SimulationUnavailable(f"O motor Altside ainda não oferece prévia de entrada para {pool['network']}.")
    engine = pool["simulation_engine"]
    if engine == "robinhood_usdg_entry_preview":
        return _run_robinhood_pool(pool, amount, range_ticks, bps, explicit_ticks)
    if engine == "legacy_weth_usdc":
        return _run_legacy_pool(pool, amount, range_ticks, bps, explicit_ticks)
    if engine == "hyperevm_analytical_preview":
        return _run_analytical_pool(pool, amount, range_ticks, bps, explicit_ticks)
    if engine == "orca_entry_preview":
        return _run_orca_pool(pool, amount, range_ticks, bps, explicit_ticks)
    if range_ticks < pool["tick_spacing"] * 2 or range_ticks > 50000:
        raise SimulationInputError(f"A faixa desta pool precisa ter entre {pool['tick_spacing'] * 2} e 50000 ticks.")
    payload = {"capital_quote": amount, "range_ticks": range_ticks, "slippage_bps": bps}
    if explicit_ticks is not None:
        payload.update({"tick_lower": explicit_ticks[0], "tick_upper": explicit_ticks[1]})
    raw = _json_request(f"/simulate/pools/{quote(pool['id'], safe=':')}/entry", payload)
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
        "assumptions": [f"Faixa: {explicit_ticks[0]} a {explicit_ticks[1]} ticks" if explicit_ticks else f"Faixa: {range_ticks} ticks", f"Slippage: {bps / 100:g}%", "Taxas futuras e rendimento líquido não estimados."],
        "url": PUBLIC_URL,
    }
    if any("None" in metric["value"] for metric in sim["metrics"]):
        raise SimulationUnavailable("O motor retornou uma alocação incompleta.")
    _scenario_or_note(sim, raw, pool, amount)
    return {"reply": "Prontinho! 🦀 O motor Altside calculou sua entrada. Veja a alocação e, quando disponível, quanto o capital mudaria em cenários de preço 👇", "simulation": sim,
            "follow_up": f"😊 Quer comparar outra faixa ou outro capital para {base_symbol}?"}


def _range_for_snapshot(pool, current_tick, width, explicit_ticks, limit=887272):
    spacing = pool["tick_spacing"]
    if explicit_ticks is None:
        lower = (current_tick - width // 2) // spacing * spacing
        upper = -(-(current_tick + width // 2) // spacing) * spacing
    else:
        lower, upper = explicit_ticks
    if not -limit <= lower < current_tick < upper <= limit or lower % spacing or upper % spacing or upper - lower > 50000:
        raise SimulationInputError("A faixa precisa conter o preço atual e respeitar os ticks desta pool.")
    return lower, upper


def _scenario_or_note(sim, raw, pool, amount):
    try:
        sim["scenarios"] = pool_price_scenarios(raw, pool, amount)
        sim["_scenario_basis"] = {
            "pool": {key: pool[key] for key in ("id", "pair", "network", "protocol", "base_symbol", "quote_symbol", "base_is_token0", "token0_decimals", "token1_decimals")},
            "capital": amount,
            "raw": {key: raw[key] for key in ("allocation", "price", "range", "position_descriptor", "residual_base", "entry_costs_included") if key in raw},
            "source": sim["source"],
        }
    except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError):
        sim["assumptions"].append("Cenários de preço indisponíveis para esta prévia.")


def _run_legacy_pool(pool, amount, range_ticks, bps, explicit_ticks):
    if Decimal(amount) != Decimal(amount).to_integral_value() or Decimal(amount) > 1000000:
        raise SimulationInputError("Nesta pool, informe capital inteiro em USDC, até 1 milhão.")
    payload = {"capital_usdc": int(Decimal(amount)), "range_ticks": max(1, range_ticks // 2)}
    if explicit_ticks is not None:
        payload.update({"tick_lower": explicit_ticks[0], "tick_upper": explicit_ticks[1]})
    raw = _json_request("/simulate/pool", payload)
    source, position, market = raw.get("source") or {}, raw.get("position") or {}, raw.get("market") or {}
    if (raw.get("simulation") != "uniswap_v3_equal_value_position" or raw.get("stateless") is not True
            or raw.get("persisted") is not False or source.get("canonical") is not True
            or type(source.get("block_number")) is not int or source["block_number"] <= 0):
        raise SimulationUnavailable("O motor retornou uma prévia antiga inválida.")
    try:
        base = Decimal(position["weth_used_raw"]) / Decimal(10**18)
        quote_used = Decimal(position["usdc_used_raw"]) / Decimal(10**6)
        unused = Decimal(position["capital_unused_usdc_x6"]) / Decimal(10**6)
        price = Decimal(market["weth_price_usdc_x6"]) / Decimal(10**6)
        lower, upper = position["tick_lower"], position["tick_upper"]
        if any(x < 0 for x in (base, quote_used, unused)) or price <= 0 or type(lower) is not int or type(upper) is not int:
            raise ValueError("invalid legacy allocation")
    except (KeyError, TypeError, InvalidOperation, ValueError) as error:
        raise SimulationUnavailable("O motor retornou uma alocação incompleta.") from error
    sim = {"kind": "pool", "title": f"Entrada {pool['pair']}", "subtitle": f"{pool['network']} · {pool['protocol']}",
           "metrics": [{"label": "Capital", "value": f"{amount} USDC"},
                       {"label": "WETH necessário", "value": f"{base:f} WETH"},
                       {"label": "USDC necessário", "value": f"{quote_used:f} USDC"},
                       {"label": "Capital não usado", "value": f"{unused:f} USDC"}],
           "source": _source({"read_only": True, "source": source}, "pool"),
           "assumptions": [f"Faixa: {lower} a {upper} ticks", "Modelo legado: capital inteiro em USDC; slippage e gas não incluídos."], "url": PUBLIC_URL}
    synthetic = {"allocation": {"formatted": {"base_required": str(base), "quote_required": str(quote_used), "unused_quote": str(unused)}},
                 "price": {"quote_per_base": str(price)}, "range": {"tick_lower": lower, "tick_upper": upper}}
    _scenario_or_note(sim, synthetic, pool, amount)
    return {"reply": "Prontinho! 🦀 O motor Altside calculou a pool WETH/USDC na Ethereum. Veja a alocação e os cenários 👇",
            "simulation": sim, "follow_up": "😊 Quer testar outra faixa ou outro capital em USDC?"}


def _run_analytical_pool(pool, amount, range_ticks, bps, explicit_ticks):
    snapshot = pool_snapshot(pool["id"], pool)
    lower, upper = _range_for_snapshot(pool, snapshot["current_tick"], range_ticks, explicit_ticks)
    with localcontext() as ctx:
        ctx.prec = 60
        capital, price = Decimal(amount), Decimal(str(snapshot["price"]["quote_per_base"]))
        if not price.is_finite() or price <= 0:
            raise SimulationUnavailable("O preço atual desta pool não está disponível.")
        scale = Decimal(10) ** (pool["token0_decimals"] - pool["token1_decimals"])
        def tick_price(tick):
            native = Decimal("1.0001") ** tick * scale
            return native if pool["base_is_token0"] else 1 / native
        floor, ceiling = sorted((tick_price(lower), tick_price(upper)))
        if not floor < price < ceiling:
            raise SimulationUnavailable("O preço atual ficou fora da faixa escolhida. Atualize o gráfico.")
        root, root_floor, root_ceiling = price.sqrt(), floor.sqrt(), ceiling.sqrt()
        base_unit = (root_ceiling - root) / (root * root_ceiling)
        quote_unit = root - root_floor
        liquidity = capital / (base_unit * price + quote_unit)
        base = (liquidity * base_unit).quantize(Decimal(1).scaleb(-pool["token0_decimals" if pool["base_is_token0"] else "token1_decimals"]), rounding=ROUND_DOWN)
        quote_used = (liquidity * quote_unit).quantize(Decimal(1).scaleb(-pool["token1_decimals" if pool["base_is_token0"] else "token0_decimals"]), rounding=ROUND_DOWN)
        unused = capital - base * price - quote_used
        if unused < 0 or unused > capital * Decimal("0.001"):
            raise SimulationUnavailable("A alocação analítica não fechou com o capital informado.")
    source = {"canonical": True, "block_number": snapshot["block_number"]}
    sim = {"kind": "pool", "title": f"Entrada {pool['pair']}", "subtitle": f"{pool['network']} · {pool['protocol']}",
           "metrics": [{"label": "Capital", "value": f"{amount} {pool['quote_symbol']}"},
                       {"label": f"{pool['base_symbol']} estimado", "value": f"{base:f} {pool['base_symbol']}"},
                       {"label": f"{pool['quote_symbol']} estimado", "value": f"{quote_used:f} {pool['quote_symbol']}"},
                       {"label": "Capital não usado", "value": f"{unused:.8f} {pool['quote_symbol']}"}],
           "source": _source({"read_only": True, "source": source, "display_engine": "Alt-IA · preço Altside"}, "pool"),
           "assumptions": [f"Faixa: {lower} a {upper} ticks", "Alocação geométrica indicativa com preço do bloco; não é cotação de swap ou execução.",
                           "Slippage, taxas de entrada, gas e rendimentos futuros não incluídos."], "url": PUBLIC_URL}
    synthetic = {"allocation": {"formatted": {"base_required": str(base), "quote_required": str(quote_used), "unused_quote": str(unused)}},
                 "price": {"quote_per_base": str(price)}, "range": {"tick_lower": lower, "tick_upper": upper}}
    _scenario_or_note(sim, synthetic, pool, amount)
    return {"reply": "Aqui está a estimativa analítica da pool na HyperEVM. 📊 Ela usa o preço observado pelo Altside e mostra como o valor mudaria nos cenários 👇",
            "simulation": sim, "follow_up": f"😊 Quer comparar outra faixa para {pool['base_symbol']}?"}


def _run_orca_pool(pool, amount, range_ticks, bps, explicit_ticks):
    capital = Decimal(amount)
    decimals = pool["token0_decimals"] if not pool["base_is_token0"] else pool["token1_decimals"]
    if capital.as_tuple().exponent < -decimals:
        raise SimulationInputError(f"Informe no máximo {decimals} casas decimais em {pool['quote_symbol']}.")
    sol_usdc = pool["base_symbol"] == "SOL" and pool["quote_symbol"] == "USDC"
    snapshot = pool_snapshot(pool["id"], pool)
    if sol_usdc:
        path = f"/solana/orca/pools/sol-usdc/budget-preview?capital_usdc={amount}&range_ticks={range_ticks}&slippage_bps={bps}"
        if explicit_ticks:
            path += f"&tick_lower={explicit_ticks[0]}&tick_upper={explicit_ticks[1]}"
        raw = _json_request(path)
        quote_data = raw.get("quote") or {}
        allocation = quote_data.get("liquidity") or {}
        if (raw.get("schema") != "altside_solana_orca_budget_preview_v1" or raw.get("pool_id") != pool["id"]
                or raw.get("read_only") is not True or raw.get("writes_performed") is not False
                or raw.get("commitment") != "confirmed" or type(raw.get("cache_slot")) is not int
                or raw["cache_slot"] <= 0 or type(raw.get("cache_age_ms")) is not int
                or raw["cache_age_ms"] > 15000 or quote_data.get("capital_usdc_raw") != int(capital * 10**6)):
            raise SimulationUnavailable("A prévia Orca não confirmou dados de leitura válidos.")
        lower, upper = allocation.get("tick_lower"), allocation.get("tick_upper")
        base_raw, quote_raw = allocation.get("sol_est_raw"), allocation.get("usdc_est_raw")
        residual_base_raw, residual_quote_raw = quote_data.get("residual_sol_min_raw"), quote_data.get("unallocated_usdc_raw")
        source = {"canonical": True, "slot": raw["cache_slot"]}
    else:
        suffix = "hype-sol" if pool["base_symbol"] == "HYPE" else "cbbtc-sol"
        lower, upper = _range_for_snapshot(pool, snapshot["current_tick"], range_ticks, explicit_ticks, 443636)
        capital_raw = int(capital * (10 ** decimals))
        path = f"/solana/orca/pools/{suffix}/budget-preview?capital_raw={capital_raw}&tick_lower={lower}&tick_upper={upper}&slippage_bps={bps}"
        raw = _json_request(path)
        allocation = raw.get("budget") or {}
        if (raw.get("pool_id") != pool["id"] or raw.get("read_only") is not True
                or raw.get("writes_performed") is not False or raw.get("commitment") != "confirmed"
                or type(raw.get("slot")) is not int or raw["slot"] <= 0
                or type(raw.get("age_ms")) is not int or raw["age_ms"] > 15000):
            raise SimulationUnavailable("A prévia Orca não confirmou dados de leitura válidos.")
        if (allocation.get("capital_raw") != str(capital_raw) or allocation.get("capital_symbol") != pool["quote_symbol"]
                or allocation.get("tick_lower") != lower or allocation.get("tick_upper") != upper):
            raise SimulationUnavailable("O capital retornado pela Orca não corresponde ao pedido.")
        base_raw, quote_raw = allocation.get("deposit_b_raw"), allocation.get("deposit_a_raw")
        residual_base_raw, residual_quote_raw = allocation.get("residual_b_raw"), allocation.get("residual_a_raw")
        source = {"canonical": True, "slot": raw["slot"]}
    if (type(lower) is not int or type(upper) is not int or lower >= upper
            or (explicit_ticks is not None and (lower, upper) != explicit_ticks)):
        raise SimulationUnavailable("A Orca retornou uma faixa diferente da solicitada.")
    try:
        base_decimals = pool["token0_decimals"] if pool["base_is_token0"] else pool["token1_decimals"]
        base = Decimal(str(base_raw)) / (10 ** base_decimals)
        quote_used = Decimal(str(quote_raw)) / (10 ** decimals)
        residual_base = Decimal(str(residual_base_raw)) / (10 ** base_decimals)
        residual_quote = Decimal(str(residual_quote_raw)) / (10 ** decimals)
        if any(x < 0 for x in (base, quote_used, residual_base, residual_quote)):
            raise ValueError("invalid orca allocation")
    except (InvalidOperation, TypeError, ValueError) as error:
        raise SimulationUnavailable("A Orca retornou uma alocação incompleta.") from error
    price = Decimal(str(snapshot["price"]["quote_per_base"]))
    if price <= 0 or not price.is_finite():
        raise SimulationUnavailable("O preço atual desta pool não está disponível.")
    sim = {"kind": "pool", "title": f"Entrada {pool['pair']}", "subtitle": f"{pool['network']} · {pool['protocol']}",
           "metrics": [{"label": "Capital", "value": f"{amount} {pool['quote_symbol']}"},
                       {"label": f"{pool['base_symbol']} estimado", "value": f"{base:f} {pool['base_symbol']}"},
                       {"label": f"{pool['quote_symbol']} estimado", "value": f"{quote_used:f} {pool['quote_symbol']}"},
                       {"label": "Saldo residual", "value": f"{residual_quote:f} {pool['quote_symbol']} + {residual_base:f} {pool['base_symbol']}"}],
           "source": _source({"read_only": True, "source": source}, "pool"),
           "assumptions": [f"Faixa: {lower} a {upper} ticks", f"Slippage máximo: {bps / 100:g}%",
                           "Orçamento indicativo da Orca; swap, preço e liquidez podem mudar antes de executar.",
                           "Gas/rent e taxas futuras de LP não incluídos."], "url": PUBLIC_URL}
    synthetic = {"allocation": {"formatted": {"base_required": str(base), "quote_required": str(quote_used), "unused_quote": str(residual_quote)}},
                 "price": {"quote_per_base": str(price)}, "range": {"tick_lower": lower, "tick_upper": upper},
                 "residual_base": str(residual_base), "entry_costs_included": True}
    _scenario_or_note(sim, synthetic, pool, amount)
    return {"reply": "Prontinho! 🌊 O motor Orca do Altside calculou uma prévia de leitura. Veja a composição e os cenários de preço 👇",
            "simulation": sim, "follow_up": f"😊 Quer comparar outra faixa para {pool['base_symbol']}?"}


def _run_robinhood_pool(pool, amount, range_ticks, bps, explicit_ticks):
    capital = Decimal(amount)
    if capital > Decimal("1000000") or capital.as_tuple().exponent < -6:
        raise SimulationInputError("Na Robinhood Chain, informe até 1 milhão de USDG com no máximo 6 casas decimais.")
    if bps > 100:
        raise SimulationInputError("Na Robinhood Chain, o slippage máximo é 1%.")
    payload = {"capital_usdg": amount, "range_ticks": range_ticks, "slippage_bps": bps}
    if explicit_ticks is not None:
        payload.update({"tick_lower": explicit_ticks[0], "tick_upper": explicit_ticks[1]})
    raw = _json_request(f"/simulate/pools/{quote(pool['id'], safe=':')}/entry", payload)
    if (raw.get("simulation_type") != "robinhood_prefunded_usdg_entry_preview"
            or raw.get("pool_id") != pool["id"] or raw.get("transactions_submitted") is not False
            or raw.get("wallet_balance_changed") is not False):
        raise SimulationUnavailable("O motor retornou uma prévia inesperada para a Robinhood Chain.")
    position = raw.get("position") or {}
    leftover = raw.get("leftover") or {}
    swap = raw.get("pool_swap") or {}
    try:
        amounts = [Decimal(value) if isinstance(value, str) else Decimal("NaN") for value in
                   (position.get("weth"), position.get("usdg"), leftover.get("expected"), swap.get("pool_fee_usdg"), position.get("current_quote_per_base"))]
    except InvalidOperation as error:
        raise SimulationUnavailable("O motor retornou valores incompletos para esta prévia.") from error
    if (any(not value.is_finite() or value < 0 for value in amounts) or amounts[-1] <= 0
            or type(position.get("tick_lower")) is not int or type(position.get("tick_upper")) is not int):
        raise SimulationUnavailable("O motor retornou valores incompletos para esta prévia.")
    sim = {
        "kind": "pool", "title": f"Entrada {pool['pair']}",
        "subtitle": f"{pool['network']} · {pool['protocol']}",
        "metrics": [
            {"label": "Capital", "value": f"{amount} USDG"},
            {"label": "WETH necessário", "value": f"{position['weth']} WETH"},
            {"label": "USDG necessário", "value": f"{position['usdg']} USDG"},
            {"label": "Capital não usado", "value": f"{leftover['expected']} USDG"},
            {"label": "Taxa da troca", "value": f"{swap['pool_fee_usdg']} USDG"},
        ],
        "source": _source(raw, "pool"),
        "assumptions": [f"Faixa: {position.get('tick_lower')} a {position.get('tick_upper')} ticks", f"Slippage: {bps / 100:g}%", "Capital em USDG já disponível na Robinhood Chain. Gas e taxas futuras não incluídos."],
        "url": PUBLIC_URL,
    }
    try:
        scenario_raw = {
            "allocation": {"formatted": {"base_required": position["weth"], "quote_required": position["usdg"], "unused_quote": leftover["expected"]}},
            "price": {"quote_per_base": position["current_quote_per_base"]},
            "range": {"tick_lower": position["tick_lower"], "tick_upper": position["tick_upper"]},
        }
        _scenario_or_note(sim, scenario_raw, pool, amount)
    except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError):
        sim["assumptions"].append("Cenários de preço indisponíveis para esta prévia.")
    return {"reply": "Prontinho! 🦀 O Altside calculou a entrada com USDG na Robinhood Chain. Veja a alocação e os cenários de preço 👇", "simulation": sim,
            "follow_up": "😊 Quer testar outra faixa ou outro capital em USDG?"}


def simulate_pool_request(request):
    if isinstance(request, dict) and request.get("kind") == "historical_pool":
        return simulate_historical_pool_request(request)
    required = {"kind", "pool_id", "capital_quote", "range_ticks", "slippage_bps"}
    if not isinstance(request, dict) or not required <= set(request) or set(request) - required not in (set(), {"tick_lower", "tick_upper"}) or request.get("kind") != "pool":
        raise SimulationInputError("Parâmetros da simulação inválidos.")
    pool = next((option for option in pool_options() if option["id"] == request["pool_id"]), None)
    if pool is None:
        raise SimulationInputError("Pool indisponível para esta prévia.")
    if not pool["simulation_available"]:
        raise SimulationUnavailable(f"O motor Altside ainda não oferece prévia de entrada para {pool['network']}.")
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
    explicit_ticks = None
    if "tick_lower" in request:
        lower, upper = request["tick_lower"], request["tick_upper"]
        spacing = pool["tick_spacing"]
        if (type(lower) is not int or type(upper) is not int or lower < -887272 or upper > 887272
                or lower >= upper or upper - lower != ticks or lower % spacing or upper % spacing):
            raise SimulationInputError("Os limites da faixa não são válidos para esta pool.")
        explicit_ticks = (lower, upper)
    return _run_pool(pool, amount, ticks, bps, explicit_ticks)


def simulate_historical_pool_request(request):
    required = {"kind", "pool_id", "capital_quote", "range_ticks", "period_days"}
    if not isinstance(request, dict) or set(request) != required:
        raise SimulationInputError("Parâmetros do histórico inválidos.")
    pool = next((option for option in pool_options() if option["id"] == request["pool_id"]), None)
    if pool is None or not pool["chart_available"]:
        raise SimulationUnavailable("O histórico desta pool ainda não está conectado ao Altside.")
    amount = request["capital_quote"]
    if not isinstance(amount, str) or not re.fullmatch(r"\d+(?:[.,]\d{1,18})?", amount):
        raise SimulationInputError("Informe um capital decimal válido.")
    amount = _decimal(amount)
    if amount is None:
        raise SimulationInputError("Informe um capital maior que zero e até 10 milhões.")
    ticks, period_days = request["range_ticks"], request["period_days"]
    if type(ticks) is not int or ticks < pool["tick_spacing"] * 2 or ticks > 50000:
        raise SimulationInputError("A faixa histórica é inválida para esta pool.")
    if type(period_days) is not int or period_days not in PERIOD_INTERVAL:
        raise SimulationInputError("Escolha um período histórico de 7, 30 ou 90 dias.")
    chart = pool_chart(pool["id"], PERIOD_INTERVAL[period_days][0])
    try:
        simulation = replay_pool_history(chart, pool, amount, ticks, period_days)
    except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError) as error:
        raise SimulationUnavailable("Não há velas históricas suficientes para reconstruir este período com segurança.") from error
    return {"reply": "Aqui está uma simulação ilustrativa com os preços passados da pool. 📊 A tabela mostra como o valor teria mudado; taxas e custos não estão incluídos.",
            "simulation": simulation, "follow_up": "😊 Quer comparar outro período, capital ou faixa?"}


def _swap(text):
    assets = [m.group(1).upper() for m in TOKEN_RE.finditer(text)]
    assets = ["WETH" if value == "ETH" else value for value in assets]
    if len(assets) < 2:
        return {"reply": "Claro! 😊 Para simular o swap, diga o token de entrada, o de saída e o valor. Ex.: 100 USDC para WETH."}
    token_in, token_out = assets[:2]
    if {token_in, token_out} != {"USDC", "WETH"}:
        return {"reply": "Por enquanto, consigo calcular swaps USDC ↔ WETH na Ethereum. 🔄 Me diga o valor para montar a prévia."}
    amount = _amount_for(text, "ETH" if token_in == "WETH" and re.search(r"\bETH\b", text, re.I) else token_in)
    if amount is None:
        return {"reply": f"Qual valor de {token_in} você quer testar? 😊 Ex.: 100 {token_in} para {token_out}."}
    bps = _slippage(text)
    if bps is None:
        return {"reply": "Pode escolher um slippage entre 0% e 5%? 🔎"}
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
    return {"reply": "Prontinho! 🔄 Aqui está a cotação calculada pelo Altside. Para mostrar ganho ou perda futura, preciso de um preço de saída; esta prévia ainda não é uma previsão. 👇", "simulation": sim,
            "follow_up": f"😊 Quer testar outro valor ou informar um preço de saída para {token_out}?"}


def _pool(text, historical=False):
    period_match = re.search(r"\b(7|30|90)\s*dias?\b", text, re.I) if historical else None
    historical_prefill = {"period_days": int(period_match.group(1))} if period_match else {}
    if re.search(r"\b(comparar|compare|comparação)\b", text, re.I):
        return {"reply": "Vamos por partes 😊 Posso calcular uma pool por vez. Diga o par, a rede e o capital; depois comparamos a segunda."}
    pools = pool_options()
    tokens = {"WETH" if m.group(1).upper() == "ETH" else m.group(1).upper() for m in TOKEN_RE.finditer(text)}
    if len(tokens) < 2:
        return {"reply": "Vamos simular com dados passados! 📊 Escolha a pool, o período, o capital e a faixa na janela." if historical else "Vamos simular! 🦀 Escolha a pool, o capital e a faixa na janela que abriu.",
                "input_request": {"kind": "historical_pool" if historical else "pool", **historical_prefill}}
    candidates = [p for p in pools if {p["base_symbol"].upper(), p["quote_symbol"].upper()} == tokens]
    lower = text.lower()
    if "base" in lower:
        candidates = [p for p in candidates if p["network"].lower().startswith("base")]
    elif "ethereum" in lower:
        candidates = [p for p in candidates if "ethereum" in p["network"].lower()]
    elif "robinhood" in lower:
        candidates = [p for p in candidates if "robinhood" in p["network"].lower()]
    elif "hyper" in lower:
        candidates = [p for p in candidates if "hyper" in p["network"].lower()]
    elif "solana" in lower:
        candidates = [p for p in candidates if "solana" in p["network"].lower()]
    if "aerodrome" in lower:
        candidates = [p for p in candidates if "aerodrome" in p["protocol"].lower()]
    if "uniswap" in lower:
        candidates = [p for p in candidates if "uniswap" in p["protocol"].lower()]
    if not candidates:
        return {"reply": "Ainda não encontrei esse par entre as pools disponíveis. 🔎 Escolha uma das opções na janela de simulação.",
                "input_request": {"kind": "historical_pool" if historical else "pool", **historical_prefill}}
    if len(candidates) > 1:
        return {"reply": "Achei mais de uma pool para esse par. 😊 Escolha a rede e o protocolo na janela de simulação.",
                "input_request": {"kind": "historical_pool" if historical else "pool", **historical_prefill}}
    pool = candidates[0]
    if historical:
        if not pool["chart_available"]:
            return {"reply": f"Encontrei {pool['pair']} na {pool['network']}, mas o Altside ainda não fornece velas históricas dessa pool. 🔎 Quer escolher outra rede?"}
        return {"reply": f"Encontrei o histórico de {pool['pair']} na {pool['network']}. 📊 Escolha período, capital e faixa para eu reconstruir o resultado.",
                "input_request": {"kind": "historical_pool", "pool_id": pool["id"], **historical_prefill}}
    if not pool["simulation_available"]:
        return {"reply": f"Encontrei {pool['pair']} na {pool['network']}. 🔎 O preço ao vivo está disponível, mas a prévia de entrada desta pool ainda não foi conectada à Alt-IA.",
                "input_request": {"kind": "pool", "pool_id": pool["id"]}}
    quote_symbol = pool["quote_symbol"]
    amount = _amount_for(text, quote_symbol)
    tick_match = re.search(r"(\d{2,6})\s*ticks?\b", text, re.I)
    range_ticks = int(tick_match.group(1)) if tick_match else max(1200, pool["tick_spacing"] * 2)
    bps = _slippage(text)
    if amount is None or tick_match is None or bps is None or range_ticks < pool["tick_spacing"] * 2 or range_ticks > 50000:
        return {"reply": "Falta pouco! 🦀 Complete o capital, a faixa e o slippage na janela para eu calcular a tabela.", "input_request": {
            "kind": "pool", "pool_id": pool["id"], "capital_quote": amount or "", "range_ticks": range_ticks if range_ticks <= 50000 else 1200, "slippage_bps": bps if bps is not None else 20,
        }}
    return _run_pool(pool, amount, range_ticks, bps)


def handle_simulation(text):
    result = None
    if SWAP_RE.search(text):
        result = _swap(text)
    elif HISTORY_RE.search(text) and (POOL_RE.search(text) or len(TOKEN_RE.findall(text)) >= 2 or re.search(r"\bsimul", text, re.I)):
        result = _pool(text, historical=True)
    elif POOL_RE.search(text) and re.search(r"\b(simular|simule|simulação|entrar|entrada|investir|alocar|comparar|compare)\b", text, re.I):
        result = _pool(text)
    if result is not None and not result.get("simulation") and not result["reply"].rstrip().endswith("?"):
        result["reply"] += "\n\n😊 Quer que eu te ajude a montar essa simulação?"
    return result


SHOCK_VERB = r"(?:subir|sobe|aumentar|aumenta|valorizar|valoriza|alta|cair|cai|descer|desce|diminuir|diminui|desvalorizar|desvaloriza|queda)"
SHOCK_NUMBER = r"(\d+(?:[.,]\d{1,2})?)\s*%"


def parse_price_shock(text):
    """Recognize an explicit token movement, never infer a percentage from prose."""
    token = r"\b(USDC|WETH|ETH|WBTC|BTC|USDT|CBBTC|USDG|KHYPE|UBTC|WHYPE|SOL|HYPE)\b"
    patterns = (
        rf"{token}\s+(?:\w+\s+){{0,3}}?({SHOCK_VERB})\s+(?:\w+\s+){{0,2}}?{SHOCK_NUMBER}",
        rf"\b({SHOCK_VERB})\s+(?:de\s+)?{SHOCK_NUMBER}\s+(?:n[oa]|d[oa]|para|em)\s+{token}",
    )
    match = re.search(patterns[0], text, re.I)
    if match:
        symbol, verb, amount = match.groups()
    else:
        match = re.search(patterns[1], text, re.I)
        if not match:
            return None
        verb, amount, symbol = match.groups()
    change = Decimal(amount.replace(",", "."))
    if change <= 0 or change > 1000:
        raise SimulationInputError("Informe uma variação maior que 0% e de até 1000%.")
    fall = verb.lower() in ("cair", "cai", "descer", "desce", "diminuir", "diminui", "desvalorizar", "desvaloriza", "queda")
    if fall and change >= 100:
        raise SimulationInputError("Uma queda de preço precisa ser menor que 100%.")
    return symbol.upper(), -change if fall else change


def is_quant_pool_question(text):
    return bool((POOL_RE.search(text) or TOKEN_RE.search(text) or re.search(r"\bsimul", text, re.I))
                and (re.search(r"\d+(?:[.,]\d+)?\s*%", text)
                     or re.search(r"\b(?:ganh|perd|lucro|preju[ií]zo|rentabil|quanto|valor|pre[cç]o|dobr)\w*\b", text, re.I)))


def simulate_price_shock(basis, shock):
    if not isinstance(basis, dict):
        return {"reply": "Para calcular essa mudança, preciso de uma simulação de entrada com pool, capital e faixa. 📊 Qual pool, capital e faixa você quer usar?",
                "input_request": {"kind": "pool"}}
    pool, raw, source = basis["pool"], basis["raw"], basis["source"]
    symbol, change = shock
    aliases = {"ETH": "WETH", "BTC": "WBTC"}
    if symbol not in (pool["base_symbol"], pool["quote_symbol"]):
        alias = aliases.get(symbol)
        if alias in (pool["base_symbol"], pool["quote_symbol"]):
            symbol = alias
        else:
            raise SimulationInputError(f"{symbol} não pertence à pool {pool['pair']}. Informe uma das duas moedas da pool.")
    try:
        scenarios = pool_price_scenarios(raw, pool, basis["capital"], changes=(0, change), shock_symbol=symbol)
        values = scenarios.pop("analysis")
        pnl, initial = Decimal(values["pnl"]), Decimal(values["initial"])
        vs_hold = Decimal(values["vs_hold"])
    except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError) as error:
        raise SimulationUnavailable("Não foi possível calcular essa variação com a alocação validada da pool.") from error
    unit = pool["quote_symbol"]
    digits = 2 if unit.upper() in ("USDC", "USDT", "USDG") else 6
    movement = f"{'subir' if change > 0 else 'cair'} {format(abs(change), 'f')}%"
    scenarios["caption"] = f"📊 {symbol} {movement} · valores em {unit}"
    quote_shock = symbol == unit
    conversion = (f"Como {symbol} é a moeda de cotação, o preço de {pool['base_symbol']} em {unit} varia no sentido inverso: "
                  f"preço final = preço inicial ÷ {format(1 + change / 100, 'f')}.") if symbol == unit else (
                  f"Preço de {pool['base_symbol']} em {unit}: preço final = preço inicial × {format(1 + change / 100, 'f')}.")
    external_pct = ((Decimal(values["value"]) * (1 + change / 100) / initial - 1) * 100) if quote_shock else pnl / initial * 100
    other = pool["base_symbol"] if quote_shock else pool["quote_symbol"]
    source = {**source, "engine": "Alt-IA · geometria Altside", "validity": "Hipótese sobre a alocação e o preço do bloco/slot da entrada; não é previsão."}
    sim = {"kind": "pool", "title": f"Se {symbol} {movement}", "subtitle": f"{pool['pair']} · {pool['network']}",
           "metrics": [{"label": "Capital inicial", "value": f"{_money(initial, digits)} {unit}"},
                       {"label": "Valor estimado", "value": f"{_money(Decimal(values['value']), digits)} {unit}"},
                       {"label": "Ganho/perda bruta", "value": f"{'+' if pnl > 0 else '−' if pnl < 0 else ''}{_money(abs(pnl), digits)} {unit}"},
                       {"label": "Variação do capital", "value": f"{_money(pnl / initial * 100, 2)}%"},
                       {"label": "Em referência externa", "value": f"{_money(external_pct, 2)}%"},
                       {"label": "Vs. manter moedas", "value": f"{'+' if vs_hold > 0 else '−' if vs_hold < 0 else ''}{_money(abs(vs_hold), digits)} {unit}"}],
           "source": source, "scenarios": scenarios,
           "assumptions": [conversion, f"Hipótese: {other} fica estável em uma referência externa; {symbol} {movement} nessa referência.",
                           "A variação em referência externa é um índice percentual, sem cotação externa observada.",
                           "Faixa e capital iguais aos da entrada simulada; posição não é rebalanceada manualmente.",
                           "Sem taxas futuras, gas, impostos ou custo de saída; resultado ilustrativo."], "url": PUBLIC_URL,
           "_scenario_basis": basis}
    return {"reply": f"Calculei a hipótese sobre a última entrada em {pool['pair']}. 📊 O resultado abaixo é em {unit}, com a mesma faixa e o mesmo capital.",
            "simulation": sim, "follow_up": f"😊 Quer testar outra variação de {symbol} nessa pool?"}


def replay_pool_context(context):
    """Recalculate old browser conversations that predate signed scenario context."""
    if not isinstance(context, dict) or context.get("kind") != "pool":
        return None
    title, subtitle = context.get("title"), context.get("subtitle")
    if not isinstance(title, str) or not isinstance(subtitle, str) or len(title) > 160 or len(subtitle) > 160:
        return None
    candidates = [pool for pool in pool_options() if title == f"Entrada {pool['pair']}" and subtitle == f"{pool['network']} · {pool['protocol']}"]
    if len(candidates) != 1:
        return None
    pool = candidates[0]
    metrics = context.get("metrics") or []
    assumptions = context.get("assumptions") or []
    if not isinstance(metrics, list) or not isinstance(assumptions, list) or len(metrics) > 6 or len(assumptions) > 5:
        return None
    capital_value = next((item.get("value") for item in metrics if isinstance(item, dict) and item.get("label") == "Capital"), None)
    if not isinstance(capital_value, str):
        return None
    capital = re.fullmatch(r"(\d+(?:[.,]\d{1,18})?) " + re.escape(pool["quote_symbol"]), capital_value)
    range_label = next((item for item in assumptions if isinstance(item, str) and item.startswith("Faixa: ")), "")
    width = re.fullmatch(r"Faixa: (\d{2,6}) ticks", range_label)
    explicit = re.fullmatch(r"Faixa: (-?\d{1,6}) a (-?\d{1,6}) ticks", range_label)
    if not capital or not (width or explicit):
        return None
    ticks = int(width.group(1)) if width else int(explicit.group(2)) - int(explicit.group(1))
    slippage_label = next((item for item in assumptions if isinstance(item, str) and item.startswith("Slippage")), "")
    slip = re.search(r"(\d+(?:[.,]\d+)?)%", slippage_label)
    bps = int(Decimal(slip.group(1).replace(",", ".")) * 100) if slip else 20
    request = {"kind": "pool", "pool_id": pool["id"], "capital_quote": capital.group(1), "range_ticks": ticks, "slippage_bps": bps}
    if explicit:
        request.update({"tick_lower": int(explicit.group(1)), "tick_upper": int(explicit.group(2))})
    return simulate_pool_request(request)
