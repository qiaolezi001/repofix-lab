def discounted_price(price, percent):
    if price < 0 or not 0 <= percent <= 100:
        raise ValueError("price or percentage is invalid")
    return price * (1 - percent / 100)


def line_total(price, quantity):
    if price < 0 or quantity < 0:
        raise ValueError("price and quantity must not be negative")
    return price * quantity
