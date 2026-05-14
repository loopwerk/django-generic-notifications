test:
  uv run pytest

format:
  uv run ruff format .

check:
  uv run ruff check . && uv run mypy .