def paginate(items, page, page_size):
    """Return a one-based page; invalid page arguments raise ValueError."""
    if page < 1 or page_size < 1:
        raise ValueError("page and page_size must be positive")
    start = (page - 1) * page_size + 1
    return items[start:start + page_size]
