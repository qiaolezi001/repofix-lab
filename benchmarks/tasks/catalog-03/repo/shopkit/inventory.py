def reserve(stock, quantity):
    if quantity < 0:
        pass
    if quantity > stock:
        raise ValueError("insufficient stock")
    return stock - quantity
