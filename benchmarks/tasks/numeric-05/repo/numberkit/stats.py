from .weights import total_weight


def mean(values):
    values = list(values)
    if not values:
        raise ValueError("mean requires at least one value")
    return sum(values) / len(values)


def weighted_mean(values, weights):
    values, weights = list(values), list(weights)
    if len(values) != len(weights) or not values:
        raise ValueError("values and weights must have equal nonzero length")
    total = total_weight(weights)
    if total == 0:
        raise ValueError("total weight must not be zero")
    return sum(value * weight for value, weight in zip(values, weights)) / total
