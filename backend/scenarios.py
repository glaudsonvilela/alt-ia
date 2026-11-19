"""Illustrative CLMM price sensitivities anchored to a canonical Altside entry quote.

Continuous Uniswap v3 liquidity math; these are hypothetical principal values,
not on-chain exit quotes or forecasts. Future fees, gas and execution costs are excluded.
"""

from decimal import Decimal, InvalidOperation, localcontext


CHANGES = (-20, -10, 0, 10, 20)


def _positive(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("invalid scenario input") from None
    if not number.is_finite() or number <= 0:
        raise ValueError("invalid scenario input")
    return number


def _money(value):
    rounded = value.quantize(Decimal("0.01"))
    return f"{rounded:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _signed(value):
    if abs(value) < Decimal("0.005"):
        return "0,00"
    return ("+" if value > 0 else "−") + _money(abs(value))


def pool_price_scenarios(raw, pool, capital):
    """Return five price-shock rows in the pool's quote token, or reject bad data."""
    allocation = (raw.get("allocation") or {}).get("formatted") or {}
    price_data = raw.get("price") or {}
    descriptor = raw.get("position_descriptor") or {}
    range_data = raw.get("range") or {}
    with localcontext() as ctx:
        ctx.prec = 60
        initial = _positive(capital)
        base = Decimal(str(allocation["base_required"]))
        quote = Decimal(str(allocation["quote_required"]))
        unused = Decimal(str(allocation["unused_quote"]))
        residual_base = Decimal(str(raw.get("residual_base", "0")))
        if any(not value.is_finite() or value < 0 for value in (base, quote, unused, residual_base)):
            raise ValueError("invalid allocation")
        tick_lower = range_data["tick_lower"]
        tick_upper = range_data["tick_upper"]
        if type(tick_lower) is not int or type(tick_upper) is not int or not -887272 <= tick_lower < tick_upper <= 887272:
            raise ValueError("invalid range")
        decimals0 = pool["token0_decimals"]
        decimals1 = pool["token1_decimals"]
        if not 0 <= decimals0 <= 36 or not 0 <= decimals1 <= 36:
            raise ValueError("invalid token decimals")
        scale = Decimal(10) ** (decimals0 - decimals1)
        base_is_token0 = pool["base_is_token0"]
        if type(base_is_token0) is not bool:
            raise ValueError("invalid token order")

        def tick_price(tick):
            native = Decimal("1.0001") ** tick * scale
            return native if base_is_token0 else 1 / native

        low, high = sorted((tick_price(tick_lower), tick_price(tick_upper)))
        if descriptor.get("entry_sqrt_price_x96"):
            sqrt_price = _positive(descriptor["entry_sqrt_price_x96"]) / Decimal(2**96)
            native_price = sqrt_price * sqrt_price * scale
            entry = native_price if base_is_token0 else 1 / native_price
        else:
            entry = _positive(price_data["quote_per_base"])
        if not low < high or not entry.is_finite() or entry <= 0:
            raise ValueError("invalid price")

        sqrt_low, sqrt_high = low.sqrt(), high.sqrt()

        def unit_amounts(price):
            root = min(sqrt_high, max(sqrt_low, price.sqrt()))
            return (sqrt_high - root) / (root * sqrt_high), root - sqrt_low

        base_unit, quote_unit = unit_amounts(entry)
        used = base * entry + quote
        divisor = base_unit * entry + quote_unit
        if used <= 0 or divisor <= 0:
            raise ValueError("invalid position")
        liquidity = used / divisor
        # The canonical allocation should reconcile with the displayed capital.
        difference = initial - (used + unused + residual_base * entry)
        tolerance = max(Decimal("0.02"), initial * Decimal("0.001"))
        if raw.get("entry_costs_included") is True:
            if difference < -max(Decimal("0.02"), initial * Decimal("0.02")) or difference > initial * Decimal("0.10"):
                raise ValueError("allocation does not reconcile")
        elif abs(difference) > tolerance:
            raise ValueError("allocation does not reconcile")

        rows = []
        for change in CHANGES:
            target = entry * (Decimal(100 + change) / 100)
            base_unit, quote_unit = unit_amounts(target)
            value = liquidity * (base_unit * target + quote_unit) + unused + residual_base * target
            pnl = value - initial
            rows.append({
                "label": "Preço atual" if change == 0 else f"{'Alta' if change > 0 else 'Queda'} {abs(change)}%",
                "price": _money(target),
                "value": _money(value),
                "pnl": _signed(pnl),
                "tone": "gain" if pnl > Decimal("0.005") else "loss" if pnl < Decimal("-0.005") else "flat",
            })
        return {
            "unit": pool["quote_symbol"],
            "base_symbol": pool["base_symbol"],
            "rows": rows,
            "note": "Cenários instantâneos de preço, sem taxas futuras da pool, gás ou impostos. Custos de entrada observados aparecem no valor inicial quando disponíveis; não são previsão nem cotação de saída." if raw.get("entry_costs_included") is True else "Cenários instantâneos de preço, sem taxas futuras da pool, gás, slippage efetivo ou impostos. Não são previsão nem cotação de saída.",
        }
