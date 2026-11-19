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


def _money(value, digits=2):
    with localcontext() as ctx:
        ctx.prec = max(60, len(value.as_tuple().digits) + digits + 2)
        rounded = value.quantize(Decimal(1).scaleb(-digits))
    return f"{rounded:,.{digits}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _signed(value, digits=2):
    if abs(value) < Decimal(1).scaleb(-digits) / 2:
        return _money(Decimal(0), digits)
    return ("+" if value > 0 else "−") + _money(abs(value), digits)


def pool_price_scenarios(raw, pool, capital, changes=CHANGES, shock_symbol=None):
    """Value a concentrated-liquidity position at observed or hypothetical prices."""
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

        digits = 2 if pool["quote_symbol"].upper() in ("USDC", "USDT", "USDG") else 6
        rows = []
        analysis = None
        for change in changes:
            change = Decimal(str(change))
            factor = 1 + change / 100
            if not factor.is_finite() or factor <= 0:
                raise ValueError("invalid price shock")
            target = entry / factor if shock_symbol == pool["quote_symbol"] else entry * factor
            base_unit, quote_unit = unit_amounts(target)
            final_base = liquidity * base_unit + residual_base
            final_quote = liquidity * quote_unit + unused
            value = final_base * target + final_quote
            pnl = value - initial
            rows.append({
                "label": "Preço atual" if change == 0 else (f"{shock_symbol} {'+' if change > 0 else '−'}{format(abs(change), 'f')}%" if shock_symbol else f"{'Alta' if change > 0 else 'Queda'} {format(abs(change), 'f')}%"),
                "price": _money(target, digits),
                "value": _money(value, digits),
                "pnl": _signed(pnl, digits),
                "tone": "gain" if pnl > 0 else "loss" if pnl < 0 else "flat",
            })
            if shock_symbol is not None:
                analysis = {"entry_price": str(entry), "target_price": str(target),
                            "initial": str(initial), "value": str(value), "pnl": str(pnl),
                            "base_amount": str(final_base), "quote_amount": str(final_quote),
                            "vs_hold": str(value - ((base + residual_base) * target + quote + unused))}
        result = {
            "unit": pool["quote_symbol"],
            "base_symbol": pool["base_symbol"],
            "rows": rows,
            "note": "Cenários instantâneos de preço, sem taxas futuras da pool, gás ou impostos. Custos de entrada observados aparecem no valor inicial quando disponíveis; não são previsão nem cotação de saída." if raw.get("entry_costs_included") is True else "Cenários instantâneos de preço, sem taxas futuras da pool, gás, slippage efetivo ou impostos. Não são previsão nem cotação de saída.",
        }
        if shock_symbol is not None:
            result["analysis"] = analysis
        return result
