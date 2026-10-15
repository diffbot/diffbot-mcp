# Diffbot Place Search

Find geographic entities in the Diffbot Knowledge Graph: cities, counties/subregions, states/provinces/regions, countries, and points of interest. This is `type:Place` DQL with the place hierarchy, the right sort keys, and the known gaps already mapped.

**Prefer the `search_places` tool.** It picks the narrowest type from `kind`, searches accented names in both spellings, handles containment and proximity, flags a silently ignored filter, and returns the DQL it ran. Drop to `dql` only when the shape is outside those parameters.

Parameter notes for `search_places` that are not in the schema:

- `kind` sizes: `country` has 634 records, `region` is states and provinces, `subregion` counties, `city` cities, `administrative_area` all four, `poi` parks, landmarks and venues; `any` spans 18.5M records including 12M points of interest, so pick the narrowest.
- `name` is matched exactly in both accented and plain spelling; add `country` or `region` to pin one of many. The graph holds duplicate records for the same place (city proper vs metro), so collapse same-name rows in the same parent and say which figure was kept.
- `near` takes a place and an optional radius ("Paris 50km", default 15km). `population` is a range string ("1M+", "10000-50000").
- There is no continent field; `continent` is text-matched and over-inclusive. `facet="placeType"` shows what mix of types a name spans.
- For a CSV file, do not page rows through this tool: curl the DQL endpoint with the `dql` string this tool returns plus `format=csv`, `exportspec` (the columns from the `dql(...)` example below), and `size` set to the hit count, writing straight to disk; without a shell, show the user that GET request to run with their token. The dql prompt has the curl template.

Sibling prompts: organizations (companies, including those *located* somewhere), people, news, deals. Use `dql` for anything outside these shapes.

## Step 1 — pick the right type

**Query the narrowest type that fits.** `type:Place` matches everything including 12M points of interest; the subtypes are far more selective.

| `kind` | Type | Approx. count | Covers |
| --- | --- | --- | --- |
| `country` | `type:Country` | 634 | Countries |
| `region` | `type:Region` | 1,671 | States, provinces, top-level subdivisions |
| `subregion` | `type:Subregion` | 28,160 | Counties, districts, second-level subdivisions |
| `city` | `type:City` | 3.7M | Cities, towns, municipalities |
| `administrative_area` | `type:AdministrativeArea` | 6.5M | Superset of the four above |
| `any` | `type:Place` | 18.5M | Everything, including POIs |

Points of interest (parks, landmarks, venues) are `Place` records that are *not* administrative areas. There is no `Landmark` type in practice (`type:Landmark` returns zero); `kind="poi"` is:

```
type:Place not(types:"AdministrativeArea") descriptors:"national park"
```

`placeType` is an equivalent filter to the type name (`placeType:"Country"` ≡ `type:Country`); POIs carry `placeType:"other"`.

## Step 2 — pick the levers

### Containment — `location` or `isPartOf`

Two fields do this, and they are near-equivalent as filters:

```
type:City location.country.name:"Japan"
type:City isPartOf.name:"France"
type:Subregion location.region.name:"California"
type:Region location.country.name:"United States"
```

`location` fields: `.city.name`, `.subregion.name`, `.region.name`, `.country.name`, `.metroArea.name`, `.latitude`, `.longitude`, `.postalCode`.

`isPartOf` is the full containment chain: for Lyon it reads *Metropolitan Lyon < Rhône < France < Metropolis of Lyon < Arrondissement of Lyon*. Measured against `location`, they agree closely: French cities are 28,361 via `isPartOf` and 28,353 via `location.country.name`, and both return exactly 46 once `population>100000` is added.

Prefer `location.*` (the `country`, `region`, `subregion` parameters) when you want a specific administrative level, and `isPartOf` (the `within` parameter) when you want "contained by X at any level" or need the chain itself. **`isPartOf` is absent from the default JSON payload**; request it with `get:` or it will look empty.

### Ranking

| Field | Type | Use |
| --- | --- | --- |
| `population` | Integer | `population>1000000`, `revSortBy:population` |
| `importance` | Float (0–100) | Prominence score. Already reflected in the default ranking; sort by it only to override a different sort |
| `wikipediaPageviews` | Integer | Attention proxy; also `wikipediaPageviewsLastQuarter`, `…LastYear`, and `…Growth` variants |
| `area` | Integer | |
| `nbIncomingEdges` | Integer | How connected the entity is in the KG |

**Leave the sort off unless the user asked for an ordering.** The default ranking already bakes in relevance and prominence, and an explicit sort overrides it. `strict:name:"Springfield"` unsorted and with `revSortBy:population` return an identical top three (Missouri 169k, Massachusetts 156k, Illinois 114k): the default already surfaces the prominent one. Add a sort only when the ordering *is* the question ("largest cities by population").

### Proximity

`near(...)` resolves a single anchor entity (the first match) and filters by distance; default radius 15km, override with `mi` or `km`:

```
type:City near(type:Place name:"Paris", 50km)
type:Place not(types:"AdministrativeArea") near(type:Place name:"Yosemite", 20mi)
```

### Other fields

`name`, `allNames`, `description`, `allDescriptions`, `descriptors`, `summary`, `postalCodes`, `areaCodes`, `headOfPlace` (mayors, governors, heads of state), `image`.

### Worked examples

```
type:City location.country.name:"Japan" population>1000000 revSortBy:population
type:City location.country.name:"Germany" revSortBy:population
type:Subregion location.region.name:"California" revSortBy:population
type:Region location.country.name:"United States"
type:City near(type:Place name:"Paris", 50km) revSortBy:population
type:Place not(types:"AdministrativeArea") descriptors:"national park"
```

## Known gap — continents are not a field

There is no continent field. `countryGroup` exists but is populated on ~49 records, and an unrecognized path like `countryGroup.name:"Europe"` is **silently ignored**: it returns the unfiltered count, which looks like a working query. Watch for a hit count equal to the bare `type:` count; that is the tell, and `search_places` reports it in `notes`.

For "all countries in Europe", match the prose description and verify (`search_places(kind="country", continent="Europe")`):

```
type:Country description:"in Europe"
```

This returns ~89 hits for Europe: over-inclusive (countries merely *mentioning* Europe leak in) and it double-counts duplicate records. Filter the list yourself before presenting, and tell the user the list was text-matched rather than pulled from a continent field. With only 634 countries total, fetching all of `type:Country` and filtering against your own knowledge is also a legitimate approach.

## Step 3 — probe before committing

```
dql_probe(queries=[
  'type:City location.country.name:"France" population>100000',
  'type:City location.country.name:"France"',
  'type:Place name:"Europe"'
])
```

Two failure signatures to watch for:
- **Hit count == the bare `type:` count** → your filter path is wrong and was ignored.
- **Zero hits** → the value is wrong for this field, or the concept isn't modelled at all (continents: `isPartOf.name:"Europe"` on countries returns 0).

Place names are matched with **contains**, so `name:"Springfield"` pulls in every Springfield on earth. Add `strict:` plus a `location.country.name` or `location.region.name` filter to pin one, and `facet:placeType` to see what mix of cities, subregions, and POIs a name spans.

**Diacritics are not normalized, and coverage is inconsistent.** Query both spellings in one shot, `name:or("Kopavogur","Kópavogur")`, whenever a name could carry an accent (`search_places` does this automatically). Verified: `name:"Kópavogur"` returns 1 city and `name:"Kopavogur"` returns 0 (as do `allNames:` and a prefix), while `type:Place name:"Reykjavik"` and `"Reykjavík"` both return 44. A zero from the ASCII spelling alone is not evidence of absence; never report a place as missing from the KG until the accented form has also returned 0.

## Step 4 — fetch and display

`search_places` returns rows with Place, Population, Type, Region, Country, Importance, and Id. The equivalent raw call is:

```
dql(query="<DQL>", size=50, fields="name,Place;population,Population;location.region.name,Region;location.country.name,Country;importance,Importance")
```

**The default JSON payload is not the full entity.** A plain `format="json"` fetch of a Place returns only `name`, `description`, `placeType`, `importance`, `types`, and provenance; `population`, `location`, and `isPartOf` are all **absent**, even though you can filter on them. Ask for them explicitly: `dql(query="<DQL> get:name,population,location,isPartOf", format="json")`. A `null` field in a JSON record usually means you didn't request it, not that the data is missing.

**Display**

1. Render a markdown table with columns matched to the question: name, population, containing region/country.
2. **Deduplicate.** The KG holds multiple records for the same place (e.g. two `Tokyo` rows with different populations, city proper vs. metro). Collapse same-name rows in the same parent and say which figure you kept, or show both labelled.
3. Format populations with thousands separators; `importance` is a 0–100 prominence score, not a rank, so only show it if it is relevant.
4. Print the final DQL in a plain code block and offer more rows (`size`, `offset`) or a refinement.
