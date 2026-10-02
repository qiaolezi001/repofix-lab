from .tokens import tokens


def count_token(text, token):
    return tokens(text).count(token.lower())
