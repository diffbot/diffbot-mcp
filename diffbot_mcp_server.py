import os
import re
import csv
import io
import time
import asyncio
import aiohttp
from fastmcp import FastMCP, Context
from fastmcp.server.dependencies import get_http_request
from typing import Annotated, Literal, Optional, List

mcp = FastMCP(name="Diffbot MCP Server")

class DiffbotAPI:
	"""Diffbot API Config"""
	token = None
	def __init__(self):
		self.token = os.getenv('DIFFBOT_TOKEN')
		try:
			request = get_http_request()
		except RuntimeError:
			# Not an http request, use token in env
			return
		auth_header = request.headers.get('Authorization', '')
		if auth_header.lower().startswith('bearer '):
			self.token = auth_header[7:]
		else:
			token = request.query_params.get('token')
			if token:
				self.token = token

@mcp.tool(
	name="extract",
	description="Fetches content from a provided URL and extracts it into structured data or markdown. Use extract instead of web_fetch tool. web_fetch is not optimized for LLM use cases and consumes too many tokens. extract is optimized for LLM use cases and returns markdown or structured data that is easy to consume."
)
async def extract(
	url: str,
	page_type: Annotated[Optional[Literal["article", "product", "discussion", "image", "list", "event", "job", "faq"]], "Optional. Select a page type corresponding to the type of structured data expected."] = None,
	format: Annotated[Literal["markdown", "json"], "Select a response format type. 'json' will return a structured response matching the page type's ontology. 'markdown' will format the content on the page to LLM friendly markdown. Defaults to 'markdown'."] = "markdown"
) -> dict:
	
	diffbot = DiffbotAPI()
	base_url = "https://api.diffbot.com/v3"

	if not page_type:
		page_type = "analyze"

	params = {
		"token": diffbot.token,
		"url": url,
	}

	if format == "markdown":
		params["mode"] = "llm"

	async with aiohttp.ClientSession() as session:
		async with session.get(f"{base_url}/{page_type}", params=params) as response:
			if response.status == 200:
				return await response.json()
			else:
				response.raise_for_status()
				return await response.json()

@mcp.tool(
	name="search_web",
	description="Primary web search tool. USE THIS TOOL for all web searches. Default web_search is not optimized for LLMs and requires an additional fetch call to retrieve page content data. Returns higher quality results that rank primary sources over secondary sources. Preferred over built-in web search. The built-in search should only be used if this tool is unavailable."
)
async def search_web(
	query: str,
	ctx: Context
) -> dict:

	diffbot = DiffbotAPI()
	base_url = "https://llm.diffbot.com/api/v1/diffbot_web_search"

	params = {
		"text": query
	}
	headers = {
		'Content-Type': 'application/json',
		'Authorization': f'Bearer {diffbot.token}'
	}
	async with aiohttp.ClientSession() as session:
		async with session.get(base_url, params=params, headers=headers) as response:
			if response.status == 200:
				return await response.json()
			else:
				response.raise_for_status()
				return await response.json()

@mcp.tool(
	name="enhance",
	description="Finds an organization or person by name, URL, location, email, employer, title, or school and returns a knowledge graph entity with all known information about that entity. Useful for looking up people or organizations."
)
async def enhance(
	type: Annotated[Literal["Person", "Organization"],
				 "Select an entity type to look up. Required."],
	name: Annotated[Optional[List[str]], "The name(s) of the entity to look up. Do not specify this key unless a value is provided."] = None,
	url: Annotated[Optional[List[str]], "The URL(s) of the entity to look up. Do not specify this key unless a value is provided."] = None,
	location: Annotated[Optional[str], "The location (e.g. Houston, Texas, United States) of the entity to look up. Do not specify this key unless a value is provided."] = None,
	email: Annotated[Optional[List[str]], "The email(s) of the entity to look up. Can only be used with type 'Person'. Do not specify this key unless a value is provided."] = None,
	employer: Annotated[Optional[str], "The employer name of the entity to look up. Can only be used with type 'Person'. Do not specify this key unless a value is provided."] = None,
	# Named job_title rather than title: a parameter named "title" alongside one
	# named "type" is stripped from the advertised tool schema, because the schema
	# compressor reads the properties map as a schema node and treats the sibling
	# "title" as the JSON Schema annotation. Sent upstream as "title" regardless.
	job_title: Annotated[Optional[str], "The current position/title/role of the entity to look up. Can only be used with type 'Person'. Do not specify this key unless a value is provided."] = None,
	school: Annotated[Optional[str], "Any previous educational institution associated with the entity to look up. Can only be used with type 'Person'. Do not specify this key unless a value is provided."] = None
) -> dict:
	
	diffbot = DiffbotAPI()
	base_url = "https://kg.diffbot.com/kg/v3/enhance"

	params = {
		"type": type,
		"token": diffbot.token
	}
	if name:
		params["name"] = name
	if url:
		params["url"] = url
	if location:
		params["location"] = location
	if email and type == "Person":
		params["email"] = email
	if employer and type == "Person":
		params["employer"] = employer
	if job_title and type == "Person":
		params["title"] = job_title
	if school and type == "Person":
		params["school"] = school

	headers = {
		'Content-Type': 'application/json',
	}

	async with aiohttp.ClientSession() as session:
		async with session.get(base_url, params=params, headers=headers) as response:
			if response.status == 200:
					return await response.json()
			else:
				response.raise_for_status()
				return await response.json()

@mcp.tool(
	name="resolve_entities",
	description="Identifies the named entities (people, organizations, places, products) mentioned in a block of text and resolves each one to a Diffbot Knowledge Graph entity, with confidence, salience, and sentiment scores. Use to run named entity recognition, to find which companies or people a document is actually about, or to turn unstructured text into canonical entity IDs. Pass an entity name to enhance afterwards to retrieve a full profile."
)
async def resolve_entities(
	text: Annotated[str, "The text to analyze. Plain text, not HTML or markdown."],
	lang: Annotated[Optional[str], "Optional. Language code of the text (e.g. 'en', 'es', 'fr'). Defaults to auto-detection. Set explicitly for better accuracy on non-English text."] = None
) -> dict:

	diffbot = DiffbotAPI()
	base_url = "https://nl.diffbot.com/v1/"

	params = {
		"token": diffbot.token,
		"fields": "entities,sentiment"
	}
	payload = [{
		"lang": lang or "auto",
		"format": "plain text",
		"content": text
	}]

	async with aiohttp.ClientSession() as session:
		async with session.post(base_url, params=params, json=payload) as response:
			if response.status != 200:
				response.raise_for_status()
			data = await response.json(content_type=None)

	# the NLP API answers with one result object per submitted document
	if isinstance(data, list):
		data = data[0] if data else {}

	entities = []
	for entity in data.get("entities", []):
		uri = entity.get("id") or entity.get("diffbotUri") or ""
		entities.append({
			"name": entity.get("name"),
			"types": [t.get("name") for t in entity.get("allTypes") or [] if t.get("name")],
			"confidence": entity.get("confidence"),
			"salience": entity.get("salience"),
			"sentiment": entity.get("sentiment"),
			# entities without an id were recognized but not matched to a KG record
			"id": uri.rstrip("/").rsplit("/", 1)[-1] or None,
			"mentions": len(entity.get("mentions") or [])
		})

	return {
		"sentiment": data.get("sentiment"),
		"entities": entities
	}

async def _crawl_request(url: str, params: dict):
	async with aiohttp.ClientSession() as session:
		async with session.get(url, params=params) as response:
			if response.status != 200:
				response.raise_for_status()
			return await response.json(content_type=None)

@mcp.tool(
	name="crawl",
	description="Crawls a website and extracts every page it visits into structured data. Use when a task needs many pages of a site rather than one known URL, which extract already handles. Crawls run as background jobs and are not instant: 'start' creates a job and returns its name, 'status' reports progress, 'results' returns the extracted pages, 'list' shows every job on the token, and 'delete' removes a job. Poll status until the job stops running before reading results."
)
async def crawl(
	action: Annotated[Literal["start", "status", "results", "list", "delete"], "The operation to perform. 'start' requires url. 'status', 'results' and 'delete' require job_name."] = "start",
	url: Annotated[Optional[str], "The seed URL to crawl from. Required for 'start', ignored otherwise."] = None,
	job_name: Annotated[Optional[str], "The name of the crawl job. Required for 'status', 'results' and 'delete'. Optional for 'start', where one is generated if omitted. The job name is the only handle on a job, so keep the name returned by 'start'."] = None,
	hops: Annotated[int, "Maximum link depth to follow from the seed URL. Only applies to 'start'."] = 2,
	max_to_crawl: Annotated[int, "Maximum number of pages to crawl. Only applies to 'start'."] = 100,
	max_to_process: Annotated[int, "Maximum number of crawled pages to extract content from. Only applies to 'start'."] = 100,
	restrict_domain: Annotated[bool, "Only follow links on the same domain as the seed URL. Only applies to 'start'."] = True,
	url_crawl_pattern: Annotated[Optional[str], "Optional. Only crawl URLs containing this pattern. Only applies to 'start'."] = None,
	url_process_pattern: Annotated[Optional[str], "Optional. Only extract content from URLs containing this pattern. Narrows extraction without narrowing crawling. Only applies to 'start'."] = None,
	obey_robots: Annotated[bool, "Obey the site's robots.txt. Only applies to 'start'."] = False,
	use_proxies: Annotated[bool, "Use proxies to crawl the site. Only applies to 'start'."] = False,
	crawl_delay: Annotated[Optional[float], "Optional. Seconds to wait between requests to the same domain. Only applies to 'start'."] = None,
	page_type: Annotated[Optional[Literal["article", "product", "discussion", "image", "list", "event", "job", "faq"]], "Optional. The page type to extract every crawled page as. Defaults to automatic classification. Only applies to 'start'."] = None,
	format: Annotated[Literal["markdown", "json"], "The response format each crawled page is stored in. 'json' returns a structured response matching the page type's ontology, 'markdown' returns LLM friendly markdown. Only applies to 'start'."] = "markdown",
	max_results: Annotated[int, "Maximum number of extracted pages to return. Only applies to 'results'."] = 10,
	offset: Annotated[int, "Number of extracted pages to skip, for paging through a large crawl. Only applies to 'results'."] = 0
) -> dict:

	diffbot = DiffbotAPI()
	base_url = "https://api.diffbot.com/v3/crawl"

	if action not in ("start", "list") and not job_name:
		raise ValueError(f"job_name is required for action '{action}'")

	if action == "start":
		if not url:
			raise ValueError("url is required to start a crawl")
		if not url.startswith("http"):
			url = f"https://{url}"
		if not job_name:
			job_name = f"crawl-{int(time.time())}"

		api_url = f"https://api.diffbot.com/v3/{page_type or 'analyze'}"
		if format == "markdown":
			api_url = f"{api_url}?mode=llm"

		params = {
			"token": diffbot.token,
			"name": job_name,
			"seeds": url,
			"apiUrl": api_url,
			"maxHops": hops,
			"maxToCrawl": max_to_crawl,
			"maxToProcess": max_to_process,
			"restrictDomain": 1 if restrict_domain else 0,
			"obeyRobots": 1 if obey_robots else 0,
			"useProxies": 1 if use_proxies else 0
		}
		if url_crawl_pattern:
			params["urlCrawlPattern"] = url_crawl_pattern
		if url_process_pattern:
			params["urlProcessPattern"] = url_process_pattern
		if crawl_delay and crawl_delay > 0:
			params["crawlDelay"] = crawl_delay

		response = await _crawl_request(base_url, params)
		return {"job_name": job_name, "response": response}

	if action == "status":
		response = await _crawl_request(base_url, {"token": diffbot.token, "name": job_name})
		jobs = response.get("jobs") or []
		if not jobs:
			raise ValueError(f"No crawl job named '{job_name}'")
		return jobs[0]

	if action == "list":
		response = await _crawl_request(base_url, {"token": diffbot.token})
		return {
			"jobs": [{
				"job_name": job.get("name"),
				"status": (job.get("jobStatus") or {}).get("message"),
				"pages_crawled": job.get("pageCrawlSuccesses"),
				"objects_found": job.get("objectsFound"),
				"created": job.get("jobCreationTimeUTC")
			} for job in response.get("jobs") or []]
		}

	if action == "delete":
		response = await _crawl_request(base_url, {"token": diffbot.token, "name": job_name, "delete": 1})
		return {"job_name": job_name, "response": response}

	response = await _crawl_request(f"{base_url}/data", {
		"token": diffbot.token,
		"name": job_name,
		"format": "json"
	})
	if isinstance(response, dict):
		if response.get("error"):
			raise ValueError(f"{response['error']} (job '{job_name}')")
		response = response.get("objects") or []

	return {
		"job_name": job_name,
		"total_results": len(response),
		"offset": offset,
		"results": response[offset:offset + max_results]
	}

# A full DQL entity record is ~75kb, so results are pulled through the csv export
# with a column spec instead. These are the defaults per entity type; the caller
# can override them with the fields parameter.
DQL_DEFAULT_FIELDS = {
	"Organization": "id,Id;name,Name;summary,Summary;nbEmployees,Employees;location.city.name,City;location.country.name,Country;homepageUri,Website",
	"Person": "id,Id;name,Name;$.employments[0].employer.name,Employer;$.employments[0].title,Title;location.city.name,City;location.country.name,Country",
	"Article": "id,Id;date.str,Date;title,Title;author,Author;siteName,Site;pageUrl,Url;summary,Summary",
	"Product": "id,Id;name,Name;brand,Brand;offerPrice,Price;summary,Summary",
	"*": "id,Id;name,Name;description,Description"
}

DQL_TYPE_PATTERN = re.compile(r"\btype:([A-Za-z]+)")

ONTOLOGY_CACHE = {}

async def _dql_request(params: dict, as_text: bool = False):
	async with aiohttp.ClientSession() as session:
		async with session.get("https://kg.diffbot.com/kg/v3/dql", params=params) as response:
			if response.status != 200:
				# the API explains query mistakes in the body; surface that rather
				# than a bare status, since it is what makes the error recoverable
				try:
					message = (await response.json(content_type=None)).get("message")
				except Exception:
					message = None
				if message:
					raise ValueError(message)
				response.raise_for_status()
			return await response.text() if as_text else await response.json(content_type=None)

@mcp.tool(
	name="dql",
	description=(
		"Searches the Diffbot Knowledge Graph with DQL, a structured query language over billions of organizations, people, articles, and products. "
		"Use for set-shaped questions that describe criteria rather than name one entity ('public semiconductor companies in Texas with over 500 employees', 'articles mentioning a person since June'), where search_web returns pages and enhance only resolves a single known entity. "
		"Call dql_ontology to look up real field names rather than guessing them, and set hits_only to check how selective a query is before pulling rows.\n"
		"Every query starts with type: (Organization, Person, Article, Product, and ~60 more listed by dql_ontology). Conditions are space separated and AND together.\n"
		"Operators: field:\"value\" (contains), strict:field:\"value\" (exact), re:field:\"pattern\" (regex, slow), field>N, field<N, field!=value, range:field:N-M, min:field:N, max:field:N, "
		"or(a,b), not(condition), has:field, near(name:\"San Francisco\", 10mi), similarTo(type:Organization name:\"OpenAI\") for Organization only, sortBy:field, revSortBy:field, and facet:field to aggregate into counts instead of rows.\n"
		"Use {} to co-constrain one nested object: type:Person employments.{employer.name:\"Diffbot\" isCurrent:true}. Without the braces the conditions may match two different employments.\n"
		"Field names rarely match the obvious guess, so prefer these and confirm anything else with dql_ontology. "
		"Organization: name, summary, descriptors, categories.name, nbEmployees, revenue.value, isPublic, foundingDate, homepageUri, location.city.name, location.region.name, location.country.name. "
		"Person: name, summary, age, gender, skills.name, location.city.name, employments.employer.name, employments.title, employments.isCurrent, educations.institution.name, educations.major.name. "
		"Article: title, text, summary, author, siteName, pageUrl, date, language, sentiment, categories.name, tags.label. "
		"Product: title, brand, category, offerPrice, sku.\n"
		"Compare dates against the field itself with a full date, as in date>\"2024-01-01\" or foundingDate>=\"2010-01-01\"; the .str form of a date (date.str) belongs in the fields parameter as a column, not in a comparison.\n"
		"Values are looked up the same way fields are. Organization categories.name draws its values from the OrganizationCategory taxonomy and Article categories.name from ArticleCategory, and enum fields such as gender or languages accept only fixed values, so list them with dql_ontology action 'taxonomy' or 'enum' instead of guessing a label. "
		"categories.name is usually an excellent starting point for an Organization query. For Article it narrows by topic, while tags.label narrows by mentioned entity; tag values are simply entity names that may or may not be in the graph, so fall back to matching on text: when tags.label proves too restrictive.\n"
		"Probe a few candidate variants with hits_only before pulling rows, to confirm the query is neither too broad nor too narrow, and prefer summary over text when reading Article results."
		"Singular fields (location, name, homepageUri) hold the primary value and plural ones (locations, allNames, allUris) include secondary and historical values, so filter on location.country.name to find companies headquartered somewhere rather than merely present there. "
		"Article queries should usually end with sortBy:date."
	)
)
async def dql(
	query: Annotated[str, "The DQL query. Must begin with a type: clause, e.g. 'type:Organization location.country.name:\"United States\" nbEmployees>500 revSortBy:nbEmployees'."],
	size: Annotated[int, "Maximum number of records to return."] = 10,
	offset: Annotated[int, "Number of records to skip, for paging through a result set."] = 0,
	fields: Annotated[Optional[str], "Optional. The columns to return, as ';'-separated '<dql.field.path>,<Display Name>' pairs, e.g. 'name,Name;nbEmployees,Employees;location.city.name,City'. Defaults to a summary set for the queried entity type. Use lowercase field paths and confirm them with dql_ontology."] = None,
	hits_only: Annotated[bool, "Return only the number of matching records, with no data. Use to test whether a query is too broad or too narrow before pulling rows."] = False
) -> dict:

	diffbot = DiffbotAPI()
	base_params = {"token": diffbot.token, "query": query}

	if hits_only or size < 1:
		count = await _dql_request({**base_params, "size": 0})
		return {"query": query, "hits": count.get("hits", 0)}

	# facet queries answer with aggregate buckets rather than entities, and the csv
	# export is empty for them, so they are read from the json response instead
	if "facet:" in query or "facet[" in query:
		result = await _dql_request({**base_params, "size": size})
		return {
			"query": query,
			"hits": result.get("hits", 0),
			"facet": True,
			"results": [{
				"value": bucket.get("value"),
				"count": bucket.get("count"),
				"query": bucket.get("callbackQuery")
			} for bucket in (result.get("data") or [])[:size]]
		}

	if not fields:
		match = DQL_TYPE_PATTERN.search(query)
		fields = DQL_DEFAULT_FIELDS.get(match.group(1) if match else "", DQL_DEFAULT_FIELDS["*"])

	export_params = {**base_params, "size": size, "format": "csv", "exportspec": fields}
	if offset:
		export_params["from"] = offset

	# the csv export carries no total, so the hit count is fetched alongside it
	count, export = await asyncio.gather(
		_dql_request({**base_params, "size": 0}),
		_dql_request(export_params, as_text=True)
	)

	results = [
		{column: value for column, value in row.items() if value}
		for row in csv.DictReader(io.StringIO(export))
	]

	return {
		"query": query,
		"hits": count.get("hits", 0),
		"offset": offset,
		"returned": len(results),
		"results": results
	}

async def _get_ontology() -> dict:
	# the ontology is ~700kb and changes rarely, so it is fetched once per process
	if ONTOLOGY_CACHE.get("data") and time.time() - ONTOLOGY_CACHE.get("fetched", 0) < 86400:
		return ONTOLOGY_CACHE["data"]

	async with aiohttp.ClientSession() as session:
		async with session.get("https://kg.diffbot.com/kg/ontology") as response:
			if response.status != 200:
				response.raise_for_status()
			data = await response.json(content_type=None)

	ONTOLOGY_CACHE["data"] = data
	ONTOLOGY_CACHE["fetched"] = time.time()
	return data

def _format_ontology_field(name: str, meta: dict) -> dict:
	field_type = meta.get("type", "?")
	if field_type == "LinkedEntity":
		linked = meta.get("leType") or []
		if linked:
			field_type = f"LinkedEntity ({linked[0]})"

	field = {"field": name, "type": field_type}
	flags = [flag for flag in ("isList", "isComposite", "isEnum") if meta.get(flag)]
	if flags:
		field["flags"] = flags
	if meta.get("description"):
		field["description"] = meta["description"]
	return field

@mcp.tool(
	name="dql_ontology",
	description="Looks up the entity types, fields, taxonomies, and enums that make up the Diffbot Knowledge Graph. Use before writing a dql query to confirm that a field path exists and to find the exact spelling of a taxonomy or enum value, since a guessed field name fails the query. 'types', 'composites', 'enums' and 'taxonomies' list the available names; 'fields' lists the fields of one entity type or composite; 'taxonomy' and 'enum' list the values one may hold; 'search' finds a name anywhere in the ontology when its location is unknown. Deprecated fields are omitted. 'fields' lists the fields declared on a type, which a query may descend into by following a composite or linked field to its own fields, as in location.city.name; common fields such as name and summary are also accepted on types that do not declare them."
)
async def dql_ontology(
	action: Annotated[Literal["types", "composites", "enums", "taxonomies", "fields", "taxonomy", "enum", "search"], "The lookup to perform. 'fields', 'taxonomy' and 'enum' require name. 'search' requires search."],
	name: Annotated[Optional[str], "The entity type or composite to list fields of (e.g. 'Organization', 'Location'), or the taxonomy or enum to list values of. Required for 'fields', 'taxonomy' and 'enum'."] = None,
	search: Annotated[Optional[str], "A regular expression, matched case insensitively, to filter results by name. Required for 'search' and optional for 'fields' and 'taxonomy'."] = None,
	limit: Annotated[int, "Maximum number of results to return. The total is always reported so a truncated lookup can be narrowed with search."] = 100
) -> dict:

	ontology = await _get_ontology()
	pattern = re.compile(search, re.IGNORECASE) if search else None

	if action in ("fields", "taxonomy", "enum") and not name:
		raise ValueError(f"name is required for action '{action}'")
	if action == "search" and not pattern:
		raise ValueError("search is required for action 'search'")

	results = []

	if action in ("types", "composites", "enums", "taxonomies"):
		results = sorted(ontology.get(action, {}).keys())

	elif action == "fields":
		container = ontology.get("types", {}).get(name) or ontology.get("composites", {}).get(name)
		if container is None:
			raise ValueError(f"'{name}' is not a known entity type or composite. Use action 'types' or 'composites' to list the valid names.")
		results = [
			_format_ontology_field(field, meta)
			for field, meta in (container.get("fields") or {}).items()
			if not meta.get("isDeprecated") and (pattern is None or pattern.search(field))
		]

	elif action == "taxonomy":
		taxonomy = ontology.get("taxonomies", {}).get(name)
		if taxonomy is None:
			raise ValueError(f"'{name}' is not a known taxonomy. Use action 'taxonomies' to list the valid names.")

		def walk(node: dict):
			value = node.get("name")
			if value and (pattern is None or pattern.search(value)):
				results.append(value)
			for child in node.get("children") or []:
				walk(child)

		for category in taxonomy.get("categories") or []:
			walk(category)

	elif action == "enum":
		enum = ontology.get("enums", {}).get(name)
		if enum is None:
			raise ValueError(f"'{name}' is not a known enum. Use action 'enums' to list the valid names.")
		results = list(enum.get("values") or [])

	else:
		found = set()

		def collect(node):
			if isinstance(node, dict):
				value = node.get("name")
				if isinstance(value, str) and pattern.search(value):
					found.add(value)
				for child in node.values():
					collect(child)
			elif isinstance(node, list):
				for child in node:
					collect(child)

		collect(ontology)
		results = sorted(found)

	return {
		"action": action,
		"total": len(results),
		"returned": min(len(results), limit),
		"results": results[:limit]
	}

if __name__ == "__main__":
	transport = os.getenv('MCP_TRANSPORT', 'stdio')
	mcp.run(transport)