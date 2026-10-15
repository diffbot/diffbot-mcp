# Diffbot Crawler

Crawl websites for structured content with the `crawl` tool, and manage crawler jobs. A crawl finds every link from a seed URL and extracts each page it visits, the same way `extract` handles one URL.

Crawls run as **background jobs**. The tool does not block until the crawl finishes; you start a job, poll its status, then read the results.

Parameter notes for `crawl` that are not in the schema:

- Only `url` and the crawl settings (`hops`, `max_to_crawl`, `max_to_process`, `restrict_domain`, `url_crawl_pattern`, `url_process_pattern`, `obey_robots`, `use_proxies`, `crawl_delay`, `custom_headers`, `page_type`, `format`) apply to `start`. `url_process_pattern` narrows extraction without narrowing crawling.
- `status`, `urls`, `results`, and `delete` need `job_name`; the name returned by `start` is the only handle on a job. `max_results` and `offset` page through `urls` and `results`.
- `format="markdown"` stores LLM-friendly markdown; `"json"` stores the structured record matching the page type's ontology.

```
crawl(action="start", url="<SITE>", ...options)      # create a job; returns job_name
crawl(action="status", job_name="<NAME>")            # progress; is_running tells you whether to keep polling
crawl(action="urls", job_name="<NAME>")              # every URL visited with its per-page crawl status
crawl(action="results", job_name="<NAME>")           # the extracted pages
crawl(action="list")                                 # every job on the token
crawl(action="delete", job_name="<NAME>")            # remove a job
```

## `start` options

| Parameter | Default | Description |
| --- | --- | --- |
| `hops` | 2 | Maximum link depth from the seed URL |
| `job_name` | generated | Name for the job. It is the only handle on the job, so keep it |
| `max_to_crawl` | 100 | Maximum pages to crawl |
| `max_to_process` | 100 | Maximum crawled pages to extract content from |
| `restrict_domain` | true | Only follow links on the same domain as the seed |
| `url_crawl_pattern` | none | Only crawl URLs containing this pattern |
| `url_process_pattern` | none | Only extract content from URLs containing this pattern, e.g. `/blog/`. Narrows extraction without narrowing crawling |
| `obey_robots` | false | Obey robots.txt |
| `use_proxies` | false | Use proxies for crawling |
| `crawl_delay` | none | Seconds between requests to the same domain |
| `custom_headers` | none | Newline-separated custom HTTP headers |
| `page_type` | automatic | Extract every page as this type (`article`, `product`, …) |
| `format` | `markdown` | How each page is stored: LLM-friendly markdown or structured JSON |

## Workflow

1. **Start.** `crawl(action="start", url="https://docs.example.com", hops=3, max_to_crawl=500, max_to_process=500)`. Note the returned `job_name`.
2. **Poll.** `crawl(action="status", job_name=...)` until `is_running` is false. Small sites finish in a minute or two; do not poll more often than every 15–30 seconds.
3. **Inspect.** `crawl(action="urls", job_name=...)` lists each URL with `Success` or an error status, so failed pages are visible before reading the payload.
4. **Read.** `crawl(action="results", job_name=..., max_results=10, offset=0)` pages through the extracted objects. Each carries the same fields `extract` returns (`title`, `pageUrl`, `content` or `text`, …). Read a few pages at a time rather than pulling a whole crawl into the conversation.

Crawl only blog posts by URL pattern:

```
crawl(action="start", url="https://example.com", url_process_pattern="/blog/", max_to_process=200)
```

## Tips

- `restrict_domain` is on by default; disable it only if you intentionally want to follow external links.
- Use `url_process_pattern` to focus extraction on specific path segments without narrowing crawling.
- Set `job_name` yourself if you want to look the job up or delete it later; generated names are `crawl-<timestamp>`.
- For a single known page, `extract` is faster; for pages Diffbot has already indexed, `search_web` with a `url:` prefix is faster still.
