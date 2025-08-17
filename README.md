
# rc-scraper

A tiny, well-structured, thread-based web scraper with a token-bucket rate limiter. 
Designed to be a concise but polished coding sample for the Recurse Center application.

## Features
- Threaded crawling with a worker pool
- Token-bucket rate limiting (polite scraping)
- Depth/breadth limits to avoid runaway crawling
- Deterministic, testable design with mocks
- CLI with sensible defaults
- JSON output to a file or stdout

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# Run with defaults
python -m scraper https://www.nytimes.com https://www.bbc.com

# Limit depth/breadth & write to a file
python -m scraper --max-depth 1 --max-breadth 2 --out results.json https://example.com
```

## Project Layout
```
scraper/
  __init__.py
  __main__.py      # CLI entry point
  models.py
  rate_limit.py
  scraper.py
tests/
  test_rate_limit.py
  test_scraper.py
requirements.txt
README.md
```

## Notes
- This is intentionally minimal and dependency-light.
- All network calls respect a simple rate limiter and set a short timeout.
- Tests use `unittest.mock` to avoid real HTTP requests.
