"""Reference-implementation measure policy: DECIMAL(38, 3), half-up rounding."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

import pandas as pd

SCALE = Decimal("0.001")
PRECISION = 38


def decimal_value(value, *, allow_missing=False):
    if value is None or pd.isna(value):
        if allow_missing:
            return None
        raise ValueError("OBS_VALUE must be a finite decimal, not missing.")
    try:
        with localcontext() as context:
            context.prec = 50
            result = Decimal(str(value))
            if not result.is_finite():
                raise ValueError("OBS_VALUE must be a finite decimal.")
            result = result.quantize(SCALE, rounding=ROUND_HALF_UP)
            if abs(result) >= Decimal(10) ** (PRECISION - 3):
                raise ValueError("OBS_VALUE exceeds DECIMAL(38,3).")
            return abs(result) if result == 0 else result
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"OBS_VALUE is not a valid DECIMAL(38,3): {value!r}.") from exc


def decimal_text(value):
    result = decimal_value(value, allow_missing=True)
    return "" if result is None else format(result, ".3f")


def decimal_sum(values):
    with localcontext() as context:
        context.prec = 50
        return sum(values, Decimal("0.000"))