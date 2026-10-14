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
    "Crawls a website and extracts every page it visits into structured data. Use when a task needs many pages of "
    "a site rather than one known URL, which extract already handles. Crawls run as background jobs and are not "
    "instant: 'start' creates a job and returns its name, 'status' reports progress, 'urls' lists every URL the "
    "crawler has visited with its per-page crawl status, 'results' returns the extracted pages, 'list' shows every "
    "job on the token, and 'delete' removes a job. Poll status until is_running is false before reading results. "
    "The job name is the only handle on a job, so keep the name returned by 'start'."
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
    action: Annotated[Literal["start", "status", "urls", "results", "list", "delete"], "The operation to perform. 'start' requires url. 'status', 'urls', 'results' and 'delete' require job_name."] = "start",
    url: Annotated[Optional[str], "The seed URL to crawl from. Required for 'start', ignored otherwise."] = None,
    job_name: Annotated[Optional[str], "The name of the crawl job. Required for 'status', 'urls', 'results' and 'delete'. Optional for 'start', where one is generated if omitted."] = None,
    hops: Annotated[int, "Maximum link depth to follow from the seed URL. Only applies to 'start'."] = 2,
    max_to_crawl: Annotated[int, "Maximum number of pages to crawl. Only applies to 'start'."] = 100,
    max_to_process: Annotated[int, "Maximum number of crawled pages to extract content from. Only applies to 'start'."] = 100,
    restrict_domain: Annotated[bool, "Only follow links on the same domain as the seed URL. Only applies to 'start'."] = True,
    url_crawl_pattern: Annotated[Optional[str], "Optional. Only crawl URLs containing this pattern. Only applies to 'start'."] = None,
    url_process_pattern: Annotated[Optional[str], "Optional. Only extract content from URLs containing this pattern, e.g. '/blog/'. Narrows extraction without narrowing crawling. Only applies to 'start'."] = None,
    obey_robots: Annotated[bool, "Obey the site's robots.txt. Only applies to 'start'."] = False,
    use_proxies: Annotated[bool, "Use proxies to crawl the site. Only applies to 'start'."] = False,
    crawl_delay: Annotated[Optional[float], "Optional. Seconds to wait between requests to the same domain. Only applies to 'start'."] = None,
    custom_headers: Annotated[Optional[str], "Optional. Custom HTTP headers to send with every request, newline separated, e.g. 'Cookie: a=b\\nUser-Agent: x'. Only applies to 'start'."] = None,
    page_type: Annotated[Optional[PageType], "Optional. The page type to extract every crawled page as. Defaults to automatic classification. Only applies to 'start'."] = None,
    format: Annotated[Literal["markdown", "json"], "The format each crawled page is stored in: 'markdown' for LLM friendly markdown, 'json' for the structured response matching the page type's ontology. Only applies to 'start'."] = "markdown",
    max_results: Annotated[int, "Maximum number of rows to return. Applies to 'urls' and 'results'."] = 10,
    offset: Annotated[int, "Number of rows to skip, for paging through a large crawl. Applies to 'urls' and 'results'."] = 0,
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
