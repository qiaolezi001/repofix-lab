"""Regenerate the MIT-licensed, self-authored synthetic v0.1 fixture set.

Never run this against a benchmark release being used for a live measurement.
All bugs and acceptance tests here were authored for engineering evaluation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parent


def clean(text: str) -> str:
    return dedent(text).lstrip("\n")


PROJECTS = {
    "numeric": {
        "numberkit/__init__.py": "",
        "numberkit/bounds.py": clean("""
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
        """),
        "numberkit/stats.py": clean("""
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
        """),
        "numberkit/weights.py": clean("""
            def total_weight(weights):
                return sum(weights)
        """),
    },
    "text": {
        "textkit/__init__.py": "",
        "textkit/core.py": clean("""
            import re


            def normalize_whitespace(text):
                return " ".join(text.split())


            def truncate(text, limit):
                if limit < 0:
                    raise ValueError("limit must not be negative")
                return text[:limit]


            def split_pair(text, delimiter="="):
                if not delimiter:
                    raise ValueError("delimiter must not be empty")
                key, found, value = text.partition(delimiter)
                if not found:
                    raise ValueError("delimiter was not found")
                return key, value


            def slugify(text):
                return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
        """),
        "textkit/tokens.py": clean("""
            import re


            def tokens(text):
                return re.findall(r"[a-z0-9]+", text.lower())
        """),
        "textkit/matching.py": clean("""
            from .tokens import tokens


            def count_token(text, token):
                return tokens(text).count(token.lower())
        """),
    },
    "catalog": {
        "shopkit/__init__.py": "",
        "shopkit/money.py": clean("""
            def discounted_price(price, percent):
                if price < 0 or not 0 <= percent <= 100:
                    raise ValueError("price or percentage is invalid")
                return price * (1 - percent / 100)


            def line_total(price, quantity):
                if price < 0 or quantity < 0:
                    raise ValueError("price and quantity must not be negative")
                return price * quantity
        """),
        "shopkit/cart.py": clean("""
            from .money import line_total


            def subtotal(items):
                return sum(line_total(item["price"], item["quantity"]) for item in items)
        """),
        "shopkit/inventory.py": clean("""
            def reserve(stock, quantity):
                if quantity < 0:
                    raise ValueError("quantity must not be negative")
                if quantity > stock:
                    raise ValueError("insufficient stock")
                return stock - quantity
        """),
        "shopkit/paging.py": clean("""
            def paginate(items, page, page_size):
                if page < 1 or page_size < 1:
                    raise ValueError("page and page_size must be positive")
                start = (page - 1) * page_size
                return items[start:start + page_size]
        """),
    },
}

# Every tuple: project, bug id, split, category, path, correct fragment,
# injected fragment, issue, public assertions, independent assertions.
TASKS = [
    (
        "numeric",
        "01",
        "dev",
        "boundary",
        "numberkit/bounds.py",
        "return min(high, max(low, value))",
        "return max(high, max(low, value))",
        "clamp(4, 0, 10) returns 10. Clamp should preserve an in-range value and cap both bounds.",
        "assert clamp(4, 0, 10) == 4\nassert clamp(-1, 0, 10) == 0",
        "assert clamp(11, 0, 10) == 10\nassert clamp(-4, -3, -1) == -3\nassert clamp(5, 5, 5) == 5",
    ),
    (
        "numeric",
        "02",
        "dev",
        "arithmetic",
        "numberkit/stats.py",
        "return sum(values) / len(values)",
        "return sum(values) / (len(values) - 1)",
        "mean([2, 4]) returns 6 instead of 3. Arithmetic mean must support one value and iterables.",
        "assert mean([2, 4]) == 3",
        "assert mean([7]) == 7\nassert mean(iter([1, 2, 3])) == 2\nassert mean([-2, 2]) == 0",
    ),
    (
        "numeric",
        "03",
        "eval",
        "exception",
        "numberkit/stats.py",
        'if not values:\n        raise ValueError("mean requires at least one value")',
        "if not values:\n        pass",
        "mean([]) raises ZeroDivisionError. Its public contract requires ValueError for empty input.",
        "with pytest.raises(ValueError):\n    mean([])",
        "with pytest.raises(ValueError):\n    mean(iter([]))\nassert mean([0]) == 0",
    ),
    (
        "numeric",
        "04",
        "eval",
        "cross_file",
        "numberkit/weights.py",
        "return sum(weights)",
        "return len(weights)",
        "weighted_mean([10, 20], [1, 3]) returns 35. Investigate the weighting helper and normalization.",
        "assert weighted_mean([10, 20], [1, 3]) == 17.5",
        "assert weighted_mean([2, 8], [2, 2]) == 5\nassert weighted_mean([3], [0.5]) == 3\nwith pytest.raises(ValueError):\n    weighted_mean([1, 2], [0, 0])",
    ),
    (
        "numeric",
        "05",
        "eval",
        "edge_case",
        "numberkit/bounds.py",
        "if low == high:\n        return [0.0 for _ in values]",
        "if low == high:\n        pass",
        "normalize([5, 5]) crashes. A constant series should normalize to zeros; empty input remains empty.",
        "assert normalize([5, 5]) == [0.0, 0.0]",
        "assert normalize([9]) == [0.0]\nassert normalize([]) == []\nassert normalize([2, 4, 6]) == [0.0, 0.5, 1.0]",
    ),
    (
        "text",
        "01",
        "dev",
        "boundary",
        "textkit/core.py",
        'return " ".join(text.split())',
        'return " ".join(text.split(" "))',
        "normalize_whitespace preserves tabs and repeated spaces. Collapse all whitespace to a single space.",
        'assert normalize_whitespace("  a\\tb  ") == "a b"',
        'assert normalize_whitespace("a\\nb\\r\\nc") == "a b c"\nassert normalize_whitespace(" \\t") == ""\nassert normalize_whitespace("x") == "x"',
    ),
    (
        "text",
        "02",
        "dev",
        "boundary",
        "textkit/core.py",
        "return text[:limit]",
        "return text[:max(0, limit - 1)]",
        "truncate('hello', 3) returns 'he'. Limit means the maximum number of characters retained.",
        'assert truncate("hello", 3) == "hel"',
        'assert truncate("hello", 0) == ""\nassert truncate("hello", 8) == "hello"\nassert truncate("你好世界", 2) == "你好"\nwith pytest.raises(ValueError):\n    truncate("x", -1)',
    ),
    (
        "text",
        "03",
        "eval",
        "exception",
        "textkit/core.py",
        'if not found:\n        raise ValueError("delimiter was not found")',
        'if not found:\n        return key, ""',
        "split_pair('key') silently returns ('key', ''). Missing delimiter must raise ValueError.",
        'with pytest.raises(ValueError):\n    split_pair("key")',
        'assert split_pair("a=b=c") == ("a", "b=c")\nassert split_pair("a=") == ("a", "")\nwith pytest.raises(ValueError):\n    split_pair("missing", ":")',
    ),
    (
        "text",
        "04",
        "eval",
        "cross_file",
        "textkit/tokens.py",
        'return re.findall(r"[a-z0-9]+", text.lower())',
        'return re.findall(r"[a-z0-9]+", text)',
        "count_token('Hello HELLO hello', 'hello') returns 1. Counting should be case-insensitive.",
        'assert count_token("Hello HELLO hello", "hello") == 3',
        'assert count_token("ONE, one! OnE", "ONE") == 3\nassert count_token("cat scatter CAT", "cat") == 2\nassert count_token("", "x") == 0',
    ),
    (
        "text",
        "05",
        "eval",
        "edge_case",
        "textkit/core.py",
        'return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")',
        'return re.sub(r"[^a-z0-9]", "-", text.lower()).strip("-")',
        "slugify('Hello,  World!') creates repeated hyphens. Runs of separators should become one hyphen.",
        'assert slugify("Hello,  World!") == "hello-world"',
        'assert slugify("--A___B--") == "a-b"\nassert slugify("!!!") == ""\nassert slugify("abc123") == "abc123"',
    ),
    (
        "catalog",
        "01",
        "dev",
        "arithmetic",
        "shopkit/money.py",
        "return price * (1 - percent / 100)",
        "return price * (1 - percent / 10)",
        "discounted_price(100, 20) produces a negative price. Percent is represented in the range 0..100.",
        "assert discounted_price(100, 20) == 80",
        "assert discounted_price(10, 0) == 10\nassert discounted_price(10, 100) == 0\nwith pytest.raises(ValueError):\n    discounted_price(10, 101)",
    ),
    (
        "catalog",
        "02",
        "dev",
        "cross_file",
        "shopkit/money.py",
        "return price * quantity",
        "return price + quantity",
        "subtotal([{'price': 3, 'quantity': 4}]) returns 7 instead of 12. Review cart line calculation.",
        'assert subtotal([{"price": 3, "quantity": 4}]) == 12',
        'assert subtotal([{"price": 2.5, "quantity": 2}, {"price": 4, "quantity": 0}]) == 5\nassert subtotal([]) == 0\nwith pytest.raises(ValueError):\n    subtotal([{"price": 3, "quantity": -1}])',
    ),
    (
        "catalog",
        "03",
        "eval",
        "exception",
        "shopkit/inventory.py",
        'if quantity < 0:\n        raise ValueError("quantity must not be negative")',
        "if quantity < 0:\n        pass",
        "reserve(10, -2) increases stock. Invalid negative reservation quantities must raise ValueError.",
        "with pytest.raises(ValueError):\n    reserve(10, -2)",
        "assert reserve(3, 0) == 3\nassert reserve(3, 3) == 0\nwith pytest.raises(ValueError):\n    reserve(3, 4)\nwith pytest.raises(ValueError):\n    reserve(0, -1)",
    ),
    (
        "catalog",
        "04",
        "eval",
        "boundary",
        "shopkit/paging.py",
        "start = (page - 1) * page_size",
        "start = (page - 1) * page_size + 1",
        "paginate([0,1,2,3,4], 1, 2) drops the first item. Pages are one-based and must not overlap.",
        "assert paginate([0, 1, 2, 3, 4], 1, 2) == [0, 1]",
        "assert paginate([0, 1, 2, 3, 4], 2, 2) == [2, 3]\nassert paginate([0, 1, 2, 3, 4], 3, 2) == [4]\nassert paginate([], 1, 2) == []\nwith pytest.raises(ValueError):\n    paginate([1], 0, 2)",
    ),
    (
        "catalog",
        "05",
        "eval",
        "edge_case",
        "shopkit/cart.py",
        'return sum(line_total(item["price"], item["quantity"]) for item in items)',
        'return sum(line_total(item["price"], item["quantity"]) for item in items) / len(items)',
        "subtotal([]) raises ZeroDivisionError and multi-line carts return an average. Subtotal means sum.",
        "assert subtotal([]) == 0",
        'assert subtotal([{"price": 2, "quantity": 3}, {"price": 4, "quantity": 1}]) == 10\nassert subtotal(iter([{"price": 2, "quantity": 3}])) == 6',
    ),
]

IMPORTS = {
    "numeric": "from numberkit.bounds import clamp, normalize\nfrom numberkit.stats import mean, weighted_mean\n",
    "text": "from textkit.core import normalize_whitespace, truncate, split_pair, slugify\nfrom textkit.matching import count_token\n",
    "catalog": "from shopkit.money import discounted_price\nfrom shopkit.cart import subtotal\nfrom shopkit.inventory import reserve\nfrom shopkit.paging import paginate\n",
}

REGRESSION = {
    "numeric": "assert clamp(10, 0, 10) == 10\nassert normalize([0, 10]) == [0, 1]\nwith pytest.raises(ValueError):\n    weighted_mean([1], [1, 2])",
    "text": 'assert normalize_whitespace("hello") == "hello"\nassert split_pair("x=y") == ("x", "y")\nassert slugify("abc") == "abc"',
    "catalog": "assert reserve(10, 2) == 8\nwith pytest.raises(ValueError):\n    discounted_price(-1, 5)\nwith pytest.raises(ValueError):\n    paginate([1], 1, 0)",
}


def test_module(project: str, assertions: str, regression: str | None = None) -> str:
    result = "import pytest\n" + IMPORTS[project] + "\n\ndef test_contract():\n"
    result += "\n".join("    " + line for line in assertions.splitlines()) + "\n"
    if regression:
        result += "\n\ndef test_regressions():\n"
        result += "\n".join("    " + line for line in regression.splitlines()) + "\n"
    return result


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def sha(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def generate() -> None:
    manifest = []
    for project, number, split, category, path, good, bad, issue, public, hidden in TASKS:
        task_id = f"{project}-{number}"
        task = ROOT / "tasks" / task_id
        source_hashes = {}
        for relative, content in PROJECTS[project].items():
            if relative == path:
                assert content.count(good) == 1, (task_id, good)
                content = content.replace(good, bad, 1)
            write(task / "repo" / relative, content)
            source_hashes[relative] = sha(content)
        public_text = test_module(project, public, REGRESSION[project])
        write(task / "repo" / "tests" / "test_public.py", public_text)
        source_hashes["tests/test_public.py"] = sha(public_text)
        readme = f"# {project} fixture\n\nSynthetic MIT-licensed RepoFix-Lab fixture.\nRun `python -m pytest tests`.\n"
        write(task / "repo" / "README.md", readme)
        source_hashes["README.md"] = sha(readme)
        initial_version = sha(json.dumps(source_hashes, sort_keys=True))
        acceptance_text = test_module(project, hidden)
        issue_text = issue + "\n"
        metadata = {
            "id": task_id,
            "project": project,
            "split": split,
            "category": category,
            "provenance": "self-authored; one artificially injected bug; MIT",
            "initial_version": initial_version,
            "source_sha256": source_hashes,
            "public_tests": "tests",
            "hidden_tests": "hidden/test_acceptance.py",
            "issue_sha256": sha(issue_text),
            "acceptance_sha256": sha(acceptance_text),
        }
        write(task / "issue.md", issue_text)
        write(task / "meta.json", json.dumps(metadata, indent=2) + "\n")
        write(task / "hidden" / "test_acceptance.py", acceptance_text)
        write(
            task / "reference.json",
            json.dumps(
                {
                    "provenance": "Author reference patch, never provided to Agent",
                    "edits": [{"path": path, "old": bad, "new": good}],
                },
                indent=2,
            )
            + "\n",
        )
        manifest.append(
            {
                key: metadata[key]
                for key in ("id", "project", "split", "category", "initial_version")
            }
        )
    write(
        ROOT / "manifest.json",
        json.dumps(
            {
                "version": "synthetic-v0.1",
                "provenance": "self-authored artificial bugs; MIT",
                "split_policy": "first two ids of each project are dev; remaining three are frozen eval",
                "tasks": manifest,
            },
            indent=2,
        )
        + "\n",
    )
    demo = ROOT.parent / "examples" / "demo"
    write(
        demo / "pagination.py",
        clean('''
        def paginate(items, page, page_size):
            """Return a one-based page; invalid page arguments raise ValueError."""
            if page < 1 or page_size < 1:
                raise ValueError("page and page_size must be positive")
            start = (page - 1) * page_size + 1
            return items[start:start + page_size]
    '''),
    )
    write(
        demo / "tests" / "test_pagination.py",
        clean("""
        import pytest
        from pagination import paginate


        def test_first_page():
            assert paginate([0, 1, 2, 3, 4], 1, 2) == [0, 1]


        def test_pages_do_not_overlap():
            assert paginate([0, 1, 2, 3, 4], 2, 2) == [2, 3]
            assert paginate([0, 1, 2, 3, 4], 3, 2) == [4]


        def test_invalid_page():
            with pytest.raises(ValueError):
                paginate([1], 0, 2)
    """),
    )
    write(
        demo / "README.md",
        "# Offline demo\n\nSynthetic pagination bug for the scripted mock adapter.\nIssue: page 1 drops the first element; preserve one-based pages without overlaps.\nMock demonstrates engineering flow only, not model ability.\n",
    )


if __name__ == "__main__":
    generate()
    print("Generated 15 synthetic tasks (6 dev, 9 eval) and the offline demo.")
