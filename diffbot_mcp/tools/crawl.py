import csv
import io
import time
from typing import Annotated, Literal, Optional

from fastmcp.exceptions import ToolError

from ..api import request, resolve_token
from ..app import mcp
from .extract import PageType, normalize_url

CRAWL_ENDPOINT = "https://api.diffbot.com/v3/crawl"
EXTRACT_BASE = "https://api.diffbot.com/v3"
# jobStatus.status codes 0 and 7 mean the job is still in progress
RUNNING_STATUS_CODES = (0, 7)

DESCRIPTION = (
    "Crawls a website from a seed URL and extracts every page into structured data, for tasks that need many "
    "pages of a site rather than one known URL (that is extract). Crawls are background jobs: 'start' returns a "
    "job name, poll 'status' until is_running is false, then read 'results' or 'urls'; 'list' and 'delete' manage jobs."
)


def job_summary(job: dict) -> dict:
    status = job.get("jobStatus") or {}
    code = status.get("status")
    return {
        "job_name": job.get("name"),
        "status": status.get("message"),
        "status_code": code,
        "is_running": code in RUNNING_STATUS_CODES,
        "pages_crawled": job.get("pageCrawlSuccesses"),
        "pages_processed": job.get("pageProcessSuccesses"),
        "objects_found": job.get("objectsFound"),
        "created": job.get("jobCreationTimeUTC"),
    }


@mcp.tool(name="crawl", description=DESCRIPTION)
async def crawl(
    action: Annotated[Literal["start", "status", "urls", "results", "list", "delete"], "start needs url; others need job_name"] = "start",
    url: Annotated[Optional[str], "Seed URL (start)"] = None,
    job_name: Annotated[Optional[str], "Job handle; generated on start if omitted"] = None,
    hops: Annotated[int, "Link depth from seed"] = 2,
    max_to_crawl: Annotated[int, "Max pages visited"] = 100,
    max_to_process: Annotated[int, "Max pages extracted"] = 100,
    restrict_domain: Annotated[bool, "Stay on the seed's domain"] = True,
    url_crawl_pattern: Annotated[Optional[str], "Only visit URLs containing this"] = None,
    url_process_pattern: Annotated[Optional[str], "Only extract URLs containing this, e.g. /blog/"] = None,
    obey_robots: Annotated[bool, "Honor robots.txt"] = False,
    use_proxies: Annotated[bool, "Crawl through proxies"] = False,
    crawl_delay: Annotated[Optional[float], "Seconds between requests per domain"] = None,
    custom_headers: Annotated[Optional[str], "Extra HTTP headers, newline separated"] = None,
    page_type: Annotated[Optional[PageType], "Force a page type; default auto"] = None,
    format: Annotated[Literal["markdown", "json"], "Stored page format"] = "markdown",
    max_results: Annotated[int, "Max rows (urls, results)"] = 10,
    offset: Annotated[int, "Rows to skip (urls, results)"] = 0,
) -> dict:
    token = resolve_token()

    if action not in ("start", "list") and not job_name:
        raise ToolError(f"job_name is required for action '{action}'")

    if action == "start":
        if not url:
            raise ToolError("url is required to start a crawl")
        url = normalize_url(url)
        job_name = job_name or f"crawl-{int(time.time())}"

        api_url = f"{EXTRACT_BASE}/{page_type or 'analyze'}"
        if format == "markdown":
            api_url = f"{api_url}?mode=llm"

        params = {
            "token": token,
            "name": job_name,
            "seeds": url,
            "apiUrl": api_url,
            "maxHops": hops,
            "maxToCrawl": max_to_crawl,
            "maxToProcess": max_to_process,
            "restrictDomain": restrict_domain,
            "obeyRobots": obey_robots,
            "useProxies": use_proxies,
            "urlCrawlPattern": url_crawl_pattern,
            "urlProcessPattern": url_process_pattern,
            "customHeaders": custom_headers,
            "crawlDelay": crawl_delay if crawl_delay and crawl_delay > 0 else None,
        }
        response = await request(CRAWL_ENDPOINT, params=params)
        return {"job_name": job_name, "response": response}

    if action == "status":
        response = await request(CRAWL_ENDPOINT, params={"token": token, "name": job_name})
        jobs = response.get("jobs") or []
        if not jobs:
            raise ToolError(f"No crawl job named '{job_name}'")
        return job_summary(jobs[0])

    if action == "list":
        response = await request(CRAWL_ENDPOINT, params={"token": token})
        return {"jobs": [job_summary(job) for job in response.get("jobs") or []]}

    if action == "delete":
        response = await request(CRAWL_ENDPOINT, params={"token": token, "name": job_name, "delete": 1})
        return {"job_name": job_name, "response": response}

    if action == "urls":
        text = await request(f"{CRAWL_ENDPOINT}/data", params={"token": token, "name": job_name, "type": "urls"}, as_text=True)
        rows = []
        for row in csv.DictReader(io.StringIO(text or "")):
            page_url = (row.get("Url") or "").strip().strip('"')
            if page_url:
                rows.append({
                    "url": page_url,
                    "status": (row.get("Crawl Status") or "unknown").strip(),
                    "crawled": (row.get("Crawled Time") or "").strip() or None,
                })
        return {
            "job_name": job_name,
            "total_urls": len(rows),
            "offset": offset,
            "urls": rows[offset:offset + max_results],
        }

    response = await request(f"{CRAWL_ENDPOINT}/data", params={"token": token, "name": job_name, "format": "json"})
    if isinstance(response, dict):
        if response.get("error"):
            raise ToolError(f"{response['error']} (job '{job_name}')")
        response = response.get("objects") or []

    return {
        "job_name": job_name,
        "total_results": len(response),
        "offset": offset,
        "results": response[offset:offset + max_results],
    }
