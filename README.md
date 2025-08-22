
# Description

A tiny thread-based web scraper with a token bucket rate limiter. 

## Features
- Threaded crawling with a worker pool
- Token-bucket rate limiting
- Depth/breadth limits to avoid runaway crawling
- CLI with sensible defaults
- JSON output to a file or stdout

# Example Commands

Run with defaults

`python3 crawler.py https://www.nytimes.com https://www.bbc.com`

With all possible params set

`python3 crawler.py --max-workers 5 --max-depth 2 --max-outlinks 5 --rate-capacity 5 --rate-per-second 1.0 --timeout 5.0 --out results.json https://example.com`