# Base sandbox: a small uv-managed Python project with one known bug
# (total_price truncates instead of rounding), a failing test for it, and a
# local bare remote named origin. Runs with the sandbox repository as cwd.
git init -q -b main
mkdir -p inventory tests

cat > pyproject.toml <<'EOF'
[project]
name = "inventory"
version = "0.1.0"
description = "Stock counts and price calculations for a small shop."
requires-python = ">=3.11"
dependencies = []
EOF

cat > .gitignore <<'EOF'
.venv/
__pycache__/
EOF

cat > README.md <<'EOF'
# inventory

Stock counts and price calculations for a small shop. The JSON file written by
`inventory/store.py` is the system of record for stock counts.

Performance budget: `find_item` must stay under 50 ms on 100,000 items.
`bench.py` measures it and prints the time in milliseconds.
EOF

: > inventory/__init__.py

cat > inventory/calc.py <<'EOF'
"""Price calculations."""


def apply_discount(price: float, percent: float) -> float:
    """Return price reduced by percent. The percent is clamped to 0..100."""
    percent = max(0.0, min(100.0, percent))
    return price * (1 - percent / 100)


def total_price(items: list[tuple[float, int]]) -> float:
    """Return the sum of unit price times quantity, rounded to cents."""
    total = sum(price * qty for price, qty in items)
    return int(total * 100) / 100
EOF

cat > inventory/store.py <<'EOF'
"""JSON file store: the system of record for stock counts."""

import json
from pathlib import Path


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text())


def save(path: Path, items: list[dict]) -> None:
    path.write_text(json.dumps(items, indent=2))


def find_item(items: list[dict], name: str) -> dict | None:
    """Return the first item whose name equals name, or None."""
    for item in items:
        if item["name"] == name:
            return item
    return None


def set_count(path: Path, name: str, count: int) -> None:
    items = load(path)
    item = find_item(items, name)
    if item is None:
        items.append({"name": name, "count": count})
    else:
        item["count"] = count
    save(path, items)
EOF

cat > inventory/export.py <<'EOF'
"""Export stock counts for the accountant."""

import json
from pathlib import Path


def export_json(items: list[dict], dest: Path) -> None:
    """Write name and count for every item as a JSON array."""
    rows = [{"name": item["name"], "count": item["count"]} for item in items]
    dest.write_text(json.dumps(rows, indent=2))
EOF

cat > bench.py <<'EOF'
"""Time find_item on 100,000 items. Budget: under 50 ms."""

import time

from inventory.store import find_item

items = [{"name": f"Item-{n}", "count": n} for n in range(100_000)]
start = time.perf_counter()
for _ in range(20):
    find_item(items, "Item-99999")
print(f"{(time.perf_counter() - start) / 20 * 1000:.2f} ms")
EOF

cat > tests/test_calc.py <<'EOF'
import unittest

from inventory.calc import apply_discount, total_price


class CalcTest(unittest.TestCase):
    def test_discount(self):
        self.assertAlmostEqual(apply_discount(200.0, 25), 150.0)

    def test_total_rounds_to_cents(self):
        self.assertEqual(total_price([(19.999, 1)]), 20.0)


if __name__ == "__main__":
    unittest.main()
EOF

cat > tests/test_store.py <<'EOF'
import tempfile
import unittest
from pathlib import Path

from inventory.store import find_item, load, set_count


class StoreTest(unittest.TestCase):
    def test_set_and_find(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stock.json"
            set_count(path, "Widget", 3)
            set_count(path, "Widget", 5)
            self.assertEqual(find_item(load(path), "Widget")["count"], 5)


if __name__ == "__main__":
    unittest.main()
EOF

uv lock -q
git add -A
git commit -q -m "feat: inventory store, price calculations and JSON export"
git init -q --bare "$RUN/remote.git"
git remote add origin "$RUN/remote.git"
git push -q -u origin main
