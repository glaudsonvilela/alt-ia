"""Read-only Aave V3 market catalog and multi-asset lending scenarios."""

import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


API = "https://api.v3.aave.com/graphql"
CHAIN_IDS = (1, 42161, 10, 8453, 137, 43114, 56, 143, 9745, 4326)
MARKETS_QUERY = "query { markets(request: {chainIds: [1,42161,10,8453,137,43114,56,143,9745,4326]}) { name address chain { name chainId } } }"
MARKET_QUERY = """query ($address: EvmAddress!, $chainId: ChainId!) {
  market(request: {address: $address, chainId: $chainId}) {
    name address chain { name chainId }
    reserves {
      underlyingToken { symbol name address decimals }
      usdExchangeRate isFrozen isPaused
      supplyInfo { apy { value } maxLTV { value } liquidationThreshold { value } canBeCollateral }
      borrowInfo { apy { value } borrowingState }
    }
  }
}"""
WALLET_QUERY = """query ($markets: [MarketInput!]!, $user: EvmAddress!) {
  userSupplies(request: {markets: $markets, user: $user}) {
    currency { address symbol } balance { amount { value } } isCollateral
  }
  userBorrows(request: {markets: $markets, user: $user}) {
    currency { address symbol } debt { amount { value } }
  }
}"""
_cache = {}


class LendingMarketError(Exception):
    pass


def _graphql(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    request = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=16) as response:
            raw = response.read(1_500_001)
        if len(raw) > 1_500_000:
            raise LendingMarketError("Dados do mercado acima do limite.")
        result = json.loads(raw)
        if result.get("errors") or not isinstance(result.get("data"), dict):
            raise LendingMarketError("Não foi possível ler este mercado agora.")
        return result["data"]
    except (OSError, ValueError, TypeError) as error:
        raise LendingMarketError("Não foi possível consultar o mercado agora.") from error


def _cached(key, ttl, fetch):
    item = _cache.get(key)
    if item and item[0] > time.monotonic():
        return item[1]
    value = fetch()
    _cache[key] = (time.monotonic() + ttl, value)
    return value


def markets():
    raw = _cached("markets", 600, lambda: _graphql(MARKETS_QUERY)["markets"])
    display = {"EthereumEtherFi": "Ethereum · EtherFi", "EthereumLido": "Ethereum · Lido",
               "EthereumHorizon": "Ethereum · Horizon", "BNB": "BNB Chain"}
    return [{"name": "Aave V3 · " + display.get(item["name"].removeprefix("AaveV3"), item["name"].removeprefix("AaveV3")), "address": item["address"],
             "chain_id": item["chain"]["chainId"], "chain": item["chain"]["name"]} for item in raw]


def _selected_market(chain_id, address):
    if type(chain_id) is not int or chain_id not in CHAIN_IDS or not isinstance(address, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", address):
        raise LendingMarketError("Escolha um mercado válido.")
    match = next((m for m in markets() if m["chain_id"] == chain_id and m["address"].lower() == address.lower()), None)
    if not match:
        raise LendingMarketError("Mercado não disponível.")
    return match


def market(chain_id, address):
    selected = _selected_market(chain_id, address)
    raw = _cached((chain_id, address.lower()), 60, lambda: _graphql(MARKET_QUERY, {"chainId": chain_id, "address": address})["market"])
    if not isinstance(raw, dict) or not isinstance(raw.get("reserves"), list):
        raise LendingMarketError("Este mercado está indisponível agora.")
    assets = []
    for reserve in raw["reserves"]:
        token, supply, borrow = reserve["underlyingToken"], reserve["supplyInfo"], reserve.get("borrowInfo")
        if reserve["isPaused"]:
            continue
        assets.append({"symbol": token["symbol"], "name": token["name"], "address": token["address"],
                       "price": reserve["usdExchangeRate"], "supply_apy": supply["apy"]["value"],
                       "borrow_apy": borrow["apy"]["value"] if borrow else None,
                       "ltv": supply["maxLTV"]["value"], "liquidation_threshold": supply["liquidationThreshold"]["value"],
                       "can_supply": not reserve["isFrozen"],
                       "can_borrow": bool(borrow and borrow["borrowingState"] == "ENABLED" and not reserve["isFrozen"]),
                       "can_collateral": bool(supply["canBeCollateral"] and not reserve["isFrozen"]),
                       "frozen": reserve["isFrozen"]})
    return {**selected, "assets": assets, "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def wallet(chain_id, address, user):
    _selected_market(chain_id, address)
    if not isinstance(user, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", user):
        raise LendingMarketError("Informe uma carteira EVM válida.")
    data = _graphql(WALLET_QUERY, {"markets": [{"address": address, "chainId": chain_id}], "user": user})
    supplies = [{"asset": row["currency"]["address"], "amount": row["balance"]["amount"]["value"],
                 "collateral": row["isCollateral"]} for row in data["userSupplies"]]
    borrows = [{"asset": row["currency"]["address"], "amount": row["debt"]["amount"]["value"]} for row in data["userBorrows"]]
    return {"supplies": supplies, "borrows": borrows}


def _number(value, *, zero=False, max_value="10000000000"):
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:[.,]\d{1,18})?", value):
        raise LendingMarketError("Informe valores numéricos válidos.")
    try:
        number = Decimal(value.replace(",", "."))
    except InvalidOperation as error:
        raise LendingMarketError("Informe valores numéricos válidos.") from error
    if not number.is_finite() or number < 0 or (not zero and number == 0) or number > Decimal(max_value):
        raise LendingMarketError("Valor fora do limite.")
    return number


def _fmt(value, digits=2):
    return f"{value:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def simulate(request):
    if not isinstance(request, dict) or request.get("kind") != "lending" or request.get("version") != 2:
        raise LendingMarketError("Pedido de lending inválido.")
    if set(request) - {"kind", "version", "chain_id", "market_address", "supplies", "borrows", "shock", "days"}:
        raise LendingMarketError("Pedido de lending inválido.")
    data = market(request.get("chain_id"), request.get("market_address"))
    assets = {a["address"].lower(): a for a in data["assets"]}
    supplies, borrows = request.get("supplies"), request.get("borrows")
    if not isinstance(supplies, list) or not isinstance(borrows, list) or len(supplies) > 12 or len(borrows) > 12 or not supplies:
        raise LendingMarketError("Adicione ao menos um ativo fornecido; limite de 12 por lado.")
    if type(request.get("days")) is not int or not 0 <= request["days"] <= 3650:
        raise LendingMarketError("Escolha de 0 a 3650 dias.")
    shock = request.get("shock") or {}
    if not isinstance(shock, dict) or set(shock) - {"asset", "pct"} or type(shock.get("pct", 0)) is not int or not -95 <= shock.get("pct", 0) <= 500:
        raise LendingMarketError("Variação de preço inválida.")
    shock_key = str(shock.get("asset") or "").lower()
    if shock_key and shock_key not in assets:
        raise LendingMarketError("Ativo da variação inválido.")
    parsed = {"supplies": [], "borrows": []}
    for side, rows in (("supplies", supplies), ("borrows", borrows)):
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) - ({"asset", "amount", "price", "collateral"} if side == "supplies" else {"asset", "amount", "price"}):
                raise LendingMarketError("Ativo inválido.")
            key = str(row.get("asset") or "").lower()
            if key not in assets or key in seen:
                raise LendingMarketError("Ativo duplicado ou não disponível.")
            seen.add(key)
            asset = assets[key]
            if side == "supplies" and not asset["can_supply"] or side == "borrows" and not asset["can_borrow"]:
                raise LendingMarketError(f"{asset['symbol']} não está disponível para esta operação.")
            amount = _number(row.get("amount"))
            if row.get("price") is not None:
                baseline = Decimal(asset["price"])
                override = _number(row["price"])
                if not baseline / 20 <= override <= baseline * 20:
                    raise LendingMarketError("Preço ajustado fora do limite.")
                asset = {**asset, "price": str(override)}
            collateral = side == "supplies" and row.get("collateral") is True
            if collateral and not asset["can_collateral"]:
                raise LendingMarketError(f"{asset['symbol']} não aceita garantia neste mercado.")
            parsed[side].append((asset, amount, collateral))
    if not any(row[2] for row in parsed["supplies"]) and borrows:
        raise LendingMarketError("Ative ao menos uma garantia para tomar empréstimo.")

    def totals(days=0, change=0):
        supplied = borrowed = weighted_ltv = weighted_liquidation = Decimal(0)
        income = cost = Decimal(0)
        for asset, amount, collateral in parsed["supplies"]:
            rate = Decimal(asset["supply_apy"])
            value = amount * Decimal(asset["price"]) * ((1 + rate) ** (Decimal(days) / 365))
            if asset["address"].lower() == shock_key:
                value *= 1 + Decimal(change) / 100
            supplied += value
            income += amount * Decimal(asset["price"]) * (((1 + rate) ** (Decimal(days) / 365)) - 1)
            if collateral:
                weighted_ltv += value * Decimal(asset["ltv"])
                weighted_liquidation += value * Decimal(asset["liquidation_threshold"])
        for asset, amount, _ in parsed["borrows"]:
            rate = Decimal(asset["borrow_apy"])
            value = amount * Decimal(asset["price"]) * ((1 + rate) ** (Decimal(days) / 365))
            if asset["address"].lower() == shock_key:
                value *= 1 + Decimal(change) / 100
            borrowed += value
            cost += amount * Decimal(asset["price"]) * (((1 + rate) ** (Decimal(days) / 365)) - 1)
        return {"supplied": supplied, "borrowed": borrowed, "ltv": weighted_ltv,
                "liquidation": weighted_liquidation, "income": income, "cost": cost,
                "health": weighted_liquidation / borrowed if borrowed else None}

    now = totals()
    future = totals(request["days"], shock.get("pct", 0))
    change = shock.get("pct", 0)
    rows = []
    scenarios = [("Agora", 0, 0)]
    if change and shock_key:
        scenarios.append((f"Preço {change:+d}%", 0, change))
    if request["days"]:
        scenarios.append((f"Em {request['days']} dias", request["days"], change))
    for label, days, pct in scenarios:
        state = totals(days, pct)
        health = state["health"]
        rows.append({"label": label, "price": f"US$ {_fmt(state['supplied'] - state['borrowed'])}",
                     "value": _fmt(health) if health is not None else "Sem dívida",
                     "pnl": "Liquidação possível" if health is not None and health < 1 else "Acima do limite",
                     "tone": "loss" if health is not None and health < 1 else "flat"})
    interest = future["income"] - future["cost"]
    liquidation_rows = []
    for asset, _, collateral in parsed["supplies"]:
        if not collateral:
            continue
        key = asset["address"].lower()
        collateral_coefficient = sum(amount * Decimal(item["liquidation_threshold"])
                                     for item, amount, enabled in parsed["supplies"] if enabled and item["address"].lower() == key)
        debt_coefficient = sum(amount for item, amount, _ in parsed["borrows"] if item["address"].lower() == key)
        coefficient = collateral_coefficient - debt_coefficient
        price = Decimal(asset["price"])
        target = now["borrowed"] - now["liquidation"] + coefficient * price
        liquidation_price = target / coefficient if coefficient > 0 and target > 0 else None
        liquidation_rows.append({"label": asset["symbol"], "price": f"US$ {_fmt(price)}",
                                 "value": f"US$ {_fmt(liquidation_price)}" if liquidation_price else "Sem limite isolado",
                                 "pnl": f"{_fmt((price - liquidation_price) / price * 100)}%" if liquidation_price else "—",
                                 "tone": "loss" if liquidation_price and liquidation_price >= price else "flat"})
    credit = max(Decimal(0), now["ltv"] - now["borrowed"])
    health_text = _fmt(now["health"]) if now["health"] is not None else "Sem dívida"
    metrics = [{"label": "Fornecido", "value": f"US$ {_fmt(now['supplied'])}"},
               {"label": "Emprestado", "value": f"US$ {_fmt(now['borrowed'])}"},
               {"label": "Patrimônio", "value": f"US$ {_fmt(now['supplied'] - now['borrowed'])}"},
               {"label": "Crédito disponível", "value": f"US$ {_fmt(credit)}"},
               {"label": "Saúde", "value": health_text},
               {"label": f"Juros líquidos em {request['days']} dias", "value": f"US$ {_fmt(interest)}"}]
    if now["borrowed"] > now["ltv"]:
        metrics.append({"label": "Entrada", "value": "Acima do limite"})
    name = data["name"]
    reply = (f"🛟 Em {name}, você teria US$ {_fmt(now['supplied'])} fornecidos e US$ {_fmt(now['borrowed'])} de dívida. "
             f"A saúde seria {health_text}; o crédito restante, US$ {_fmt(credit)}. "
             f"Em {request['days']} dias, com as taxas atuais constantes, os juros líquidos seriam US$ {_fmt(interest)}.")
    if change and shock_key:
        reply += f" Com {assets[shock_key]['symbol']} a {change:+d}%, a saúde estimada seria {_fmt(future['health']) if future['health'] is not None else 'sem dívida'}."
    if now["borrowed"] > now["ltv"]:
        reply += " ⚠️ Esta dívida supera o limite de entrada do mercado; reduza o empréstimo ou aumente a garantia."
    simulation = {"kind": "lending", "title": name, "subtitle": f"{data['chain']} · posição simulada",
                  "metrics": metrics, "scenarios": {"caption": "📊 Patrimônio e saúde por cenário", "headers": ["Cenário", "Patrimônio", "Saúde", "Situação"],
                   "rows": rows, "note": "Juros projetados com APYs constantes; a variação de preço afeta o ativo selecionado."},
                  "extra_tables": [{"caption": "🎯 Preço de liquidação por garantia", "headers": ["Ativo", "Preço atual", "Liquidação", "Distância"],
                                    "rows": liquidation_rows, "note": "Cada preço é calculado com os demais ativos constantes."},
                                   {"caption": "📅 Acúmulo de juros", "headers": ["Prazo", "Juros recebidos", "Juros pagos", "Saldo"],
                                    "rows": [{"label": f"{days} dias", "price": f"US$ {_fmt(totals(days)['income'])}",
                                              "value": f"US$ {_fmt(totals(days)['cost'])}",
                                              "pnl": f"US$ {_fmt(totals(days)['income'] - totals(days)['cost'])}",
                                              "tone": "gain" if totals(days)["income"] >= totals(days)["cost"] else "loss"}
                                             for days in sorted({7, 30, 90, request["days"]}) if days > 0],
                                    "note": "Projeção de juros futuros com as taxas atuais constantes."}],
                  "source": {"engine": "Alt-IA · lending", "kind": "lending_live", "source_label": "Dados", "block_number": int(time.time()),
                             "captured_at": data["updated_at"], "validity": "Parâmetros e APYs podem mudar; resultados são estimativas."},
                  "assumptions": [f"Juros ganhos: US$ {_fmt(future['income'])}; juros pagos: US$ {_fmt(future['cost'])}.",
                                  "Limites especiais, eMode, caps, taxas de gás e bônus de liquidação não incluídos."],
                  "url": "https://app.bigbanana.io/"}
    return {"reply": reply, "simulation": simulation, "mode": "lending", "lending_request": request,
            "follow_up": "😊 Quer alterar o prazo, a garantia ou o preço de algum ativo?"}
