"""Read-only, bounded lookup of a public blockchain address via Altside."""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from datetime import datetime


NETWORKS = {"bitcoin": "Bitcoin", "ethereum": "Ethereum", "solana": "Solana"}
ASSETS = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL"}
BASE_URL = "https://app.bigbanana.io"


class WalletInputError(ValueError):
    pass


class WalletUnavailable(Exception):
    pass


def validate_request(value):
    if not isinstance(value, dict) or set(value) != {"network", "address"}:
        raise WalletInputError("Informe a rede e o endereço da wallet.")
    network, address = value.get("network"), value.get("address")
    if network not in NETWORKS or not isinstance(address, str):
        raise WalletInputError("Escolha Bitcoin, Ethereum ou Solana e informe o endereço.")
    address = address.strip()
    if network == "ethereum":
        valid = bool(re.fullmatch(r"0x[0-9a-fA-F]{40}", address))
    elif network == "bitcoin":
        valid = bool(re.fullmatch(r"[13][1-9A-HJ-NP-Za-km-z]{25,34}|bc1[023456789acdefghjklmnpqrstuvwxyz]{11,87}", address))
    else:
        valid = bool(re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", address))
    if not valid:
        raise WalletInputError(f"Esse endereço não parece válido para {NETWORKS[network]}.")
    return {"network": network, "address": address}


def parse_wallet_text(text):
    if not isinstance(text, str) or not re.search(r"\b(?:wallet|carteira|endere[cç]o|rastre\w*)\b", text, re.I):
        return None
    match = re.search(r"(?<![A-Za-z0-9])(?:0x[0-9a-fA-F]{40}|bc1[023456789acdefghjklmnpqrstuvwxyz]{11,87}|[1-9A-HJ-NP-Za-km-z]{26,44})(?![A-Za-z0-9])", text)
    if not match:
        return None
    address = match.group(0)
    if address.startswith("0x"):
        network = "ethereum"
    elif address.startswith("bc1"):
        network = "bitcoin"
    elif re.search(r"\bsolana\b", text, re.I):
        network = "solana"
    elif re.search(r"\bbitcoin|\bbtc\b", text, re.I):
        network = "bitcoin"
    elif len(address) > 35:
        network = "solana"
    elif address.startswith(("1", "3")):
        network = "bitcoin"
    else:
        network = "solana"
    try:
        return validate_request({"network": network, "address": address})
    except WalletInputError:
        return None


def _number(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def _format(value, places=6):
    return f"{value:,.{places}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def lookup_wallet(request, *, base_url=BASE_URL, attempts=8, pause=time.sleep, open_url=urllib.request.urlopen):
    request = validate_request(request)
    network, address = request["network"], request["address"]
    query = urllib.parse.urlencode(request)
    url = f"{base_url.rstrip('/')}/public-wallets/lookup?{query}"
    for attempt in range(attempts):
        try:
            with open_url(urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Alt-IA/1.0 (read-only wallet research)"}), timeout=7) as response:
                data = json.load(response)
                status = response.status
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            raise WalletUnavailable("Não consegui consultar essa wallet no Altside agora. Tente novamente.") from error
        if status == 202 and data.get("status") == "loading":
            if attempt < attempts - 1:
                pause(1)
                continue
            raise WalletUnavailable("A consulta da wallet ainda está em andamento. Tente novamente em instantes.")
        wallet = data.get("wallet") if isinstance(data, dict) else None
        if status != 200 or data.get("schema") != "altside_wallet_address_lookup_v1" or data.get("status") != "live" or not isinstance(wallet, dict):
            raise WalletUnavailable("Não consegui consultar essa wallet no Altside agora. Tente novamente.")
        if wallet.get("network") != network or wallet.get("address", "").lower() != address.lower() or wallet.get("asset") != ASSETS[network]:
            raise WalletUnavailable("O Altside retornou dados incompatíveis com o endereço pedido.")
        raw = wallet.get("balance_raw")
        decimals = wallet.get("decimals")
        if not isinstance(raw, str) or not raw.isdigit() or not isinstance(decimals, int) or not 0 <= decimals <= 18:
            raise WalletUnavailable("O saldo da wallet veio em um formato inesperado.")
        balance = Decimal(raw) / Decimal(10) ** decimals
        value_usdc = _number(wallet.get("value_usdc"))
        transactions = []
        for item in (wallet.get("transactions") or [])[:2]:
            if not isinstance(item, dict) or not isinstance(item.get("txid"), str):
                continue
            direction = item.get("direction")
            amount = _number(item.get("net_base_units"))
            if direction not in ("received", "sent", "self_or_other") or amount is None:
                continue
            block_time = item.get("block_time_unix")
            if not isinstance(block_time, int) and isinstance(item.get("block_time_iso"), str):
                try:
                    block_time = int(datetime.fromisoformat(item["block_time_iso"].replace("Z", "+00:00")).timestamp())
                except ValueError:
                    block_time = None
            transactions.append({
                "txid": item["txid"][:120], "direction": direction,
                "amount": _format(abs(amount) / Decimal(10) ** decimals, 8) if direction != "self_or_other" else None,
                "block_time_unix": block_time if isinstance(block_time, int) else None,
                "confirmed": item.get("confirmed") is True,
            })
        result = {
            "network": network, "network_label": NETWORKS[network], "address": address,
            "asset": ASSETS[network], "balance": _format(balance, 6),
            "balance_raw": raw, "decimals": decimals,
            "value_usdc": _format(value_usdc, 2) if value_usdc is not None else None,
            "observed_at_unix_ms": wallet.get("observed_at_unix_ms") if isinstance(wallet.get("observed_at_unix_ms"), int) else None,
            "transaction_count": wallet.get("transaction_count") if isinstance(wallet.get("transaction_count"), int) else None,
            "transactions": transactions,
            "evidence_url": wallet.get("evidence_url") if isinstance(wallet.get("evidence_url"), str) else "",
        }
        result["reply"] = (f"👀 Consultei esse endereço na {NETWORKS[network]}. O saldo nativo é {_format(balance, 6)} {ASSETS[network]}."
                           + (f" A referência de valor é US$ {_format(value_usdc, 2)}." if value_usdc is not None else "")
                           + " Abaixo estão as movimentações recentes disponíveis. Isso é uma consulta pontual do endereço, não um monitoramento contínuo nem o patrimônio total."
                           + "\n\nQuer consultar outra wallet ou atualizar esta?")
        return result
    raise WalletUnavailable("A consulta da wallet não terminou. Tente novamente.")
