from __future__ import annotations

from decimal import Decimal, InvalidOperation

MAX_TRANSACTION_RUPEES = Decimal("10000000")  # ₹1 crore per transaction


def rupees_to_paise(value) -> int:
    """
    Strictly converts a rupee amount to integer paise.

    "100"    -> 10000
    "100.50" -> 10050
    "1,000"  -> 100000
    Rejects: zero, negatives, NaN/Infinity, more than 2 decimals, huge values.
    """
    try:
        amount = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid monetary amount")

    if not amount.is_finite():
        raise ValueError("Invalid monetary amount")
    if amount <= 0:
        raise ValueError("Amount must be greater than zero")
    if amount > MAX_TRANSACTION_RUPEES:
        raise ValueError("Amount exceeds the per-transaction limit")
    if amount != amount.quantize(Decimal("0.01")):
        raise ValueError("Amount cannot have more than two decimal places")

    return int(amount * 100)


def format_paise(paise: int) -> str:
    sign = "-" if paise < 0 else ""
    paise = abs(int(paise))
    return f"{sign}₹{paise // 100:,}.{paise % 100:02d}"
