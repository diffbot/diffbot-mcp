# Diffbot Extract

Extract structured content from any URL with the `extract` tool. It returns a clean markdown rendering of the page by default, or the full structured JSON on request.

## First: is a live fetch actually needed?

Extract is a **live retrieval**: it fetches and parses the page on demand. Measured: 1.3 s–9 s for most URLs, 24 s cold for one docs page (0.8 s on a repeat). That is the cost of going to the origin.

Diffbot has usually already parsed the page, and that copy is one index lookup away:

```
search_web(query="url:<URL> <what you want to know>")
```

~300 ms, one record back, and the chunks matching your terms. See the web-search prompt, which also covers when a cached copy is *not* safe to trust. Run it first for any public URL, the same way you would before reaching for `WebFetch` or `curl`. Come back here when:

- `search_results` came back **empty**: the URL isn't indexed (too new, paywalled, private, behind a login), so live retrieval is the only option;
- you need the **whole document**, not the ~4–6 KB of chunks the index lookup returns: every row of a table, a full changelog, an entire spec, license, or transcript (that docs page: 4.3 KB of chunks from the index, 25.5 KB of text from Extract);
- the page's **current state** is the question: a status page, a feed, a price, a version number, where a snapshot of unknown age is worse than no answer;
- you need Extract-only fields the search index doesn't carry: `author`, `images`, `links`, `tags`, `sentiment`, or a typed `product`/`discussion` parse.

## The `extract` tool

```
extract(url="<URL>", page_type="article" | "product" | "discussion" | "image" | "video" | "list" | "event" | "job" | "faq", format="markdown" | "json")
```

| Parameter | Default | Description |
| --- | --- | --- |
| `page_type` | automatic | Force a specific extractor when auto-detection picks the wrong one |
| `format` | `markdown` | `markdown` for cleaned LLM-friendly content, `json` for the full raw API response |

The `https://` scheme is added when missing.

## Common fields in the JSON response

The `objects[0]` structure from the automatic/article extractor includes:

| Field | Description |
| --- | --- |
| `title` | Page/article title |
| `text` | Plain text of the main content |
| `content` | Markdown-formatted content |
| `pageUrl` | Canonical URL |
| `date` | Publication date (ISO 8601) |
| `author` | Author name |
| `tags` | Entity tags (from the Diffbot KG) |
| `images` | Extracted images |
| `links` | Outbound links |
| `type` | Detected page type (`article`, `product`, etc.) |

## Tips

- Re-check the index before extracting a batch of URLs: a `url:` lookup per URL costs ~300 ms and usually removes the need to extract most of them.
- If extraction fails, the page may be behind auth, a bot wall, or a JavaScript app. Try `page_type="article"` explicitly as a fallback.
- To find the pages of a whole site rather than one URL, use `crawl`.
