"""Bounded wallet research: on-chain balances plus source-attributed market scenarios."""

import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation

from wallet_lookup import WalletUnavailable, lookup_wallet, validate_request


ETH_RPC = "https://ethereum-rpc.publicnode.com"
SOL_RPC = "https://api.mainnet-beta.solana.com"
PRICE_API = "https://coins.llama.fi/prices"
ETH_TOKENS = (
    ("USDC", "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6),
    ("USDT", "0xdac17f958d2ee523a2206206994597c13d831ec7", 6),
    ("WETH", "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", 18),
    ("WBTC", "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", 8),
    ("DAI", "0x6b175474e89094c44da98b954eedeac495271d0f", 18),
)
SOL_TOKENS = (("USDC", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", 6),)
NATIVE_PRICE_IDS = {"bitcoin": "coingecko:bitcoin", "ethereum": "coingecko:ethereum", "solana": "coingecko:solana"}


def _read_json(request, *, timeout=7, limit=120_000, open_url=urllib.request.urlopen):
    with open_url(request, timeout=timeout) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Resposta externa muito grande")
    return json.loads(raw)


def _request(url, payload=None):
    headers = {"Accept": "application/json", "User-Agent": "Alt-IA/1.0 (read-only wallet research)"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    return urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                                  headers=headers, method="POST" if payload is not None else "GET")


def _rpc(url, method, params, *, limit=120_000):
    data = _read_json(_request(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}), limit=limit)
    if not isinstance(data, dict) or data.get("error") or "result" not in data:
        raise ValueError("RPC indisponível")
    return data["result"]


def _eth_balances(address):
    if _rpc(ETH_RPC, "eth_chainId", []) != "0x1":
        raise ValueError("Rede Ethereum incorreta")
    block = _rpc(ETH_RPC, "eth_blockNumber", [])
    if not isinstance(block, str) or not block.startswith("0x"):
        raise ValueError("Bloco Ethereum inválido")
    padded = address[2:].lower().rjust(64, "0")
    def read_token(spec):
        symbol, contract, decimals = spec
        try:
            raw = _rpc(ETH_RPC, "eth_call", [{"to": contract, "data": "0x70a08231" + padded}, block])
            quantity = Decimal(int(raw, 16)) / Decimal(10) ** decimals
        except (OSError, ValueError, TypeError, InvalidOperation):
            return None
        if quantity > 0:
            return {"symbol": symbol, "quantity": quantity, "price_id": f"ethereum:{contract}", "source": "Ethereum RPC"}
        return None

    with ThreadPoolExecutor(max_workers=3) as workers:
        return [item for item in workers.map(read_token, ETH_TOKENS) if item]


def _sol_balances(address):
    balances = []
    for symbol, mint, _ in SOL_TOKENS:
        try:
            result = _rpc(SOL_RPC, "getTokenAccountsByOwner", [address, {"mint": mint}, {"encoding": "jsonParsed", "commitment": "confirmed"}], limit=120_000)
            entries = result.get("value") if isinstance(result, dict) else None
            if not isinstance(entries, list) or len(entries) > 100:
                continue
            quantity = Decimal(0)
            for entry in entries:
                token = entry["account"]["data"]["parsed"]["info"]["tokenAmount"]
                quantity += Decimal(token["amount"]) / Decimal(10) ** int(token["decimals"])
        except (OSError, ValueError, TypeError, KeyError, InvalidOperation):
            continue
        if quantity > 0:
            balances.append({"symbol": symbol, "quantity": quantity, "price_id": f"solana:{mint}", "source": "Solana RPC"})
    return balances


def _prices(price_ids, now):
    if not price_ids:
        return {"now": {}, "day": {}, "week": {}, "month": {}}
    joined = ",".join(price_ids)
    def read_period(period, timestamp):
        path = f"current/{joined}" if period == "now" else f"historical/{timestamp}/{joined}"
        try:
            data = _read_json(_request(f"{PRICE_API}/{path}"), limit=40_000)
            coins = data.get("coins", {})
        except (OSError, ValueError, TypeError):
            coins = {}
        cleaned = {}
        for price_id in price_ids:
            item = coins.get(price_id)
            if not isinstance(item, dict):
                continue
            try:
                price = Decimal(str(item["price"]))
                confidence = Decimal(str(item.get("confidence", 0)))
                age = abs(int(item["timestamp"]) - timestamp)
            except (InvalidOperation, ValueError, TypeError, KeyError):
                continue
            if price.is_finite() and price > 0 and confidence >= Decimal("0.8") and age <= (3600 if period == "now" else 172800):
                cleaned[price_id] = price
        return period, cleaned

    periods = (("now", now), ("day", now - 86400), ("week", now - 7 * 86400), ("month", now - 30 * 86400))
    with ThreadPoolExecutor(max_workers=4) as workers:
        return dict(workers.map(lambda item: read_period(*item), periods))


def _money(value):
    return f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _native_fallback(request):
    """Use direct public chain sources if Altside's asynchronous lookup is not ready."""
    request = validate_request(request)
    network, address = request["network"], request["address"]
    transactions = []
    if network == "bitcoin":
        data = _read_json(_request(f"https://blockstream.info/api/address/{address}"), limit=10_000)
        stats = data["chain_stats"]
        raw = int(stats["funded_txo_sum"]) - int(stats["spent_txo_sum"])
        if raw < 0:
            raise WalletUnavailable("O saldo Bitcoin veio em um formato inesperado.")
        source, asset, decimals = "Blockstream", "BTC", 8
        try:
            items = _read_json(_request(f"https://blockstream.info/api/address/{address}/txs"), limit=350_000)
            for item in items[:2]:
                received = sum(int(output.get("value", 0)) for output in item.get("vout", []) if output.get("scriptpubkey_address") == address)
                spent = sum(int(input_item.get("prevout", {}).get("value", 0)) for input_item in item.get("vin", [])
                            if input_item.get("prevout", {}).get("scriptpubkey_address") == address)
                net = received - spent
                transactions.append({"txid": item["txid"], "direction": "received" if net > 0 else "sent" if net < 0 else "self_or_other",
                                     "amount": f"{abs(Decimal(net) / Decimal(10) ** 8):,.8f}".replace(",", "_").replace(".", ",").replace("_", "."),
                                     "block_time_unix": item.get("status", {}).get("block_time"),
                                     "confirmed": item.get("status", {}).get("confirmed") is True})
        except (OSError, ValueError, TypeError, KeyError):
            pass
        transaction_count = stats.get("tx_count")
    elif network == "ethereum":
        if _rpc(ETH_RPC, "eth_chainId", []) != "0x1":
            raise WalletUnavailable("A fonte Ethereum respondeu com outra rede.")
        raw = int(_rpc(ETH_RPC, "eth_getBalance", [address, "latest"]), 16)
        source, asset, decimals, transaction_count = "Ethereum RPC", "ETH", 18, None
    else:
        result = _rpc(SOL_RPC, "getBalance", [address, {"commitment": "confirmed"}])
        raw = int(result["value"])
        source, asset, decimals, transaction_count = "Solana RPC", "SOL", 9, None
        try:
            signatures = _rpc(SOL_RPC, "getSignaturesForAddress", [address, {"limit": 2, "commitment": "confirmed"}], limit=10_000)
            for item in signatures[:2]:
                if isinstance(item.get("signature"), str):
                    transactions.append({"txid": item["signature"], "direction": "self_or_other", "amount": None,
                                         "block_time_unix": item.get("blockTime"), "confirmed": item.get("err") is None})
        except (OSError, ValueError, TypeError, KeyError):
            pass
    quantity = Decimal(raw) / Decimal(10) ** decimals
    return {"network": network, "network_label": network.capitalize(), "address": address, "asset": asset,
            "balance_raw": str(raw), "decimals": decimals,
            "balance": f"{quantity:,.6f}".replace(",", "_").replace(".", ",").replace("_", "."),
            "value_usdc": None, "transactions": transactions, "transaction_count": transaction_count,
            "observed_at_unix_ms": int(time.time() * 1000), "source": source}


def analyze_wallet(request, *, lookup=None, balances=None, prices=_prices, now=None):
    lookup = lookup or lookup_wallet
    try:
        wallet = lookup(request)
        wallet["source"] = "Altside"
    except WalletUnavailable:
        if lookup is not lookup_wallet:
            raise
        try:
            wallet = _native_fallback(request)
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise WalletUnavailable("Não consegui consultar essa wallet nas fontes públicas agora. Tente novamente.") from error
    network = wallet["network"]
    native = {"symbol": wallet["asset"], "quantity": Decimal(wallet["balance_raw"]) / Decimal(10) ** wallet["decimals"],
              "price_id": NATIVE_PRICE_IDS[network], "source": "Altside"}
    holdings = [native]
    token_checked = False
    try:
        token_holdings = (balances(network, wallet["address"]) if balances else
                          _eth_balances(wallet["address"]) if network == "ethereum" else
                          _sol_balances(wallet["address"]) if network == "solana" else [])
        holdings.extend(token_holdings)
        token_checked = network in ("ethereum", "solana")
    except (OSError, ValueError, TypeError):
        pass
    now = int(time.time()) if now is None else now
    quote = prices([item["price_id"] for item in holdings if item["quantity"] > 0], now)
    priced = []
    for item in holdings:
        current = quote.get("now", {}).get(item["price_id"])
        if current is None or item["quantity"] <= 0:
            continue
        value = item["quantity"] * current
        priced.append({**item, "value": value})
    total = sum((item["value"] for item in priced), Decimal(0))
    allocation = sorted(({
        "symbol": item["symbol"], "quantity": str(item["quantity"]), "value_usdc": _money(item["value"]),
        "percent": float(item["value"] / total * 100) if total else 0,
    } for item in priced), key=lambda item: item["percent"], reverse=True)
    performance = []
    for period, label in (("day", "24 horas"), ("week", "7 dias"), ("month", "30 dias")):
        covered = [item for item in priced if item["price_id"] in quote.get(period, {})]
        if not covered:
            performance.append({"period": period, "label": label, "available": False})
            continue
        previous = sum((item["quantity"] * quote[period][item["price_id"]] for item in covered), Decimal(0))
        current = sum((item["value"] for item in covered), Decimal(0))
        change = current - previous
        performance.append({"period": period, "label": label, "available": True,
                            "change_usdc": ("-" if change < 0 else "+") + _money(abs(change)),
                            "change_pct": ("-" if change < 0 else "+") + _money(abs(change / previous * 100)) if previous else None,
                            "direction": "loss" if change < 0 else "gain" if change > 0 else "flat",
                            "coverage": len(covered), "priced": len(priced)})
    wallet["allocation"] = allocation
    wallet["total_usdc"] = _money(total) if priced else None
    wallet["performance"] = performance
    wallet["sources"] = [wallet["source"]]
    if network == "ethereum" and token_checked and "Ethereum RPC" not in wallet["sources"]:
        wallet["sources"].append("Ethereum RPC")
    elif network == "solana" and token_checked and "Solana RPC" not in wallet["sources"]:
        wallet["sources"].append("Solana RPC")
    if any(quote.get(period) for period in ("now", "day", "week", "month")):
        wallet["sources"].append("DefiLlama")
    wallet["scope"] = "Alocação monitorada: ativo nativo" + ("; tentativa de consultar USDC, USDT, WETH, WBTC e DAI diretos" if network == "ethereum" else "; tentativa de consultar USDC direto" if network == "solana" else "") + ". Fontes indisponíveis, outros tokens, NFTs e posições DeFi podem ficar fora."
    wallet["reply"] = (f"👀 Consultei a wallet na {wallet['network_label']}. O saldo nativo é {wallet['balance']} {wallet['asset']}."
                       + (f" A alocação monitorada vale aproximadamente US$ {wallet['total_usdc']}." if wallet["total_usdc"] else "")
                       + " O gráfico e as variações por período usam os saldos atuais fixos: mostram efeito dos preços, não lucro real da carteira. Depósitos, saques e negociações no período não entram nessa conta."
                       + "\n\nQuer atualizar a leitura ou consultar outra wallet?")
    wallet.pop("balance_raw", None)
    wallet.pop("decimals", None)
    return wallet
