def reserve(stock, quantity):
    if quantity < 0:
        raise ValueError("quantity must not be negative")
    if quantity > stock:
        raise ValueError("insufficient stock")
    return stock - quantity
