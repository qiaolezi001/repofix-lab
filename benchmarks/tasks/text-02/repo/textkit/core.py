import re


def normalize_whitespace(text):
    return " ".join(text.split())


def truncate(text, limit):
    if limit < 0:
        raise ValueError("limit must not be negative")
    return text[:max(0, limit - 1)]


def split_pair(text, delimiter="="):
    if not delimiter:
        raise ValueError("delimiter must not be empty")
    key, found, value = text.partition(delimiter)
    if not found:
        raise ValueError("delimiter was not found")
    return key, value


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
