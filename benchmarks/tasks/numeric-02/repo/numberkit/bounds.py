def clamp(value, low, high):
    if low > high:
        raise ValueError("low must be <= high")
    return min(high, max(low, value))


def normalize(values):
    values = list(values)
    if not values:
        return []
    low, high = min(values), max(values)
    if low == high:
        return [0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]
