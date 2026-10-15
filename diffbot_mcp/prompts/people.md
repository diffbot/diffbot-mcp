# Diffbot People Search

Parameter notes for `search_people` that are not in the schema:

- Everything about one job (`title`, `employer`, `employer_industry`, `employer_employees`, `employer_country`, `job_category`, `job_location`) is co-constrained inside one `employments.{}`; `current=False` drops `isCurrent:true` for career history.
- `job_category` is the EmploymentCategory taxonomy (occupation groups such as "Business", "Engineering, IT and Software Development", "Religion"); `employer_industry` is the employer's OrganizationCategory. Free text is resolved and ambiguous text returns `candidates`.
- `job_location` and `school_location` take a city or a country and match either (`or(location.city.name:X, location.country.name:X)`); `city`/`region`/`country` are the person's residence.
- `employer_employees` and `net_worth` are range strings (`"<=50"`, `"100-500"`, `"1B"`). `name` and `city` accept lists for OR.
- `language` is the Language enum; dialects that are not values ("Bavarian", "Deccan") return no candidates, so fall back to the parent language.
- `leadership_of` reads `ceo` and `founders` from the Organization record and ignores other filters; prefer the homepage domain.
- To deliver the results as a CSV file, pass the `dql` string this tool returns to `export_csv` with a `path`; it exports the whole result set, not a page.


Find people in the Diffbot Knowledge Graph. This is `type:Person` DQL with the people-research levers pre-selected: employment history, employer industry, education, skills, and location.

**Prefer the `search_people` tool.** It puts every employment condition inside one `{}`, expands C-suite titles to both spellings, resolves `employer_industry` against the OrganizationCategory taxonomy, renders the job that *matched* rather than the person's primary one, and returns the DQL it ran. `leadership_of` answers "who is the CEO / who founded X" from the curated Organization fields. Drop to `dql` only when the shape is outside those parameters.

**Coverage is limited to people with a public online presence.** See the note at the end before reporting an empty or partial result.

**Row shape decides the workflow.** If the rows are people, this owns it, including "who runs Nvidia". If the rows are companies ("companies whose CEO is a woman"), use the organizations prompt and `search_organizations`. Sibling prompts: news, places, deals. Use `dql` for anything outside these shapes.

## Step 1 — the subquery rule comes first

`employments` is a **list** of jobs. Conditions written separately are matched against *different* jobs, which silently inflates results. Co-constrain them with `{}`:

```
✗ type:Person employments.{title:"Chief Executive Officer" isCurrent:true} employments.employer.categories.name:"Semiconductor Companies"
✓ type:Person employments.{title:"Chief Executive Officer" isCurrent:true employer.categories.name:"Semiconductor Companies"}
```

Measured: **3,457 hits vs 399**. The loose form matches anyone who was ever a CEO *somewhere* and also worked at *some* semiconductor company, a different job. Nearly 9 out of 10 of those rows are wrong.

**Put every condition about one job inside one `{}`.** The same applies to `educations`, `colleagues`, and `locations`. `search_people` does this for you.

Add `isCurrent:true` whenever the user means the present ("who runs X", "current CTO"); omit it for history ("everyone who has worked at X"). This is the `current` parameter, default true.

## Step 2 — the levers

### Employer industry resolves — this is the headline capability

`employments.employer` is a full `Organization` link, so you can filter people by their employer's industry, size, or location:

```
type:Person employments.{title:"Chief Technology Officer" isCurrent:true employer.categories.name:"Biotechnology Companies"}
type:Person employments.{isCurrent:true employer.location.country.name:"Germany" employer.nbEmployees>1000}
```

Look up category strings first in raw DQL; they are title-cased and usually plural: `dql_ontology(action="taxonomy", name="OrganizationCategory", search="<regex>")`.

(Contrast with deals, where `investee` is a bare `LinkedEntity` with no categories. The employer link is richer; the deals trap does not apply here.)

### Field reference

| Field | Type | Notes |
| --- | --- | --- |
| `name` / `allNames` | String | `nameDetail.firstName`, `.lastName`, `.nicknames` |
| `employments` | list | `.title`, `.employer.name`, `.isCurrent`, `.from`, `.to`, `.description`, `.location`, `.categories.name` (EmploymentCategory taxonomy), `.technologies.name` |
| `educations` | list | `.institution.name`, `.major.name`, `.degree.name`, `.isCurrent`, `.hasDroppedOut`, `.from`, `.to` |
| `skills` | list | `skills.name`, free-form skill entities |
| `location` / `locations` | Location | Singular is primary residence; same HQ-vs-offices split as Organization |
| `nationalities` | list | `nationalities.name` |
| `gender` | enum | `gender:"Female"` works. Values: Male, Female, Transgender_male, Transgender_female, Bigender, Agender, Trigender, Other |
| `age`, `birthDate`, `deathDate` | | `birthPlace`, `deathPlace` are Location composites |
| `netWorth.value` | Amount | See the caveat below |
| `awards` | list | `awards.title`, `awards.date` |
| `colleagues` | list | `.colleague.name`, `.relationship`, `.isCurrent` |
| `parents`, `children`, `siblings`, `unions` | list | Family graph |
| `politicalAffiliation` | list | Linked Organization |
| `importance` | Float | Prominence; the best general "most notable first" sort |
| `wikipediaPageviews` | Integer | Attention proxy, with quarter/year and growth variants |
| `linkedInUri`, `twitterUri`, `githubUri`, `crunchbaseUri`, `homepageUri` | URL | |
| `emailAddresses`, `phoneNumbers` | list | Sparse |

`type:PersonInvestor` (~57k) is a narrower type for angels and individual investors.

**Leave the sort off unless the user asked for an ordering.** The default ranking already bakes in relevance and prominence, and an explicit sort overrides it, usually for the worse. `strict:name:"Jensen Huang"` unsorted returns the records in descending `importance` order already (97.2, then 13.6, then 10.1): the Nvidia CEO first, without asking for it.

### Worked examples

```
type:Person employments.{employer.name:"Nvidia" isCurrent:true}
type:Person employments.{title:or("Chief Executive Officer","CEO") isCurrent:true employer.categories.name:"Semiconductor Companies"}
type:Person educations.{institution.name:"Stanford University" major.name:"Computer Science"}
type:Person skills.name:"Machine Learning" location.city.name:"San Francisco"
type:Person gender:"Female" employments.{title:or("Chief Executive Officer","CEO") isCurrent:true}
type:Person nationalities.name:"France" netWorth.value>1000000000 revSortBy:netWorth.value
```

## Step 3 — probe before committing

```
dql_probe(queries=[
  'type:Person employments.{employer.name:"Anthropic" isCurrent:true}',
  'type:Person employments.{employer.name:"Anthropic" isCurrent:true title:"Engineer"}'
])
```

**Compare the `{}` and non-`{}` forms when a query has two or more employment conditions.** A large gap means the loose form is matching across different jobs and the subquery is required.

## Step 4 — fetch and display

`search_people` returns rows with Name, Title, Employer, City, Country, LinkedIn, and Id. When an employer or title filter is set, Title and Employer are the **matched** job. The equivalent raw call renders the *primary* employment instead:

```
dql(query="<DQL>", size=50, fields="name,Name;employments.title,Title;employments.employer.name,Employer;location.city.name,City;linkedInUri,LinkedIn")
```

**Display**

1. Render a markdown table: name, title, employer, location.
2. Print the final DQL in a plain code block and offer more rows (`size`, `offset`) or a refinement.

## Traps

- **A column spec renders the primary employment, not the matched one.** This is the trap most likely to make you report something false. Querying Tesla's founders through raw `dql` with `fields` returns the right *people* but shows their current jobs:

  | Name | Employer (as rendered) |
  | --- | --- |
  | Elon Musk | Neuralink |
  | Martin Eberhard | INEVIT |
  | JB Straubel | QuantumScape |

  All three genuinely co-founded Tesla; none of those employers is Tesla. `search_people` avoids this by reading the records as JSON and picking the employment that matched. In raw DQL, use `dql(query="<DQL> get:name,employments", format="json")` and pick the right entry yourself.
- **`descriptors` is effectively unpopulated on Person** (`descriptors:"venture capitalist"` → 0 hits), unlike Organization where it is a good fallback. Use `employments.title`, `skills.name`, or `summary` instead.
- **`netWorth` has extreme outliers.** The top of `revSortBy:netWorth.value` includes obviously bad values (a $96T record) and historical figures like Mansa Musa. Sanity-check the top rows before presenting, and prefer a bounded range.
- **Titles are free text, and the abbreviation is not a substring of the long form.** `title:"Chief Executive Officer"` → 521,798 current holders; adding the abbreviation, `title:or("Chief Executive Officer","CEO")` → **2,620,747**. Five times as many, and dropping them is a silent under-count, not an error. Always `or()` the abbreviation with the spelled-out form for C-suite roles (CEO, CTO, CFO, COO, CIO); `search_people` expands these automatically. Note this is the opposite of a field like `investment.series`, where `"Series A"` already contains `"Series A-1"` and `or()` changes nothing.
- **Board membership is titled "Director", not "Board Member".** At Nvidia, `title:"Board Member"` finds **5** people; `title:or("Board Member","Board of Directors","Director")` finds **904**. Never answer a board question with the naive string; it under-counts by two orders of magnitude. ("Founder" is the happy opposite: it is a substring of "Co-Founder", so it catches both without `or()`.)
- **For the CEO or founders of one specific named company, don't scan Person; read the Organization.** It is a curated field and far cleaner than title matching, which drags in same-named companies (a Person scan for Tesla founders surfaced the *band* Tesla's guitarist). `search_people(leadership_of="tesla.com")` does this; the raw form needs `get:` because these fields are absent from the default payload:
  ```
  dql(query='type:Organization homepageUri:"tesla.com" get:name,ceo,founders', size=1, format="json")
  ```
  Returns `ceo=Elon Musk`, `founders=JB Straubel, Martin Eberhard, Ian Wright, Marc Tarpenning, Elon Musk`.

  **Match on `homepageUri`, not `name`, and do not sort.** Both alternatives fail: `strict:name:"Apple"` never matches the real company (its canonical name is "Apple Inc."), and adding `revSortBy:nbEmployees` returns *"OpenAI for Developers"* for openai.com and *"Claude Builder Club"* for anthropic.com. The domain plus the default relevance ranking is correct for all of apple.com, tesla.com, openai.com, anthropic.com, airbnb.com, nvidia.com, and stripe.com.
- **Matching a specific person by name — use `strict:`.** `name:"…"` is a contains match, so a common name pulls in every partial hit. `strict:name:"Jensen Huang"` pins it (`search_people(name=...)` is strict). Person records also duplicate, so expect several rows for one individual.
- **Person records duplicate.** Same-name rows with different employers may be distinct people or the same person twice; say which when it matters.

## Coverage — public presence only

The Knowledge Graph is built from the public web, so this workflow sees people who have a public professional footprint: company pages, bylines, filings, conference listings, profiles they chose to publish. It does not surface people who have not put themselves online, and it is not a people-finder.

Two things follow, and both change how you report results:

- **Absence is not evidence.** Zero hits means "not publicly published", not that the person doesn't exist, doesn't hold the role, or isn't employed there. Say which one you actually know. Never present an empty result as a factual negative about someone.
- **Coverage is uneven, so counts are a floor and never a census.** Executives, founders, academics, authors, and public figures are dense; individual contributors, private-company staff, and people outside English-language sources are sparse. "15,227 people at Nvidia" is who is publicly documented, not the headcount; use `search_organizations` and `nbEmployees` for that.

If a request is really about locating, profiling, or compiling a dossier on a private individual, this is the wrong tool and name matching is not a substitute. Say the KG covers public professional presence and stop there.
