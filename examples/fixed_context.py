def clamp(value: int, lower: int, upper: int) -> int:
    """Return *value* constrained to the inclusive interval."""
    if lower > upper:
        raise ValueError("lower must not exceed upper")
    return max(lower, min(value, upper))
