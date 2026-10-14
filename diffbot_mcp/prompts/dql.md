# Diffbot Knowledge Graph Search (DQL)

Query the Diffbot Knowledge Graph via the DQL API. Translate the user's plain-text request into a DQL query, validate it, execute it through the `dql` tool, and display formatted results.

This is the general-purpose layer beneath the typed tools. **Reach for `search_news`, `search_organizations`, `search_people`, `search_places`, or `search_deals` first** when the question fits one of those shapes; each returns the DQL it ran, which can be refined here. Use raw DQL for any other entity type or query shape: products, patents, brands, job posts, cross-entity queries, and facet aggregations the typed tools do not cover.

## The tools

```
dql_ontology(action="types" | "composites" | "enums" | "taxonomies")     # list names
dql_ontology(action="fields", name="Organization", search="<regex>")    # entity-type or composite fields
dql_ontology(action="taxonomy", name="OrganizationCategory", search="<regex>")  # taxonomy values
dql_ontology(action="enum", name="Language")                            # enum values
dql_ontology(action="search", search="<regex>")                         # fallback: any name anywhere in the ontology
dql_probe(queries=["<Q1>", "<Q2>", ...])                                # parallel hit counts for variants
dql(query="<DQL>", size=N, offset=K, fields="name,Name;...", format="csv" | "json", hits_only=false)
```

No initialization step is needed: the ontology is fetched once per server and cached for a day.

## Step 1 — construct and validate the DQL query

Translate the natural-language request into a DQL string. Examples:

```
type:Organization name:"Diffbot"
type:Product site:"ikea.com"
type:Organization location.city.name:"San Francisco" investments.investors.name:"Andreessen Horowitz"
type:Article categories.name:"War and Conflicts" tags.label:"Ethiopia" date>="2020-11-01" date<="2022-11-30" sortBy:date
type:Article quotes.speaker:"Donald Trump" sortBy:date
```

Every DQL string starts with `type:`. Start with common types (`Organization`, `Person`, `Article`, `Product`) and reach for a more specific entity type via `dql_ontology(action="types")` if those don't fit.

**Look up fields before using them.** Independent ontology lookups should be issued as parallel tool calls in a single message so they don't queue.

```
dql_ontology(action="fields", name="Organization", search="location")   # entity-type fields, regex-filtered
dql_ontology(action="fields", name="Location")                          # composite fields
dql_ontology(action="taxonomy", name="OrganizationCategory", search="semiconductor")
dql_ontology(action="enum", name="Language")
dql_ontology(action="search", search="asset")                           # when you don't know where a field lives
```

`fields` accepts both entity-type names (e.g. `Organization`) and composite names (e.g. `Location`, `Employment`); it auto-routes. Each result carries the field's type and its `isList` / `isComposite` / `isEnum` flags.

### Operators

| Operator | Syntax | Example |
| --- | --- | --- |
| Contains (string) | `field:"value"` | `name:"Diffbot"` |
| Regex | `re:field:"pattern"` | `re:name:"^Apple"` |
| Exact match | `strict:field:"value"` | `strict:name:"Apple Inc"` |
| Greater than | `field>N` | `nbEmployees>500` |
| Less than | `field<N` | `nbEmployees<10000` |
| Not equals | `field!=value` | `gender!="MALE"` |
| Max | `max:field:N` | `max:capitalization.value:1000000` |
| Min | `min:field:N` | `min:capitalization.value:1000000` |
| Range | `range:field:N-M` | `range:nbEmployees:10-100` |
| AND (implicit) | space-separated | `type:Organization isPublic:true` |
| OR | `or(v1,v2)` | `categories.name:or("Software companies","Hardware companies")` |
| NOT | `not(condition)` | `not(isPublic:true)`, `not(has:parentCompany)` |
| Near (proximity) | `near(name:"Place")` | `near(name:"San Francisco", 10mi)` |
| Similar to | `similarTo(…)` | `similarTo(type:Organization homepageUri:"walmart.com")` |
| Has (field exists) | `has:field` | `has:sicClassification` |
| Get (include fields) | `get:field` | `has:subsidiaries get:subsidiaries` |
| Get (exclude fields) | `get:!field` | `get:!nbEmployeesMax,!phoneNumbers` |
| Facet (aggregate) | `facet:field` | `facet:locations.city.name` |
| Facet with ranges | `facet[a:b,b:c]:field` | `facet[100:500,500:1000]:nbEmployees` |
| Facet with values | `facet["a","b"]:field` | `facet["Austin","Seattle"]:locations.city.name` |
| Sort ascending | `sortBy:field` | `sortBy:nbEmployees` |
| Sort descending | `revSortBy:field` | `revSortBy:nbEmployees` |

### `field:"value"` is CONTAINS, not equals

This is the root of most over-matching. `name:"Apple"` returns 68,068 organizations; `strict:name:"Apple"` returns 1,426; `strict:name:"Apple Inc."` returns 1. Whenever the user names a specific entity, start with `strict:`.

Two consequences worth internalizing:

- **`or()` is redundant when one string contains another.** `investment.series:"Series A"` already matches `"Series A-1"`, so `or("Series A","Series A-1")` returns an identical count.
- **`or()` is mandatory when the spellings genuinely differ.** An abbreviation is not a substring of its expansion: `employments.title:"Chief Executive Officer"` finds 521,798 people, while `or("Chief Executive Officer","CEO")` finds 2,620,747.

### Subquery syntax for nested fields

Use `{}` to co-constrain multiple conditions on the same nested object:

```
type:Person employments.{employer.name:"Diffbot" isCurrent:true}
```

Without `{}` the two conditions are independent (matches a person with *any* Diffbot employment AND *any* current employment, possibly different ones). Subqueries only work on composite-typed list fields; check the ontology to confirm. Attempting `{}` on a non-nested field returns: `Nested expression over non-nested list field [...] is not allowed`.

### Singular vs plural fields (primary vs all/historical)

Many entity types expose both a singular and plural form of the same composite field. The singular form is the primary/current value; the plural is the full list including historical entries.

| Singular (primary) | Plural (all/historical) |
| --- | --- |
| `location` | `locations` |
| `name` | `allNames` |
| `description` | `allDescriptions` |
| `homepageUri` | `allUris` |

Prefer the singular form when you want to filter on the entity's *primary* fact. To find companies headquartered in the US, use `location.country.name:"United States"`, not `locations.country.name:"United States"`, which matches any org with a US office (even foreign-headquartered companies with a US branch).

### regex operator

Regex is slow and compute heavy. Avoid if possible. If it must be used, stick to short, simple, and speedy regex matches.

### similarTo operator (Organization only)

```
type:Organization similarTo(name:"OpenAI")
```

Returns a ranked list of exactly `size` similar companies; `hits` mirrors the size you requested rather than a true match count. Other clauses compose and narrow within the similarity search. **Do not validate it with `dql_probe`** (see Step 2); use a small `dql(size=10)` instead.

### near operator

Finds entities within a given distance of a Place (default 15km; specify with `mi` or `km`). `near` operates on a single entity; if the subquery returns multiple, only the first is used.

```
type:Organization near(type:Place name:"San Francisco")
type:Organization descriptors:"mexican restaurant" near(type:Organization name:"Diffbot")
```

### get operator

`get:<field,field2>` restricts the response payload to specified fields (and descendants). It only matters with `format="json"`; the csv `fields` parameter selects its own columns.

**The default payload is not the full entity; `get:` also *adds* fields.** A plain `format="json"` fetch returns a trimmed record, and many filterable fields are simply absent from it. `type:Organization strict:name:"Tesla"` returns no `ceo` and no `founders` key at all; add `get:name,ceo,founders` and you get `ceo=Elon Musk`, `founders=JB Straubel, Martin Eberhard, Ian Wright, Marc Tarpenning, Elon Musk`. The same is true of `Place.population` and `Place.isPartOf`.

So: **a missing or null field in a JSON record usually means you didn't request it, not that the data is absent.** Confirm with `has:<field>` before concluding a field is unpopulated. The csv `fields` parameter requests its columns automatically, so only JSON reads need `get:`.

### Facet queries

Use facets for aggregation/distribution questions ("what industries are common among Berlin startups?", "how are employees distributed across company sizes?"). A facet response has `value`, `count`, and `query` (the callback query for that bucket) per bucket, *not* entity records. Not appropriate when the user wants individual entity rows.

- Numeric/date fields are auto-bucketed; override with `facet[a:b,b:c]:field`
- Date fields accept `day`, `week`, or `month` interval specifiers
- Restrict to specific values with `facet["v1","v2"]:field`
- `size` is the number of buckets and must be ≥ 1

### Entity-specific tips

**Article**: use `search_news` and the news prompt, which own this entity type and its defaults. Only reach for `type:Article` here when articles are one leg of a larger cross-entity query. `categories.name` narrows by topic, `tags.label` by mentioned entity, and `sortBy:date` orders newest-first.

**Organization**: use `search_organizations`. `categories.name` is usually the best starting point.

**Person**: use `search_people`. Every employment condition goes inside one `employments.{}`.

**Place / Investment / Transaction**: use `search_places` and `search_deals`; the places and deals prompts document field paths and traps that are easy to get wrong from scratch.

**Don't add a sort unless the ordering is the question.** For non-Article types the default ranking already encodes relevance and prominence, and an explicit sort overrides it, measurably for the worse (`homepageUri:"openai.com"` unsorted → OpenAI; with `revSortBy:nbEmployees` → "OpenAI for Developers"). Articles are the deliberate exception and default to `sortBy:date`.

## Step 2 — probe variants in parallel before committing

Before running the final query, probe candidate variants for hit counts to verify the query is well-shaped (not too broad, not too narrow). `dql_probe` fires all variants concurrently:

```
dql_probe(queries=[
  'type:Organization descriptors:"GPU" location.country.name:"United States"',
  'type:Organization descriptors:"GPU" location.country.name:"United States" categories.name:"Semiconductor Companies"',
  'type:Organization descriptors:"GPU" location.country.name:"United States" isPublic:true'
])
```

This is the right way to test query selectivity, far faster than running them serially. A query the API rejects reports its error in place without failing the others.

Two failure signatures: **zero hits** means the value is wrong for the field or the concept is not modelled; a **hit count equal to the bare `type:X` count** means a field path was misspelled and silently ignored.

**Exception: `similarTo` queries cannot be probed.** A probe requests size 0, and `similarTo` reports `hits` equal to the requested size, so it always returns 0 here no matter how good the query is. Skip this step for `similarTo` and validate with `dql(size=10)`.

**Never probe an unfiltered `type:Article`**; the article index is large enough that it times out.

## Step 3 — fetch and display

**Choose the format based on intent:**

- **Final display to the user** (markdown table, no downstream processing): `format="csv"`, the default. Rows carry only the requested columns.
- **Further analysis** (reading a list field in full, feeding another tool): `format="json"`, with `get:` in the query to keep records small.

```
dql(query="<DQL>", size=25, fields="name,Name;nbEmployees,Employees;homepageUri,Website;location.city.name,City;location.region.name,State;isPublic,Public")
dql(query="<DQL> get:name,investments", size=25, format="json")
```

`fields` notes:
- Format is `<field-path>,<Display Name>` per pair, `;`-separated
- Use lowercase field paths (`name`, not `Name`); the first token is the actual DQL field path
- For list/composite fields, only the primary value is rendered; JSONPath such as `$.employments[0].title` selects a specific element
- Every response reports the total `hits`, `offset`, and `returned` alongside the rows

Refrain from reading `text` or `content` from `type:Article` records. `summary` is more appropriate.

**Final display**

1. Always print the final DQL string in a plain code block so the user can copy and iterate.
2. For csv: render the rows as a markdown table with columns appropriate to the entity type.
3. Offer pagination (`size`, `offset`) or query refinement.

## Performance discipline

- **One ontology lookup per tool call is wasteful.** When you need to inspect multiple fields or types, issue the `dql_ontology` calls in parallel in the same message.
- **Never loop `dql(hits_only=true)` serially.** Use `dql_probe`, which parallelizes internally, for any N-variant hit-count check.
- The ontology is cached server-side; there is nothing to initialize or refresh mid-session.
