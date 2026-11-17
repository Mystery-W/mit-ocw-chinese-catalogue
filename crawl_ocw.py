"""Collect an auditable OCW catalogue, with resumable caches and bounded requests.

Run in Python 3.10+ with requests and lxml (the existing CorpusCrawler environment
already supplies both). Only public catalogue metadata and HTML are downloaded;
videos, PDFs and original research files are never modified. Each output directory
is a dated snapshot; use a NEW directory for a later refresh.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import requests
from lxml import etree, html

BASE = "https://ocw.mit.edu/"
SEARCH = "https://open.mit.edu/api/v0/search/"
TZ = timezone(timedelta(hours=8))
LOCAL = threading.local()
LOCK = threading.Lock()
NEXT_REQUEST = 0.0


def now() -> str:
    """Return an unambiguous capture time in the user's UTC+08 time zone."""
    return datetime.now(TZ).isoformat(timespec="seconds")


def save_json(path: Path, value: Any) -> None:
    """Atomically replace generated state so an interruption leaves a valid cache."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def request(url: str, payload: dict | None = None) -> requests.Response:
    """Fetch public content with global pacing, per-thread sessions and retries.

    Network/5xx errors receive bounded retries. A 403 or 429 is not bypassed;
    the request is recorded as failed for a later explicit rerun.
    """
    global NEXT_REQUEST
    if not hasattr(LOCAL, "session"):
        LOCAL.session = requests.Session()
        LOCAL.session.headers["User-Agent"] = "PersonalStudyCatalogue/1.0 (public OCW metadata; rate-limited)"
    for attempt in range(3):
        with LOCK:
            delay = max(0.0, NEXT_REQUEST - time.monotonic())
            NEXT_REQUEST = time.monotonic() + delay + 0.18
        time.sleep(delay)
        try:
            response = LOCAL.session.request("POST" if payload else "GET", url,
                                             json=payload, timeout=(15, 60))
            if response.status_code in (403, 404, 429):
                response.raise_for_status()
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            if getattr(exc.response, "status_code", None) in (403, 404, 429) or attempt == 2:
                raise
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError("Request exhausted")


def discover(root: Path) -> list[str]:
    """Compare the public search API with the sitemap, preserving both originals."""
    source = root / "sources"
    source.mkdir(exist_ok=True)
    robot_file = source / "robots.txt"
    if not robot_file.exists():
        robot_file.write_bytes(request(BASE + "robots.txt").content)
    robots = RobotFileParser()
    robots.parse(robot_file.read_text(encoding="utf-8").splitlines())
    if not robots.can_fetch("PersonalStudyCatalogue", BASE + "courses/"):
        raise RuntimeError("robots.txt does not allow course collection")
    sitemap = source / "sitemap.xml"
    if not sitemap.exists():
        sitemap.write_bytes(request(BASE + "sitemap.xml").content)
    xml = etree.fromstring(sitemap.read_bytes())
    sitemap_urls = {u.removesuffix("sitemap.xml") for u in xml.xpath('//*[local-name()="loc"]/text()')
                    if "/courses/" in u and u.endswith("/sitemap.xml")}
    search_file = source / "search_courses.json"
    if search_file.exists():
        hits = json.loads(search_file.read_text(encoding="utf-8"))
        total = json.loads((source / "search_summary.json").read_text(encoding="utf-8"))["reported_total"]
    else:
        hits, total, offset = [], None, 0
        while total is None or offset < total:
            query = {"from": offset, "size": 100, "sort": [{"id": "asc"}],
                     "query": {"bool": {"filter": [{"term": {"object_type": "course"}},
                                                    {"term": {"offered_by": "OCW"}}]}}}
            result = request(SEARCH, query).json()
            save_json(source / f"search_{offset:05d}.json", result)
            raw_total = result["hits"]["total"]
            total = raw_total.get("value") if isinstance(raw_total, dict) else raw_total
            batch = result["hits"]["hits"]
            if not batch:
                raise RuntimeError(f"Search ended early at {offset}/{total}")
            hits.extend(x["_source"] for x in batch)
            offset += len(batch)
            logging.info("Search %s/%s", offset, total)
        if len({x["id"] for x in hits}) != total:
            raise RuntimeError("Search result IDs are duplicated or missing")
        save_json(search_file, hits)
        save_json(source / "search_summary.json", {"reported_total": total, "fetched_at": now(), "query": query})
    search_urls = {urljoin(BASE, r["slug"]).rstrip("/") + "/" for c in hits for r in c.get("runs", []) if r.get("slug")}
    urls = sorted(sitemap_urls | search_urls)
    save_json(root / "coverage.json", {"discovered_at": now(), "search_total": total,
              "search_unique_urls": len(search_urls), "sitemap_course_urls": len(sitemap_urls),
              "search_only": sorted(search_urls-sitemap_urls), "sitemap_only": sorted(sitemap_urls-search_urls),
              "union_total": len(urls)})
    return urls


def clean(text: str) -> str:
    """Normalize display whitespace without truncating source descriptions."""
    return " ".join(text.split())


def collect(url: str, root: Path) -> dict:
    """Read one course's metadata and homepage, retaining independent evidence.

    Each response is cached separately, so a later failure does not discard earlier
    progress. A failed homepage is unknown availability, never 'not open'.
    """
    slug = url.rstrip("/").split("/")[-1]
    # Hash cache names to remain below Windows path limits for very long titles.
    key = hashlib.sha256(url.encode()).hexdigest()[:20]
    cache = root / "cache" / key
    cache.mkdir(parents=True, exist_ok=True)
    record_path = cache / "record.json"
    if record_path.exists():
        old = json.loads(record_path.read_text(encoding="utf-8"))
        if old.get("status") == "ok":
            return old
    record: dict[str, Any] = {"url": url, "slug": slug, "cache_key": key, "fetched_at": now(), "errors": []}
    for name, suffix in (("metadata", "data.json"), ("homepage", "")):
        filename = cache / ("data.json" if name == "metadata" else "homepage.html.gz")
        try:
            if filename.exists():
                content = filename.read_bytes() if name == "metadata" else gzip.decompress(filename.read_bytes())
            else:
                response = request(url + suffix)
                content = response.content
                if name == "metadata":
                    json.loads(content)  # Reject HTML error pages before caching.
                filename.write_bytes(content if name == "metadata" else gzip.compress(content))
                save_json(cache / f"{name}_response.json", {"requested_url": url+suffix,
                          "final_url": response.url, "status_code": response.status_code,
                          "fetched_at": now(), "sha256": hashlib.sha256(content).hexdigest(),
                          "last_modified": response.headers.get("Last-Modified")})
            if name == "metadata":
                record["metadata"] = json.loads(content)
            else:
                page = html.fromstring(content)
                record["departments"] = list(dict.fromkeys(clean(e.text_content()) for e in
                    page.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," course-info-department ")]')))
                links = []
                for a in page.xpath('//*[@id="mobile-course-nav"]//a[@href]'):
                    item = {"label": clean(a.text_content()), "url": urljoin(url, a.get("href"))}
                    if item["label"] and item not in links:
                        links.append(item)
                record["resource_links"] = links
                record["mooc_links"] = list(dict.fromkeys(urljoin(url, a.get("href")) for a in page.xpath('//main//a[@href] | //*[@id="course-main-content"]//a[@href]')
                    if any(domain in a.get("href", "").lower() for domain in ("edx.org", "mitxonline.mit.edu"))))
                record["download_links"] = list(dict.fromkeys(urljoin(url, a.get("href")) for a in page.xpath('//a[@href]')
                    if a.get("href", "").endswith("/download/") and "/courses/" in a.get("href", "")))
                full = page.xpath('//*[@id="expanded-description"]') or page.xpath('//*[@id="collapsed-description"]')
                if full:
                    for button in full[0].xpath('.//button'):
                        button.drop_tree()
                    record["description_text"] = clean(full[0].text_content())
                record["homepage_title"] = clean(" ".join(page.xpath('//h1//text()')))
        except Exception as exc:
            record["errors"].append({"part": name, "error": str(exc)})
    record["status"] = "ok" if not record["errors"] else "partial_or_failed"
    save_json(record_path, record)
    return record


def main() -> None:
    """Collect or resume a snapshot and report exact success/failure counts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=0, help="Optional small diagnostic sample")
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(root/"crawl.log", encoding="utf-8"), logging.StreamHandler()])
    urls = discover(root)
    if args.limit:
        urls = urls[:args.limit]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8,max(1,args.workers))) as executor:
        futures = {executor.submit(collect, url, root): url for url in urls}
        for f in concurrent.futures.as_completed(futures):
            try:
                results.append(f.result())
            except Exception as exc:
                results.append({"url": futures[f], "status": "failed", "errors": [str(exc)]})
            if len(results) % 50 == 0 or len(results) == len(urls):
                counts = {"completed": len(results), "total": len(urls),
                          "ok": sum(r["status"] == "ok" for r in results), "updated_at": now()}
                save_json(root/"progress.json", counts)
                logging.info("Courses %s", counts)
    results.sort(key=lambda x: x["url"])
    save_json(root/"course_records.json", results)
    failures = [r for r in results if r["status"] != "ok"]
    save_json(root/"failures.json", failures)
    logging.info("FINISHED: %s successful, %s partial/failed; output: %s",len(results)-len(failures),len(failures),root)


if __name__ == "__main__":
    main()
