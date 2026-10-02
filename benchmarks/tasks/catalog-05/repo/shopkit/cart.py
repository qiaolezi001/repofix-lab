from .money import line_total


def subtotal(items):
    return sum(line_total(item["price"], item["quantity"]) for item in items) / len(items)
