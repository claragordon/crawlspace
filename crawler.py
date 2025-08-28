import argparse
import json
from queue import Queue
from dataclasses import dataclass
import sys
import threading
from bs4 import BeautifulSoup
import requests
from typing import List, Optional
from urllib.parse import urljoin
import time


@dataclass
class UrlResult:
    url: str
    title: str
    outlinks: list[str]


class TokenBucket:
    """
    A threadsafe token bucket rate limiter.

    Attributes:
          capacity (int): Maximum number of tokens the bucket can hold.
          rate_per_second (float): Rate at which tokens are added to the bucket.
          tokens (float): Current number of available tokens.
          last_updated (float): Last time the bucket was refilled, in unix seconds.
    """

    def __init__(self, capacity: int, rate_per_second: float):
        self.tokens = capacity
        self.capacity = capacity
        self.rate_per_second = rate_per_second
        self.last_updated = time.time()
        self.lock = threading.Lock()

    def _refill(self):
        now = time.time()
        to_add = (now - self.last_updated) * self.rate_per_second
        self.tokens = min(self.capacity, self.tokens + to_add)
        self.last_updated = now

    def take(self, amount: float = 1.0) -> bool:
        """Attempt to take `amount` tokens. Returns True if allowed, else False."""
        with self.lock:
            self._refill()
            if self.tokens >= amount:
                self.tokens -= amount
                return True
            return False

    def wait(self, amount: float = 1.0) -> None:
        """Block until `amount` tokens are available and then consume them."""
        while not self.take(amount):
            time.sleep(0.01)


class WebScraper:
    """
    A concurrent web scraper with rate limiting and crawl depth control.

    It uses a pool of worker threads to fetch pages, extract metadata, and find outlinks.

    Attributes:
        workers (int): Number of worker threads to use parallel crawling.
        max_depth (int): Maximum depth to follow outlinks from the initial URLs.
        max_outlinks (int): Maximum number of outlinks to follow per crawled page.
        urls_to_process (Queue[tuple[str,int]]): Thread-safe queue of (url, depth) items.
        seen_urls: (set[str]): Set of already-visted urls.
        results (Queue[UrlResult]): Thread-safe queue of crawl results.
    """

    def __init__(
        self,
        workers: int,
        max_depth: int,
        max_outlinks: int,
        rate_capacity: int,
        rate_per_second: float,
        request_timeout: int,
    ):
        self.workers = workers
        self.max_depth = max_depth
        self.max_outlinks = max_outlinks
        self.request_timeout = request_timeout
        self.urls_to_process = Queue()
        self.rate_limiter = TokenBucket(rate_capacity, rate_per_second)
        self.seen_urls = set()
        self.seen_urls_lock = threading.Lock()
        self.results = Queue()  # Threadsafe for storing crawl results

    def _fetch(self, url: str) -> Optional[str]:
        self.rate_limiter.wait(1.0)
        try:
            resp = requests.get(url, timeout=self.request_timeout)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"Error processing {url}: {e}")
            return None

    def _parse(self, url: str, html: str) -> UrlResult:
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""
        outlinks = [
            urljoin(url, link.get("href")) for link in soup.find_all("a", href=True)
        ]
        return UrlResult(url=url, title=title, outlinks=outlinks)

    def _process_url(self, url: str) -> Optional[UrlResult]:
        html = self._fetch(url)
        if not html:
            return None
        return self._parse(url, html)

    def _worker(self):
        print(f"[{threading.current_thread().name}] Started")

        while True:
            url, depth = self.urls_to_process.get()
            try:
                if url is None:
                    break
                if depth > self.max_depth:
                    continue
                with self.seen_urls_lock:
                    if url in self.seen_urls:
                        continue
                    if self.seen_urls and len(self.seen_urls) % 10 == 0:
                        print(f"Processed {len(self.seen_urls)} urls")
                    self.seen_urls.add(url)

                result = self._process_url(url)
                if result:
                    self.results.put(result)
                    for outlink in result.outlinks[
                        : min(self.max_outlinks, len(result.outlinks))
                    ]:
                        self.urls_to_process.put((outlink, depth + 1))

            except Exception as e:
                print(f"Error processing {url}: {e}")

            finally:
                # Mark current element as done in all cases to keep queue
                # bookkeeping accurate.
                self.urls_to_process.task_done()

        print(f"[{threading.current_thread().name}] Done")

    def scrape_urls(self, urls: List[str]) -> list[UrlResult]:
        """
        Crawl a list of URLs concurrently and return their metadata.

        This method starts multiple worker threads to fetch and parse the given URLs,
        following their outbound links as needed.
        """
        start = time.time()
        with self.seen_urls_lock:
            self.seen_urls.clear()
        for url in urls:
            self.urls_to_process.put((url, 0))

        threads = []
        for _ in range(self.workers):
            t = threading.Thread(target=self._worker)
            t.start()
            threads.append(t)
        self.urls_to_process.join()
        for _ in range(self.workers):
            self.urls_to_process.put((None, 0))  # Poison pill to stop worker loop
        for t in threads:
            t.join()  # Join threads to ensure the worker loops finish before proceeding

        final_results = []
        while not self.results.empty():
            final_results.append(self.results.get())
        scrape_time = time.time() - start
        print(f"URLs scraped: {len(final_results)}")
        print(f"Total scrape time: {scrape_time:.2f} seconds")
        print(f"Mean time per url: {scrape_time / len(final_results):.2f} seconds")
        return final_results


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Threaded web scraper with rate limiting.")
    p.add_argument("urls", nargs="+", help="Seed URLs to scrape")
    p.add_argument("--workers", type=int, default=5, help="Number of worker threads")
    p.add_argument("--max-depth", type=int, default=2, help="Maximum crawl depth")
    p.add_argument(
        "--max-outlinks", type=int, default=5, help="Maximum outlinks followed per page"
    )
    p.add_argument(
        "--rate-capacity", type=float, default=5.0, help="Token bucket capacity"
    )
    p.add_argument(
        "--rate-per-second", type=float, default=1.0, help="Token bucket refill rate"
    )
    p.add_argument(
        "--timeout", type=float, default=5.0, help="HTTP request timeout in seconds"
    )
    p.add_argument("--out", type=str, default="", help="Write results to JSON file")
    return p.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    scraper = WebScraper(
        args.workers,
        args.max_depth,
        args.max_outlinks,
        args.rate_capacity,
        args.rate_per_second,
        args.timeout,
    )
    results = scraper.scrape_urls(args.urls)
    payload = [r.__dict__ for r in results]

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
