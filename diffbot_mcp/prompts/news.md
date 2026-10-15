# Diffbot News Search

Find news articles in the Diffbot Knowledge Graph. This is `type:Article` DQL with news-shaped defaults already chosen: recency sorting, the right narrowing levers, and a display format built for headlines.

**Prefer the `search_news` tool.** It builds the query described below from typed parameters (mentions, topic, text, publisher, dates, sentiment, facet), applies the sort rule, resolves `topic` against the ArticleCategory taxonomy, and returns the DQL it ran. Drop to `dql` only when the shape is outside those parameters, and use `dql_probe` to compare variants first.

Parameter notes for `search_news` that are not in the schema:

- `mentions` is `tags.label`, the strongest lever; if it returns nothing, retry the same words as `text`. `title` is a headline-only match and much tighter than `text`.
- `topic` is resolved against the ArticleCategory taxonomy; ambiguous text returns `candidates`.
- `sentiment_min`/`sentiment_max` filter the document score (-1..1; `sentiment_max=-0.5` is negative coverage). `mention_sentiment_max` is the score toward the single entity in `mentions` and is ignored with zero or several mentions.
- Without a date range results are newest first; inside one they are relevance-ranked. `facet` buckets instead of rows, e.g. which outlets cover an entity.
- To deliver the results as a CSV file, pass the `dql` string this tool returns to `export_csv` with a `path`; it exports the whole result set, not a page.

This is the workflow for **all** news requests, breaking events included; the Knowledge Graph's article index updates continuously. Do not hand news off to `search_web`. For non-news entity queries use the sibling prompts (organizations, people, places, deals), or `dql` for anything outside those shapes.

## Step 1 — build the query

Every query starts `type:Article`. Add narrowing clauses, then apply the sort rule.

### The sort rule

| The user's request | Sort clause |
| --- | --- |
| No sort and no date condition | append `sortBy:date` (newest first). **The default**, and what `search_news` does when `sort` is unset |
| Names an explicit sort ("most relevant", "highest sentiment") | use that sort; do not add `sortBy:date` |
| Contains a date condition (`date>=`, "in July", "last quarter", "2024") | omit `sortBy:date`; the window already scopes recency, so let relevance ordering pick the best articles inside it (`search_news` switches to relevance when `since` or `until` is given) |

`sortBy:date` is ascending by field name but returns newest-first for `date`; use `revSortBy:date` only if the user explicitly wants oldest-first.

### Narrowing levers, in order of preference

1. **`tags.label:"<entity>"`** (the `mentions` parameter): articles that *mention* a KG entity. The strongest lever for "news about X" where X is a company, person, product, or place.
   ```
   type:Article tags.label:"Nvidia" sortBy:date
   ```
   Tag values are entity names; there is no exhaustive list. If a tag returns zero or too few hits, fall back to `text:`.

2. **`categories.name:"<category>"`** (the `topic` parameter): IAB topic taxonomy (459 values), best for subject-matter queries.
   ```
   type:Article categories.name:"Artificial Intelligence" sortBy:date
   ```
   Look up exact names before using them in raw DQL: `dql_ontology(action="taxonomy", name="ArticleCategory", search="<regex>")`. `search_news` resolves free text itself and returns candidates when it is ambiguous.

3. **`text:"<phrase>"`**: full-text fallback when no tag or category fits.

4. **`title:"<phrase>"`**: headline-only match; much tighter than `text:`.

### Field reference

| Field | Type | Notes |
| --- | --- | --- |
| `date` | DDateTime | Publication date. Compare as `date>="2026-01-01"` |
| `title` | String | Headline |
| `summary` | String | Short abstract. **Use this, not `text` or `html`** |
| `text` / `html` | String | Full body. Huge; never pull into the conversation |
| `siteName` | String | Publisher, e.g. `"Reuters"` |
| `author` | String | Byline |
| `language` | String | ISO code, e.g. `"en"`, `"no"` |
| `publisherCountry` | String | Full country name, e.g. `"Norway"`, not a code |
| `publisherRegion` | String | Macro region, e.g. `"Northern Europe"` |
| `sentiment` | Float | −1 (negative) to +1 (positive) |
| `tags` | list | `tags.label`, `tags.sentiment`, `tags.score`; per-entity sentiment lives here |
| `categories` | list | `categories.name`, `categories.score` |
| `quotes` | list | `quotes.speaker`, `quotes.quote` |
| `pageUrl` | String | Canonical article URL |

### Worked examples

```
type:Article tags.label:"OpenAI" sortBy:date
type:Article categories.name:"Artificial Intelligence" date>="2026-08-01"
type:Article tags.label:"OpenAI" sentiment<-0.5 sortBy:date
type:Article language:"en" tags.label:"Nvidia" date>="2026-08-05"
type:Article quotes.speaker:"Sam Altman" sortBy:date
type:Article tags.label:or("Tesla","Rivian") categories.name:"Automotive" sortBy:date
```

**Entity-specific sentiment.** Document-level `sentiment` scores the whole article. For "negative coverage *of Nvidia specifically*" in an article that also covers others, co-constrain inside the tag with a subquery (`search_news` does this from `mentions=["Nvidia"], mention_sentiment_max=-0.3`):

```
type:Article tags.{label:"Nvidia" sentiment<-0.3} sortBy:date
```

### "Who is covering this?" is a facet

For distribution questions (which outlets, which topics, how coverage is spread over time) aggregate rather than listing articles: `search_news(mentions=["Anthropic"], facet="siteName", size=15)`, or in raw DQL:

```
type:Article tags.label:"Anthropic" facet:siteName
```

Also useful: `facet:categories.name` (what topics an entity gets covered under), `facet:publisherCountry` (geographic spread), `facet:date` (volume over time; date fields accept `day`, `week`, or `month` interval specifiers).

Facets need `size` ≥ 1, and `size` sets the **number of buckets**, not rows. Expect noise in `siteName` buckets: aggregators, forums, and mirrors rank alongside newsrooms, so read the top buckets before quoting them.

## Step 2 — probe before committing

```
dql_probe(queries=[
  'type:Article tags.label:"Anthropic" sortBy:date',
  'type:Article tags.label:"Anthropic" categories.name:"Artificial Intelligence" sortBy:date',
  'type:Article title:"Anthropic" sortBy:date'
])
```

Aim for a few hundred to a few thousand hits. Zero means the tag or category string is wrong: check the taxonomy or fall back to `text:`.

**Never probe an unfiltered `type:Article`** (or bare `has:` / `language:` filters over the whole corpus). The article index is large enough that these time out.

## Step 3 — fetch and display

`search_news` returns rows with Date, Title, Publisher, Author, Sentiment, URL, and Summary, plus the DQL it ran. The equivalent raw call is:

```
dql(query="<DQL>", size=25, fields="date.str,Date;title,Title;siteName,Publisher;sentiment,Sentiment;pageUrl,URL")
```

Use `dql(query="<DQL> get:title,summary,tags", format="json")` only when a list field must be read in full (every tag with its sentiment). Never relay raw records; read `summary`, not `text`.

**Display**

1. Render a markdown table: **Date | Headline | Publisher | Sentiment**, with the headline linked to the URL.
2. Dates arrive as `2026-08-12T20:02:31`; trim to the day unless the time matters.
3. Print the final DQL in a plain code block so the user can iterate.
4. Offer more results (`size`, `offset`) or a refinement.

To read one article in full, hand its URL to `extract` rather than pulling `text` out of a record.
