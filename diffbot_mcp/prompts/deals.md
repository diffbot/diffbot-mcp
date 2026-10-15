# Diffbot Deal Search

Find funding rounds, acquisitions, and transactions in the Diffbot Knowledge Graph. Deals live in two places: as standalone `Investment`/`Transaction` records, and as fields hanging off the `Organization` involved. **Choosing the right one is the whole skill**; see the routing table below.

**Prefer the `search_deals` tool.** Its `kind` parameter applies the routing table, an `industry` filter is moved to the company side automatically, amounts and dates are normalized, and it returns the DQL it ran. Drop to `dql` only when the shape is outside those parameters.

Parameter notes for `search_deals` that are not in the schema:

- `kind="funding"` reads Investment records; `"acquisitions"` reads the `acquiredBy` field on the acquired company because standalone Acquisition records are empty stubs; `"any"` reads every Transaction.
- `amount` is a range string (`"50M+"`, `"1M-10M"`, `"<=500K"`) in `currency` (default USD); values are not normalized across currencies. A blank amount in a row means undisclosed and "Series Unknown" is a real series value.
- `series` is contains-matched, so "Series A" also covers "Series A-1". An `industry` filter is applied on the company side, since a deal's investee carries no categories.
- Leave `sort` unset unless the ordering is the question; unsorted results surface the headline deals. `facet` buckets by series, investors, or amount, and `size` becomes the bucket count.
- To deliver the results as a CSV file, pass the `dql` string this tool returns to `export_csv` with a `path`; it exports the whole result set, not a page.

**First, check the row shape.** This workflow is for when the rows are deals: target, acquirer/investors, amount, date, series. If the rows the user wants are *companies* ("everything Microsoft acquired", "companies Sequoia backed"), use the organizations prompt and `search_organizations`; it filters on the same `acquiredBy` and `investments` fields but presents companies.

Sibling prompts: organizations (companies as rows), news, places. Use `dql` for anything outside these shapes.

## Step 1 — route the question

| The user asks about | Query | `kind` | Why |
| --- | --- | --- | --- |
| Funding rounds by date, size, series, or investor | `type:Investment` | `funding` | One row per round, with amount, series, date, investors |
| Deals in an **industry / location / company-size** segment | `type:Organization` + `investments.{...}` | `funding` + `industry` | Industry lives on the company, not the deal; see the gap below |
| Acquisitions ("who bought X", "everything Microsoft acquired") | `type:Organization isAcquired:true acquiredBy.name:"…"` | `acquisitions` | `Acquisition` records are name-only stubs |
| Any money movement, not just equity | `type:Transaction` | `any` | Superset: `Investment` and `Acquisition` are both subtypes |

### The industry gap — read this before filtering deals by sector

`investee` on an `Investment` is a `LinkedEntity`, which carries only `name`, `types`, `summary`, `image`, `diffbotUri`. It has **no `categories`**, so `investee.categories.name:"…"` returns zero; it looks like "no such deals" rather than "no such field."

Flip the query to the company side instead, and use `{}` so the round's conditions co-constrain:

```
type:Organization categories.name:"Artificial Intelligence Software" investments.{amount.value>50000000 date>="2026-01-01"}
type:Organization categories.name:"Artificial Intelligence Software" investments.{series:"Series A" date>="2026-01-01"}
```

Without `{}` the clauses are independent: a company with *any* $50M round and *any* 2026 round matches, even if they are different rounds. `search_deals(kind="funding", industry=..., ...)` builds this form and lists only the rounds that match.

## Step 2 — field reference

**`type:Investment`** — a funding round.

| Field | Type | Notes |
| --- | --- | --- |
| `investee` | LinkedEntity (Organization) | `investee.name`, the company raising |
| `investment.series` | String | `"Series A"`, `"Series B"`, `"Series Unknown"`, … |
| `investment.amount.value` | Float | Raw number; pair with `.currency` |
| `investment.amount.currency` | String | `"USD"`, … **Always filter or display currency**; values are not normalized |
| `investment.date` | DDate | `investment.date>="2026-01-01"` |
| `investment.investors` | list of LinkedEntity | `investment.investors.name` |
| `date`, `name`, `amount` | | Inherited from `Transaction`; `date` mirrors `investment.date` |

**`type:Transaction`** — any transaction; `Investment` and `Acquisition` are subtypes (filter with `types:"Acquisition"`).

| Field | Notes |
| --- | --- |
| `payee` | LinkedEntity (Organization), receiving side |
| `payers` | list of LinkedEntity, paying side |
| `amount.value` / `amount.currency` | |
| `date` | DDate |
| `name` | e.g. `"Venture Round - OpenAI"` |

**`Organization.acquiredBy`** — the reliable path for M&A.

| Field | Notes |
| --- | --- |
| `acquiredBy.name` | The acquirer |
| `acquiredBy.amount.value` | Deal size |
| `acquiredBy.date` | |
| `isAcquired` | Boolean flag on the target |

Also on Organization: `investments` (full round history), `totalInvestment.value`, `nbUniqueInvestors`.

**Sorting.** There *is* a useful default: unsorted, `investment.investors.name:"Sequoia Capital"` returns the headline rounds (OpenAI $122B, Anthropic $50B, OpenAI $40B), whereas `revSortBy:investment.date` returns whatever closed most recently regardless of size. Leave the sort off unless the ordering is the question, then use:

```
revSortBy:investment.date         # newest rounds first  (sort="newest")
revSortBy:investment.amount.value # largest rounds first (sort="largest")
```

### Worked examples

```
type:Investment investment.investors.name:"Sequoia Capital" revSortBy:investment.date
type:Investment investment.series:"Series A" investment.date>="2026-01-01" revSortBy:investment.amount.value
type:Investment investment.amount.value>100000000 investment.amount.currency:"USD" revSortBy:investment.date
type:Investment investee.name:"OpenAI" revSortBy:investment.date
type:Organization isAcquired:true acquiredBy.name:"Microsoft" revSortBy:acquiredBy.amount.value
type:Organization categories.name:"Semiconductor Companies" investments.{amount.value>100000000 date>="2025-01-01"}
type:Transaction types:"Acquisition" sortBy:date
```

**Note on `type:Acquisition`.** These records exist (~209k) but are near-empty stubs, typically just a `name` like `"Reliance Motor Car Company acquired by General Motors"`, with `date`, `amount`, `payee`, and `payers` all null. Don't build a deal table from them; route acquisitions through `Organization.acquiredBy`.

### Distribution questions are facets, not row lists

"What stage is most funding at?", "which investors are most active?": aggregate instead of listing, with `search_deals(since="2026-01-01", facet="series", size=12)` or in raw DQL:

```
type:Investment investment.date>="2026-01-01" facet:investment.series
```

Returns buckets like `Seed 4568 · Grant 3796 · Series A 2061 · Debt Financing 2015 · Pre Seed 1965`. Also useful: `facet:investment.investors.name` (most active investors), `facet:investment.amount.value` (auto-bucketed deal sizes).

Facets need `size` ≥ 1, and `size` sets the **number of buckets**, not rows. A facet response has `value`/`count` per bucket, not entities, so don't use it when the user wants individual deals.

**`or()` is usually unnecessary on `series`.** `investment.series:"Series A"` is a contains match and already covers `"Series A-1"`; `or("Series A","Series A-1")` returns the identical count. Reach for `or()` only across genuinely different strings.

## Step 3 — probe before committing

```
dql_probe(queries=[
  'type:Investment investment.series:"Series A" investment.date>="2026-01-01"',
  'type:Investment investment.amount.value>100000000',
  'type:Organization categories.name:"Artificial Intelligence Software" investments.{amount.value>50000000 date>="2026-01-01"}'
])
```

Zero hits on an `investee.<something>` path almost always means the field doesn't exist on `LinkedEntity`; re-read the gap above rather than loosening the filter.

## Step 4 — fetch and display

`search_deals` returns rounds as Company, Round, Amount, Currency, Date, Lead Investor, Id, and acquisitions as Target, Acquirer, Amount, Currency, Date, Industry, Id. The equivalent raw calls:

```
dql(query="<DQL>", size=50, fields="investee.name,Company;investment.series,Round;investment.amount.value,Amount;investment.amount.currency,Currency;investment.date.str,Date;investment.investors.name,Lead Investor")
dql(query="<DQL>", size=50, fields="name,Target;acquiredBy.name,Acquirer;acquiredBy.amount.value,Amount;acquiredBy.date.str,Date;categories.name,Industry")
```

A column spec renders only the **primary** value of a list field, so the row shows one investor even when a round had thirty. When the full investor list matters, read the records as JSON: `dql(query="<DQL> get:investee,investment", format="json")`. The industry-routed form of `search_deals` already lists every investor per matching round.

**Display**

1. Render a markdown table: **Date | Company | Round | Amount | Investors**.
2. **Reformat amounts.** Values arrive as plain numbers (`300000000`); show `$300M`. Never present a bare number without its currency.
3. Dates are already trimmed to `2026-07-23`.
4. Blank amount means the round was reported without a disclosed size; label it "undisclosed", not `0`.
5. `"Series Unknown"` is a real value in the data, not a lookup failure.
6. Print the final DQL in a plain code block and offer more rows (`size`, `offset`) or a refinement.
