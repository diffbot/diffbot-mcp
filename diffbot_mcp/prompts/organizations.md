# Diffbot Organization Search

Find organizations in the Diffbot Knowledge Graph. This is `type:Organization` DQL with the company-research levers pre-selected: industry taxonomy, headquarters vs. offices, headcount and revenue bands, funding, and ownership.

**Prefer the `search_organizations` tool.** It builds the query described below from typed parameters, resolves `industry` against the OrganizationCategory taxonomy, handles `similar_to` and `near`, and returns the DQL it ran. Drop to `dql` only when the shape is outside those parameters, and use `dql_probe` to compare variants first.

Parameter notes that are not in the schema:

- `industry` is the best first filter. Free text is resolved against the taxonomy; ambiguous text returns `candidates` instead of rows, so pick one and call again. It matches the primary category only unless `primary_industry=False` (see the categories note below).
- `descriptors` is the free-text niche filter and combines with `industry` ("Food Companies" + "plant-based"). An `industry` value that resolves to nothing is matched as a `descriptors` tag instead ("GPU", "cold chain"), and the response says so in `notes`.
- `name` matches exactly (`strict:`) and falls back to contains-matching only when the exact form has zero hits, flagged in `notes`. A homepage domain in `name` ("tesla.com") matches `homepageUri` instead and is the most reliable way to pin one company. Large companies have duplicate records; the top row is the primary one.
- `city`/`region`/`country` are the headquarters. For "has an office in" use raw DQL with the plural `locations.city.name` form. `near` takes a place and an optional radius ("Austin 30mi", default 15km) for "near" or "within X miles".
- `revenue`, `employees`, and `founded` are range strings: `"10M-75M"`, `"500+"`, `"<20"`, `">=1B"`, `"2015-2020"`, a single value for exactly that. Revenue is a plain number in the company's reporting currency.
- `name` and `city` accept a list for OR. `part_of` is index or group membership ("S&P 500", "Dow Jones Industrial Average"); `subsidiary` finds the parent of a named company; `investor` and `acquired_by` take the backer or acquirer and return its portfolio or acquisitions; `series` keeps rows as companies that raised that round (use `search_deals` when the rows should be the rounds themselves).
- `similar_to` returns exactly `size` lookalikes ranked by similarity; other filters narrow within that ranking and `hits` is null.
- Leave `sort` unset unless the ordering is the question; the default importance ranking is better. `facet` turns the call into buckets (`size` becomes the bucket count).
- To deliver the results as a CSV file, pass the `dql` string this tool returns to `export_csv` with a `path`; it exports the whole result set, not a page.

**The organizations/deals boundary is the row shape.** If the rows the user wants are companies, this workflow owns it, including "everything Microsoft acquired", which is a list of target companies. If the rows are transactions, investments, or deals, use the deals prompt and `search_deals`. Both filter on the same `acquiredBy` and `investments` fields; what differs is what ends up in the table.

Sibling prompts: news (articles), people, places (geography), deals (deals as rows). Use `dql` for products or anything outside these shapes.

## Step 1 — build the query

Every query starts `type:Organization`. Layer the clauses below.

### Industry — start here

`categories.name` is almost always the best first filter. A company carries several categories and only one is primary; the loose `categories.name:"X"` form matches any of them, which is how hospitals and sports leagues show up in a software list. `search_organizations` therefore filters on the primary category (`categories.{name:"X" isPrimary:true}`) unless `primary_industry=False`; use the loose form when recall matters more than precision, since a company whose primary category is a sibling ("Video Game Companies") drops out of the primary-only form. Look up the exact string before using it in raw DQL; the taxonomy is title-cased and often plural (`"Semiconductor Companies"`, `"Artificial Intelligence Software"`):

```
dql_ontology(action="taxonomy", name="OrganizationCategory", search="<regex>")
```

```
type:Organization categories.name:"Semiconductor Companies" isPublic:true
```

When no category fits the niche, fall back to **`descriptors`**, short free-text capability tags:

```
type:Organization descriptors:"GPU"
type:Organization descriptors:"mexican restaurant" near(type:Organization name:"Diffbot")
```

### Location — singular is headquarters, plural is any office

| Use | Meaning |
| --- | --- |
| `location.city.name:"Berlin"` | **Headquartered** in Berlin, the primary location |
| `locations.city.name:"Berlin"` | Has *an* office in Berlin, HQ anywhere (`any_office=true`) |

Prefer the singular form for "companies in X". The same split applies to `name`/`allNames`, `description`/`allDescriptions`, `homepageUri`/`allUris`.

`location` is a `Location` composite: `.city.name`, `.region.name`, `.country.name`, `.subregion.name`, `.metroArea.name`, `.street`, `.postalCode`, `.latitude`, `.longitude`.

### Field reference

| Field | Type | Notes |
| --- | --- | --- |
| `name` / `fullName` | String | Add `strict:` for exact match: `strict:name:"Apple Inc"` |
| `categories` | list | `categories.name`, OrganizationCategory taxonomy |
| `descriptors` | list of String | Free-text capability tags |
| `homepageUri` | URL | Primary domain |
| `nbEmployees` | Integer | Also `nbEmployeesMin`, `nbEmployeesMax`, `nbEmployeeRanges` |
| `revenue.value` / `.currency` | Amount | Also `yearlyRevenues`, `quarterlyRevenues` |
| `isPublic` | Boolean | |
| `ipo` | IPO composite | |
| `stock` | Stock composite | Ticker and exchange |
| `foundingDate` | DDate | `foundingDate>="2020-01-01"` |
| `ceo` | LinkedEntity (Person) | `ceo.name`; absent from the default payload, request with `get:` |
| `founders` | list | `founders.name`; absent from the default payload, request with `get:` |
| `investments` | list | `investments.investors.name`, `investments.series`, `investments.amount.value`, `investments.date` |
| `totalInvestment` | Amount | `totalInvestment.value>100000000` |
| `nbUniqueInvestors` | Integer | |
| `isAcquired` | Boolean | |
| `acquiredBy` | list | `acquiredBy.name` (acquirer), `acquiredBy.amount.value`, `acquiredBy.date` |
| `location` / `locations` | Location | See above |
| `nbLocations` | Integer | |

### Matching a company by name — use `strict:`

`name:"…"` is a **contains** match, and company names are short and repetitive, so it over-matches badly:

| Query | Hits |
| --- | --- |
| `type:Organization name:"Apple"` | 68,068 |
| `type:Organization strict:name:"Apple"` | 1,426 |
| `type:Organization strict:name:"Apple Inc."` | 1 |

When the user names a specific company, reach for `strict:` first (what `search_organizations` does, falling back to contains only on zero hits) and in raw DQL fall back to the contains form only if strict returns nothing. When they mean a *category* of company ("apple growers"), contains is correct, but prefer `categories.name` or `descriptors` for that. The homepage domain (`name="apple.com"`) is the most reliable way to pin one company.

`strict:` still leaves duplicates: the KG holds several records for large companies (subsidiaries, regional entities, stale dupes). The default ranking puts the primary record first; take the top row when you need "the" company.

### `near` — companies within a radius of a place

Default radius 15km; override with `mi` or `km`. `near` resolves a single anchor entity: if the inner query matches several, only the first is used.

```
type:Organization categories.name:"Semiconductor Companies" near(type:Place name:"Austin", 30mi)
type:Organization descriptors:"mexican restaurant" near(type:Organization name:"Diffbot")
```

Use this rather than `location.city.name` when the user says "near", "around", or "within X miles"; city-name matching misses the surrounding metro.

### `similarTo` — find companies like this one

Organization-only. Give it an anchor and it returns a ranked list of similar companies: the right tool for "competitors of X", "companies like X", or building a lookalike list.

```
type:Organization similarTo(name:"OpenAI")
type:Organization similarTo(type:Organization homepageUri:"walmart.com")
```

The anchor is a subquery: `name:"…"` is the short form, or use a fuller one like `type:Organization homepageUri:"…"` when the name is ambiguous. `search_organizations(similar_to=...)` uses the domain form when the value looks like a domain.

**Other clauses compose and narrow within the similarity search.** They are not a post-filter on the top N, so adding a filter surfaces companies deeper in the ranking rather than just deleting rows:

```
type:Organization similarTo(name:"OpenAI") location.country.name:"United States"
type:Organization similarTo(name:"OpenAI") isPublic:true
```

**It behaves differently from a normal query in two ways:**

- It returns *exactly* `size` results, ranked by similarity. The `hits` field mirrors the size you asked for, so there is no meaningful total; asking for more results just goes further down the ranking.
- **`dql_probe` cannot validate it.** A probe runs at size 0, and `similarTo` at size 0 returns 0, which looks like "no matches" but means nothing. Skip Step 2 for `similarTo` queries and validate with a small fetch (`size=10`) instead.

### Subqueries — co-constraining nested fields

Use `{}` when two conditions must hold on the *same* nested object:

```
type:Organization investments.{series:"Series A" date>="2026-01-01"}
```

Without `{}` those are independent: an org with *any* Series A and *any* 2026 round would match, even if they are different rounds. `{}` only works on composite-typed list fields.

### Worked examples

```
type:Organization categories.name:"Semiconductor Companies" isPublic:true
type:Organization categories.name:"Artificial Intelligence Software" location.city.name:"San Francisco"
type:Organization investments.investors.name:"Sequoia Capital"
type:Organization nbEmployees>1000 revenue.value>1000000000
type:Organization isAcquired:true acquiredBy.name:"Microsoft"
type:Organization categories.name:"Artificial Intelligence Software" investments.{amount.value>50000000 date>="2026-01-01"}
type:Organization range:nbEmployees:10-100 location.country.name:"Germany" descriptors:"SaaS"
type:Organization similarTo(name:"OpenAI") location.country.name:"United States"
```

**Distribution questions** ("what industries dominate Berlin startups?") are facets, not row lists: `search_organizations(city="Berlin", facet="categories.name", size=25)`, or in raw DQL:

```
type:Organization location.city.name:"Berlin" facet:categories.name
```

Facets require `size` ≥ 1, and `size` sets the **number of buckets** returned, not rows.

**Leave the sort off unless the user asked for an ordering.** The default ranking already bakes in relevance and prominence, and an explicit sort overrides it, usually for the worse. Measured: `homepageUri:"openai.com"` unsorted returns **OpenAI**, while `revSortBy:nbEmployees` returns *"OpenAI for Developers"*; `anthropic.com` unsorted returns **Anthropic**, sorted returns *"Claude Builder Club"*.

## Step 2 — probe before committing

```
dql_probe(queries=[
  'type:Organization descriptors:"GPU" location.country.name:"United States"',
  'type:Organization categories.name:"Semiconductor Companies" location.country.name:"United States"',
  'type:Organization categories.name:"Semiconductor Companies" location.country.name:"United States" isPublic:true'
])
```

Zero hits usually means a mistyped category; re-check with `dql_ontology`. A hit count equal to the bare `type:Organization` count means a field path was silently ignored (the tools flag this in `notes`).

**Do not probe `similarTo` queries**; validate those with a small fetch instead.

## Step 3 — fetch and display

`search_organizations` returns rows with Company, Description, Employees, Revenue, Currency, City, Country, Website, Public, and Id. The equivalent raw call is:

```
dql(query="<DQL>", size=50, fields="name,Company;descriptors,Description;nbEmployees,Employees;revenue.value,Revenue;location.city.name,City;location.country.name,Country;homepageUri,Website;isPublic,Public")
```

`fields` renders only the **primary** value of list/composite fields: one investor, one location. Use `dql(query="<DQL> get:name,investments", format="json")` when the user needs full lists; the default JSON payload is not the full entity, and a missing field usually means it was not requested rather than that the data is absent.

**Display**

1. Render a markdown table sized to the question: company, one-line descriptor, headcount, HQ, website.
2. Revenue arrives as a plain number; format it as `$100M` for the user, with its currency.
3. Print the final DQL in a plain code block.
4. Offer more rows (`size`, `offset`) or a refinement.

For `similarTo` results, present them as a ranked list and say what the anchor was: the ordering is the answer, and there is no total count to report.
