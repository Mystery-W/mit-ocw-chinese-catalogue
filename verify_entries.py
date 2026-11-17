"""Check resource landing pages without downloading media or claiming playback.

Reads the generated catalogue and checks OCW-hosted video entry pages and entries
whose sparse metadata needs review. Responses are cached independently; only HTML
is requested. External platforms are recorded as unverified, not crawled broadly.
"""
from __future__ import annotations

import concurrent.futures
import gzip
import hashlib
import json
from pathlib import Path

from lxml import html

from crawl_ocw import now, request, save_json, clean
from build_catalogue import is_internal

ROOT = Path(__file__).resolve().parent


def verify(url: str) -> dict:
    """Record HTTP status and a local evidence copy; return failure instead of aborting."""
    key = hashlib.sha256(url.encode()).hexdigest()[:24]
    folder = ROOT / "entry_checks"
    folder.mkdir(exist_ok=True)
    result_path = folder / (key + ".json")
    if result_path.exists():
        return json.loads(result_path.read_text(encoding="utf-8"))
    result = {"url": url, "checked_at": now(), "playback_checked": False}
    try:
        response = request(url)
        result.update({"status": response.status_code, "final_url": response.url})
        (folder / (key + ".html.gz")).write_bytes(gzip.compress(response.content))
        tree = html.fromstring(response.content)
        result["title"] = clean(" ".join(tree.xpath('//title/text()')))
        areas = tree.xpath('//*[@id="course-content-section"] | //*[@id="main-content"] | //main')
        result["text_excerpt"] = clean((areas[0] if areas else tree).text_content())[:16000]
    except Exception as exc:
        result.update({"status": "error", "error": str(exc)})
    save_json(result_path, result)
    return result


def main() -> None:
    """Verify all identified internal video entries plus sparse-resource cases."""
    rows = json.loads((ROOT / "课程完整数据.json").read_text(encoding="utf-8"))
    urls = set()
    for row in rows:
        if row["resource_category"][0] in ("A", "B", "G"):
            if row["resource_category"].startswith("G"):
                urls.update(x["url"] for x in row["resource_links"] if is_internal(x["url"]))
            elif is_internal(row["primary_resource_url"]):
                urls.add(row["primary_resource_url"])
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        for future in concurrent.futures.as_completed([executor.submit(verify, u) for u in sorted(urls)]):
            results.append(future.result())
            if len(results) % 50 == 0:
                print(f"Entry checks {len(results)}/{len(urls)}", flush=True)
    save_json(ROOT / "resource_entry_checks.json", sorted(results,key=lambda x:x["url"]))
    print(f"Checked {len(results)} pages; failed {sum(r['status'] != 200 for r in results)}", flush=True)


if __name__ == "__main__":
    main()
