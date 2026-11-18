import csv
import io
import time
from typing import Annotated, Literal, Optional

from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from diffbot import APIError

from ..api import diffbot
from ..app import mcp
from .extract import PageType, normalize_url

# jobStatus.status codes 0 and 7 mean the job is still in progress
RUNNING_STATUS_CODES = (0, 7)

DESCRIPTION = (
    "Crawls a website from a seed URL and extracts every page it finds into markdown or typed JSON. Prefer when a "
    "task needs to discover a catalog of pages from an entire site, or deep search a site for structured data "
    "(e.g. all product inventory, all press releases, PDFs). Crawls run in the background. `start` returns a job "
    "name, poll `status` until is_running is false, then read `results` or `urls`. `list` and `delete` manage jobs."
    " API docs: https://www.diffbot.com/docs/crawl/"
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


@mcp.tool(name="crawl", title="Crawl Website", description=DESCRIPTION, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True))
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
    use_proxies: Annotated[bool, "Crawl with Diffbot proxy; try when site blocks the crawler"] = False,
    crawl_delay: Annotated[Optional[float], "Seconds between requests per domain"] = None,
    custom_headers: Annotated[Optional[str], "Extra HTTP headers, newline separated"] = None,
    page_type: Annotated[Optional[PageType], "Override auto-detection; rarely needed"] = None,
    format: Annotated[Literal["markdown", "json"], "`markdown` for readable text; `json` for typed fields such as title, author, date, price, images"] = "markdown",
    max_results: Annotated[int, "Max rows (urls, results)"] = 10,
    offset: Annotated[int, "Rows to skip (urls, results)"] = 0,
) -> dict:
    if action not in ("start", "list") and not job_name:
        raise ToolError(f"job_name is required for action '{action}'")

    async with diffbot() as db:
        if action == "start":
            if not url:
                raise ToolError("url is required to start a crawl")
            url = normalize_url(url)
            job_name = job_name or f"crawl-{int(time.time())}"

            api_url = f"{db.analyze_url}/{page_type or 'analyze'}"
            if format == "markdown":
                api_url = f"{api_url}?mode=llm"

            # Built here rather than with db.crawl(): the SDK leaves obeyRobots out when it is
            # false, and the crawler's default is to obey, so obey_robots=False would be lost.
            # Booleans go out as 1/0 and unset options are dropped.
            params = {
                "token": db.token,
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
            params = {key: int(value) if isinstance(value, bool) else value for key, value in params.items() if value is not None}
            # creating a job is not idempotent, so no retries
            created = await db.request("GET", db.crawler_url, params=params, retryable=False)
            response = created.json()
            # some create failures (e.g. a job name over 30 characters) come back as a 200 with errorCode
            if isinstance(response, dict) and response.get("errorCode"):
                raise APIError(created.status_code, created.text)
            return {"job_name": job_name, "response": response}

        if action == "status":
            job = await db.crawl_get_job(job_name)
            if not job:
                raise ToolError(f"No crawl job named '{job_name}'")
            return job_summary(job)

        if action == "list":
            return {"jobs": [job_summary(job) for job in await db.crawl_list_jobs()]}

        if action == "delete":
            await db.crawl_delete_job(job_name)
            return {"job_name": job_name, "deleted": True}

        if action == "urls":
            text = await db.crawl_download(job_name, type="urls")
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

        # an unknown job raises JobError, which names the job
        response = await db.crawl_download(job_name)

        return {
            "job_name": job_name,
            "total_results": len(response),
            "offset": offset,
            "results": response[offset:offset + max_results],
        }
