"""Read-only market adapters for Fluid, Morpho Blue, and Kamino Lend."""

import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


FLUID_API = "https://api.fluid.instadapp.io"
MORPHO_API = "https://api.morpho.org"
KAMINO_API = "https://api.kamino.finance"
SOLANA_CHAIN_ID = 101
MORPHO_MARKETS = (
    (1, "0xb323495f7e4148be5643a4ea4a8221eef163e4bccfdedc2a6f4696baacbc86cc", "wstETH / USDC", "Ethereum"),
    (8453, "0x8793cf302b8ffd655ab97bd1c695dbd967807e8367a65cb2f4edaf1380ba1bda", "WETH / USDC", "Base"),
    (8453, "0x9103c3b4e834476c9a62ea009ba2c884ee42e94e6e314a26f04d312434191836", "cbBTC / USDC", "Base"),
)
_cache = {}


class ProviderError(Exception):
    pass


def _json(url):
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Alt-IA/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            raw = response.read(3_000_001)
        if len(raw) > 3_000_000:
            raise ProviderError("Resposta do mercado acima do limite.")
        return json.loads(raw)
    except (OSError, ValueError, TypeError) as error:
        raise ProviderError("Não foi possível consultar este protocolo agora.") from error


def _cached(key, ttl, fetch):
    old = _cache.get(key)
    if old and old[0] > time.monotonic():
        return old[1]
    value = fetch()
    _cache[key] = (time.monotonic() + ttl, value)
    return value


def _decimal(value, default="0"):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else Decimal(default)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fluid_vaults():
    return _cached("fluid_vaults", 300, lambda: _json(f"{FLUID_API}/v2/borrowing/1/vaults"))


def fluid_markets():
    ranked = []
    for vault in _fluid_vaults():
        if vault.get("type") != "1":
            continue  # Smart vaults hold DEX positions and need a different risk model.
        collateral = vault.get("supplyToken", {}).get("token0", {})
        loan = vault.get("borrowToken", {}).get("token0", {})
        if not collateral.get("symbol") or not loan.get("symbol") or not vault.get("address"):
            continue
        debt_usd = (_decimal(vault.get("totalBorrow")) / (10 ** int(loan.get("decimals", 18)))) * _decimal(loan.get("price"))
        if debt_usd < 100_000 or _decimal(vault.get("collateralFactor")) <= 0:
            continue
        ranked.append((debt_usd, {"name": f"Fluid · {collateral['symbol']} / {loan['symbol']} · Ethereum · #{vault['id']}",
                                  "address": vault["address"], "chain_id": 1, "chain": "Ethereum",
                                  "protocol": "fluid", "vault_id": vault["id"]}))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return [item for _, item in ranked[:20]]


def morpho_markets():
    return [{"name": f"Morpho · {pair} · {chain}", "address": market_id, "chain_id": chain_id,
             "chain": chain, "protocol": "morpho"} for chain_id, market_id, pair, chain in MORPHO_MARKETS]


def kamino_markets():
    def fetch():
        with ThreadPoolExecutor(max_workers=2) as pool:
            configs = pool.submit(_json, f"{KAMINO_API}/v2/kamino-market")
            pairs = pool.submit(_json, f"{KAMINO_API}/markets/collateral-reserves")
            return configs.result(), pairs.result()

    configs, pairs = _cached("kamino_catalog", 300, fetch)
    sizes = {}
    for pair in pairs.get("collateralReserves", []):
        if not pair.get("hidden"):
            key = pair.get("lendingMarket")
            sizes[key] = sizes.get(key, Decimal(0)) + _decimal(pair.get("sizeUsd"))
    ranked = []
    for item in configs:
        address = item.get("lendingMarket")
        if item.get("isVisibleInUi") and sizes.get(address, 0) > 100_000:
            name = item.get("description") or item.get("name") or "Mercado"
            ranked.append((sizes[address], {"name": f"Kamino · {name}", "address": address,
                                            "chain_id": SOLANA_CHAIN_ID, "chain": "Solana", "protocol": "kamino"}))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return [item for _, item in ranked[:25]]


def markets():
    result = []
    for discover in (fluid_markets, morpho_markets, kamino_markets):
        try:
            result.extend(discover())
        except (ProviderError, KeyError, TypeError, ValueError):
            continue
    return result


def _asset(symbol, name, address, price, supply_apy, borrow_apy, ltv, liquidation, *, can_supply, can_borrow,
           can_collateral, borrow_factor="1"):
    return {"symbol": symbol, "name": name, "address": address, "price": str(price),
            "supply_apy": str(supply_apy), "borrow_apy": str(borrow_apy), "ltv": str(ltv),
            "liquidation_threshold": str(liquidation), "borrow_factor": str(borrow_factor),
            "can_supply": can_supply, "can_borrow": can_borrow, "can_collateral": can_collateral}


def _fluid_market(selected):
    vault = _cached(("fluid", selected["vault_id"]), 60,
                    lambda: _json(f"{FLUID_API}/v2/borrowing/1/vaults/{selected['vault_id']}"))
    collateral = vault["supplyToken"]["token0"]
    loan = vault["borrowToken"]["token0"]
    if vault.get("type") != "1" or vault.get("address", "").lower() != selected["address"].lower():
        raise ProviderError("Vault da Fluid indisponível.")
    # Fluid reports APR in percent with 1e2 precision (163 = 1.63%).
    apy = lambda rate: (Decimal(1) + _decimal(rate) / Decimal(3_650_000)) ** 365 - 1
    ltv = _decimal(vault["collateralFactor"]) / 10_000
    threshold = _decimal(vault["liquidationThreshold"]) / 10_000
    assets = [
        _asset(collateral["symbol"], collateral.get("name") or collateral["symbol"], collateral["address"],
               collateral["price"], apy(vault["supplyRate"]["vault"]["rate"]), 0, ltv, threshold,
               can_supply=True, can_borrow=False, can_collateral=True),
        _asset(loan["symbol"], loan.get("name") or loan["symbol"], loan["address"], loan["price"],
               0, apy(vault["borrowRate"]["vault"]["rate"]), 0, 0,
               can_supply=False, can_borrow=True, can_collateral=False),
    ]
    return {**selected, "assets": assets, "updated_at": _timestamp(),
            "rate_note": "APY estimado a partir do APR atual da Fluid, sem incentivos externos.",
            "risk_note": "Vault isolado: uma garantia e uma dívida. Limites de liquidez e penalidade de liquidação não entram na conta.",
            "source_url": f"{FLUID_API}/v2/borrowing/1/vaults/{selected['vault_id']}"}


def _morpho_market(selected):
    selector = f"{selected['chain_id']}:{selected['address']}"
    root = _cached(("morpho_root", selector), 600,
                   lambda: _json(f"{MORPHO_API}/v0/blue/markets/{selector}")["data"])
    chain_id = selected["chain_id"]
    collateral_address, loan_address = root["collateral_token"], root["loan_token"]
    urls = [f"{MORPHO_API}/v0/blue/markets/{selector}/apy-averages"]
    for address in (collateral_address, loan_address):
        urls += [f"{MORPHO_API}/v0/tokens/{chain_id}:{address}", f"{MORPHO_API}/v0/tokens/{chain_id}:{address}/price"]
    def fetch_all():
        with ThreadPoolExecutor(max_workers=5) as pool:
            return list(pool.map(_json, urls))
    raw = _cached(("morpho_live", selector), 60, fetch_all)
    rates = raw[0]["data"]
    tokens = [(raw[1]["data"], raw[2]["data"]), (raw[3]["data"], raw[4]["data"])]
    lltv = _decimal(root["lltv_wad"]) / Decimal(10**18)
    collateral, loan = tokens
    assets = [
        _asset(collateral[0]["symbol"], collateral[0]["name"], collateral_address, collateral[1]["price"],
               0, 0, lltv, lltv, can_supply=True, can_borrow=False, can_collateral=True),
        _asset(loan[0]["symbol"], loan[0]["name"], loan_address, loan[1]["price"],
               rates["supply_apy_averages"]["24h"], rates["borrow_apy_averages"]["24h"], 0, 0,
               can_supply=True, can_borrow=True, can_collateral=False),
    ]
    return {**selected, "assets": assets, "updated_at": _timestamp(),
            "rate_note": "APYs médios das últimas 24 horas, sem recompensas. A garantia na Morpho Blue não rende juros.",
            "risk_note": "Mercado isolado. O LLTV é o limite de empréstimo e de liquidação do modelo.",
            "source_url": f"{MORPHO_API}/v0/blue/markets/{selector}"}


def _kamino_market(selected):
    address = selected["address"]
    def fetch():
        with ThreadPoolExecutor(max_workers=2) as pool:
            metrics = pool.submit(_json, f"{KAMINO_API}/kamino-market/{address}/reserves/metrics")
            stats = pool.submit(_json, f"{KAMINO_API}/reserves/batch/stats?market={address}")
            return metrics.result(), stats.result()
    metrics, stats = _cached(("kamino", address), 60, fetch)
    ranked_assets = []
    for row in metrics:
        reserve = row.get("reserve")
        detail = stats.get(reserve, {})
        if not detail or detail.get("status") != "Active":
            continue
        supply, supply_usd = _decimal(row.get("totalSupply")), _decimal(row.get("totalSupplyUsd"))
        debt, debt_usd = _decimal(row.get("totalBorrow")), _decimal(row.get("totalBorrowUsd"))
        price = supply_usd / supply if supply > 0 else debt_usd / debt if debt > 0 else Decimal(0)
        if price <= 0:
            continue
        price = price.quantize(Decimal("0.000000000001"))
        if price <= 0:
            continue
        ltv = _decimal(detail.get("maxLTV"))
        threshold = _decimal(detail.get("liqLTV"))
        ranked_assets.append((supply_usd, _asset(row["liquidityToken"], row["liquidityToken"], reserve, price,
                                                 max(Decimal(0), _decimal(row.get("supplyApy"))),
                                                 max(Decimal(0), _decimal(row.get("borrowApy"))), ltv, threshold,
                                                 can_supply=True, can_borrow=True, can_collateral=ltv > 0 and threshold > 0,
                                                 borrow_factor=max(Decimal(1), _decimal(detail.get("borrowFactor"), "1")))))
    assets = [item for _, item in sorted(ranked_assets, key=lambda row: row[0], reverse=True)]
    if not assets or not any(asset["can_collateral"] for asset in assets):
        raise ProviderError("Reservas deste mercado indisponíveis.")
    return {**selected, "assets": assets, "updated_at": _timestamp(),
            "rate_note": "APYs base atuais da Kamino, sem incentivos nem rendimento próprio do token.",
            "risk_note": "Cálculo com LTV, limiar e fator de empréstimo padrão das reservas. Grupos de elevação e limites por par não entram na conta.",
            "source_url": f"{KAMINO_API}/kamino-market/{address}/reserves/metrics"}


def market(selected):
    return {"fluid": _fluid_market, "morpho": _morpho_market, "kamino": _kamino_market}[selected["protocol"]](selected)
