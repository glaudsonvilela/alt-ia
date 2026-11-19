"""Illustrative CLMM replay over historical pool candles supplied by Altside.

This models principal at historical close prices. It cannot reconstruct historical
swap execution, liquidity depth, accrued fees, gas, taxes, or intra-candle events.
"""

import math
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext


PERIOD_INTERVAL = {7: ("1h", 3600), 30: ("4h", 14400), 90: ("1d", 86400)}


def _money(value):
    return f"{value.quantize(Decimal('0.01')):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _signed(value):
    if abs(value) < Decimal("0.005"):
        return "0,00"
    return ("+" if value > 0 else "−") + _money(abs(value))


def _positive(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("invalid historical price") from None
    if not number.is_finite() or number <= 0:
        raise ValueError("invalid historical price")
    return number


def replay_pool_history(chart, pool, capital, range_ticks, period_days):
    """Replay a centered, static CLMM range over actual historical close prices."""
    if period_days not in PERIOD_INTERVAL or type(range_ticks) is not int or range_ticks < pool["tick_spacing"] * 2 or range_ticks > 50000:
        raise ValueError("invalid historical request")
    interval, step_seconds = PERIOD_INTERVAL[period_days]
    if chart.get("interval") != interval or chart.get("pool_id") != pool["id"] or chart.get("source") != "GeckoTerminal via Altside":
        raise ValueError("invalid historical source")
    candles = chart.get("candles") or []
    if len(candles) < 25:
        raise ValueError("insufficient historical candles")
    end_time = candles[-1]["time"]
    cutoff = end_time - period_days * 86400
    selected = [c for c in candles if c["time"] >= cutoff]
    if len(selected) < 25 or selected[0]["time"] > cutoff + step_seconds * 2:
        raise ValueError("insufficient historical coverage")

    with localcontext() as ctx:
        ctx.prec = 60
        initial = _positive(capital)
        entry = _positive(selected[0]["close"])
        scale = Decimal(10) ** (pool["token0_decimals"] - pool["token1_decimals"])
        base_is_token0 = pool["base_is_token0"]
        spacing = pool["tick_spacing"]
        native = entry if base_is_token0 else 1 / entry
        approximate_tick = math.log(float(native / scale)) / math.log(1.0001)
        if not math.isfinite(approximate_tick):
            raise ValueError("historical tick unavailable")
        lower_tick = math.floor((approximate_tick - range_ticks / 2) / spacing) * spacing
        upper_tick = math.ceil((approximate_tick + range_ticks / 2) / spacing) * spacing
        if not -887272 <= lower_tick < upper_tick <= 887272:
            raise ValueError("historical range out of bounds")

        def tick_price(tick):
            native_price = Decimal("1.0001") ** tick * scale
            return native_price if base_is_token0 else 1 / native_price

        low, high = sorted((tick_price(lower_tick), tick_price(upper_tick)))
        sqrt_low, sqrt_high = low.sqrt(), high.sqrt()

        def unit_amounts(price):
            root = min(sqrt_high, max(sqrt_low, price.sqrt()))
            return (sqrt_high - root) / (root * sqrt_high), root - sqrt_low

        base_unit, quote_unit = unit_amounts(entry)
        denominator = base_unit * entry + quote_unit
        if denominator <= 0 or not low < entry < high:
            raise ValueError("historical entry outside range")
        liquidity = initial / denominator
        held_base, held_quote = liquidity * base_unit, liquidity * quote_unit

        def at(candle):
            price = _positive(candle["close"])
            base_amount, quote_amount = unit_amounts(price)
            value = liquidity * (base_amount * price + quote_amount)
            return price, value, value - initial

        indexes = sorted({round((len(selected) - 1) * fraction / 4) for fraction in range(5)})
        rows = []
        for index in indexes:
            candle = selected[index]
            price, value, pnl = at(candle)
            label = datetime.fromtimestamp(candle["time"], timezone.utc).strftime("%d/%m/%y")
            rows.append({"label": label, "price": _money(price), "value": _money(value), "pnl": _signed(pnl),
                         "tone": "gain" if pnl > Decimal("0.005") else "loss" if pnl < Decimal("-0.005") else "flat"})
        final_price, final_value, final_pnl = at(selected[-1])
        hold_value = held_base * final_price + held_quote
        start_date = datetime.fromtimestamp(selected[0]["time"], timezone.utc).strftime("%d/%m/%Y")
        end_date = datetime.fromtimestamp(end_time, timezone.utc).strftime("%d/%m/%Y")
        return {
            "kind": "historical_pool", "title": f"Histórico {pool['pair']} · {period_days} dias",
            "subtitle": f"{pool['network']} · {pool['protocol']} · {start_date} a {end_date}",
            "metrics": [
                {"label": "Capital inicial", "value": f"{_money(initial)} {pool['quote_symbol']}"},
                {"label": "Preço inicial", "value": f"{_money(entry)} {pool['quote_symbol']}"},
                {"label": "Preço final", "value": f"{_money(final_price)} {pool['quote_symbol']}"},
                {"label": "Valor final", "value": f"{_money(final_value)} {pool['quote_symbol']}"},
                {"label": "Ganho/perda", "value": f"{_signed(final_pnl)} {pool['quote_symbol']}"},
                {"label": "Vs. manter tokens", "value": f"{_signed(final_value - hold_value)} {pool['quote_symbol']}"},
            ],
            "scenarios": {
                "caption": f"📊 Preços históricos · valores em {pool['quote_symbol']}",
                "unit": pool["quote_symbol"], "base_symbol": pool["base_symbol"], "rows": rows,
                "note": "Reconstituição ilustrativa com preços de fechamento. Não inclui taxas recebidas, swap de entrada, gas, slippage, impostos ou movimentos dentro das velas.",
            },
            "source": {
                "kind": "historical_candles", "period_start": selected[0]["time"], "period_end": end_time,
                "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "validity": "Velas históricas GeckoTerminal via Altside" + (" · cache histórico" if chart.get("stale") else ""),
            },
            "assumptions": [f"Faixa fixa centrada no primeiro preço: {lower_tick} a {upper_tick} ticks", "Capital convertido em base/quote ao preço inicial; sem execução real."],
            "url": "https://app.bigbanana.io/",
        }
