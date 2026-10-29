"""Generated-DQL assertions for the typed tools. No network: the builders are pure."""

import pytest
from fastmcp.exceptions import ToolError

from diffbot_mcp import dql_builder as b
from diffbot_mcp.dql import clean_row, clean_value, default_fields
from diffbot_mcp.tools.deals import build_deals_query
from diffbot_mcp.tools.news import build_news_query
from diffbot_mcp.dql import rank_names, rank_values
from diffbot_mcp.dql_builder import parse_date_range, parse_range, split_near
from diffbot_mcp.tools.organizations import build_organizations_query
from diffbot_mcp.tools.people import build_leadership_query, build_people_query, pick_employment
from diffbot_mcp.tools.places import build_places_query
from diffbot_mcp.tools.search_web import is_page_lookup


# --- builder primitives -----------------------------------------------------------

def test_quote_escapes_double_quotes():
    assert b.quote('Say "hi"') == '"Say \\"hi\\""'


def test_or_clause_collapses_single_value_and_dedupes():
    assert b.or_clause("tags.label", ["Nvidia"]) == 'tags.label:"Nvidia"'
    assert b.or_clause("tags.label", ["Tesla", "Rivian", "Tesla"]) == 'tags.label:or("Tesla","Rivian")'
    assert b.or_clause("name", ["A", "B"], strict=True) == 'strict:name:or("A","B")'


def test_subquery_is_empty_without_clauses():
    assert b.subquery("employments", []) == ""
    assert b.subquery("employments", ['employer.name:"Diffbot"', "isCurrent:true"]) == 'employments.{employer.name:"Diffbot" isCurrent:true}'


def test_expand_titles_covers_both_spellings_and_board_seats():
    assert b.expand_titles(["CEO"]) == ["Chief Executive Officer", "CEO"]
    assert b.expand_titles(["chief technology officer"]) == ["Chief Technology Officer", "CTO"]
    assert b.expand_titles(["board member"]) == ["Board Member", "Board of Directors", "Director"]
    assert b.expand_titles(["VP of Engineering"]) == ["VP of Engineering"]


def test_name_variants_folds_diacritics():
    assert b.name_variants("Kópavogur") == ["Kópavogur", "Kopavogur"]
    assert b.name_variants("Reykjavik") == ["Reykjavik"]


def test_date_validation():
    assert b.date_range("date", "2026-08-01", None) == ['date>="2026-08-01"']
    with pytest.raises(ToolError):
        b.validate_date("August 2026", "since")


def test_near_radius_validation():
    assert b.near_clause("Austin", "30mi") == 'near(type:Place name:"Austin", 30mi)'
    assert b.near_clause("Paris") == 'near(type:Place name:"Paris")'
    with pytest.raises(ToolError):
        b.near_clause("Austin", "30 miles")


# --- executor post-processing -----------------------------------------------------

def test_clean_value_strips_date_prefix_and_expands_scientific_notation():
    assert clean_value("d2026-07-23") == "2026-07-23"
    assert clean_value("d2026-08-12T20:02:31") == "2026-08-12T20:02:31"
    assert clean_value("3.0E8") == "300000000"
    assert clean_value("1.5E-1") == "0.15"
    assert clean_value("Series A") == "Series A"


def test_clean_row_drops_empty_columns():
    assert clean_row({"Name": "X", "Amount": "", "Date": "d2026-01-01"}) == {"Name": "X", "Date": "2026-01-01"}


def test_default_fields_by_type():
    assert default_fields("type:Investment investee.name:\"OpenAI\"").startswith("investee.name,Company")
    assert default_fields("type:City location.country.name:\"Japan\"").startswith("name,Place")
    assert default_fields("type:Patent").startswith("id,Id")


# --- news ------------------------------------------------------------------------

def test_news_always_sorts_newest_first():
    query, _ = build_news_query(mentions=["OpenAI"])
    assert query == 'type:Article tags.label:"OpenAI" sortBy:date'
    query, _ = build_news_query(mentions=["OpenAI"], since="2026-08-01")
    assert query == 'type:Article tags.label:"OpenAI" date>="2026-08-01" sortBy:date'


def test_news_entity_sentiment_is_co_constrained_on_the_tag():
    query, _ = build_news_query(mentions=["Nvidia"], mention_sentiment_max=-0.3)
    assert query == 'type:Article tags.{label:"Nvidia" sentiment<-0.3} sortBy:date'


def test_news_refuses_an_unfiltered_query():
    with pytest.raises(ToolError):
        build_news_query()


# --- organizations ------------------------------------------------------------------

def test_organizations_strict_name_and_hq_location():
    query = build_organizations_query(industry=["Semiconductor Companies"], country="United States", is_public=True)
    assert query == 'type:Organization categories.{name:"Semiconductor Companies" isPrimary:true} location.country.name:"United States" isPublic:true'
    loose = build_organizations_query(industry=["Semiconductor Companies", "Fabless Semiconductor Companies"], primary_industry=False)
    assert loose == 'type:Organization categories.name:or("Semiconductor Companies","Fabless Semiconductor Companies")'
    assert build_organizations_query(name="Apple Inc.") == 'type:Organization strict:name:"Apple Inc."'
    assert build_organizations_query(city="Berlin", any_office=True) == 'type:Organization locations.city.name:"Berlin"'


def test_organizations_or_lists_and_membership():
    assert build_organizations_query(name=["American Express", "Starbucks"]) == 'type:Organization strict:name:or("American Express","Starbucks")'
    assert build_organizations_query(city=["Long Beach", "Fortaleza"], min_employees=71) == 'type:Organization location.city.name:or("Long Beach","Fortaleza") nbEmployees>=71'
    assert build_organizations_query(part_of="S&P 500") == 'type:Organization partOf.name:"S&P 500"'
    assert build_organizations_query(subsidiary="Bally Total Fitness", industry=["Resorts"]) == 'type:Organization categories.{name:"Resorts" isPrimary:true} subsidiaries.name:"Bally Total Fitness"'


def test_organizations_series():
    assert build_organizations_query(series="Series B", industry=["Accounting Services"]) == 'type:Organization categories.{name:"Accounting Services" isPrimary:true} investments.series:"Series B"'


def test_organizations_acquired_by_and_similar_to():
    assert build_organizations_query(acquired_by="Microsoft") == 'type:Organization isAcquired:true acquiredBy.name:"Microsoft"'
    assert build_organizations_query(similar_to="OpenAI", country="United States") == 'type:Organization similarTo(name:"OpenAI") location.country.name:"United States"'
    assert build_organizations_query(similar_to="walmart.com") == 'type:Organization similarTo(homepageUri:"walmart.com")'


def test_organizations_revenue_band():
    query = build_organizations_query(industry=["Software Companies"], region="Massachusetts", min_revenue=10_000_000, max_revenue=75_000_000)
    assert query == 'type:Organization categories.{name:"Software Companies" isPrimary:true} location.region.name:"Massachusetts" revenue.value>=10000000 revenue.value<=75000000'


def test_range_parsing():
    assert parse_range("10M-75M", "revenue") == (10_000_000, 75_000_000)
    assert parse_range("$1.5B+", "revenue") == (1_500_000_000, None)
    assert parse_range(">=500", "employees") == (500, None)
    assert parse_range("<20", "employees") == (None, 20)
    assert parse_range("<20", "employees", integer=True) == (None, 19)
    assert parse_range(">20", "employees", integer=True) == (21, None)
    assert parse_range("50-500", "employees", integer=True) == (50, 500)
    assert parse_range("50 - 500", "employees") == (50, 500)
    assert parse_range("", "employees") == (None, None)
    assert parse_date_range("2015-2020", "founded") == ("2015-01-01", "2020-12-31")
    assert parse_date_range("2019", "founded") == ("2019-01-01", "2019-12-31")
    assert parse_date_range(">=2020-06-01", "founded") == ("2020-06-01", None)
    assert parse_date_range("2015-06-01-2016-01-31", "founded") == ("2015-06-01", "2016-01-31")
    assert split_near("Austin 30mi") == ("Austin", "30mi")
    assert split_near("San Francisco, 50 km") == ("San Francisco", "50km")
    assert split_near("Austin") == ("Austin", None)


def test_organizations_sort_is_opt_in():
    assert "SortBy" not in build_organizations_query(industry=["Semiconductor Companies"])
    assert build_organizations_query(industry=["Semiconductor Companies"], sort="employees").endswith("revSortBy:nbEmployees")


# --- people -----------------------------------------------------------------------

def test_people_employment_conditions_share_one_subquery_with_expanded_titles():
    query = build_people_query(title=["Chief Executive Officer"], employer_industry="Semiconductor Companies")
    assert query == 'type:Person employments.{title:or("Chief Executive Officer","CEO") employer.categories.name:"Semiconductor Companies" isCurrent:true}'


def test_people_history_drops_is_current_and_education_is_co_constrained():
    query = build_people_query(employer="Nvidia", current=False, school="Stanford University", major="Computer Science")
    assert query == 'type:Person employments.{employer.name:"Nvidia"} educations.{institution.name:"Stanford University" major.name:"Computer Science"}'


def test_people_new_filters():
    query = build_people_query(job_category="Business", job_location="Hong Kong")
    assert query == 'type:Person employments.{categories.name:"Business" or(location.city.name:"Hong Kong", location.country.name:"Hong Kong") isCurrent:true}'
    query = build_people_query(school_location="Ghana", employer_max_employees=48)
    assert query == 'type:Person employments.{employer.nbEmployees<=48 isCurrent:true} educations.{or(location.city.name:"Ghana", location.country.name:"Ghana")}'
    assert build_people_query(language="German", name=["Ralph", "Judy"]) == 'type:Person strict:name:or("Ralph","Judy") languages:"German"'
    assert build_people_query(city=["Los Angeles", "Indianapolis"]) == 'type:Person location.city.name:or("Los Angeles","Indianapolis")'


def test_leadership_query_prefers_the_domain_and_requests_curated_fields():
    assert build_leadership_query("tesla.com") == 'type:Organization homepageUri:"tesla.com" get:name,ceo,founders'
    assert build_leadership_query("Tesla") == 'type:Organization name:"Tesla" get:name,ceo,founders'


def test_pick_employment_returns_the_matched_job_not_the_primary_one():
    employments = [
        {"title": "CEO", "employer": {"name": "Neuralink"}, "isCurrent": True},
        {"title": "Co-Founder", "employer": {"name": "Tesla"}, "isCurrent": False},
    ]
    assert pick_employment(employments, "Tesla", [], current=False)["employer"]["name"] == "Tesla"
    assert pick_employment(employments, None, ["CEO"], current=True)["employer"]["name"] == "Neuralink"


# --- places -----------------------------------------------------------------------

def test_places_uses_the_narrow_type_and_both_spellings():
    query, _ = build_places_query(kind="city", name="Kópavogur")
    assert query == 'type:City strict:name:or("Kópavogur","Kopavogur")'
    query, _ = build_places_query(kind="city", country="Japan", min_population=1000000, sort="population")
    assert query == 'type:City location.country.name:"Japan" population>=1000000 revSortBy:population'


def test_places_poi_and_continent_note():
    query, notes = build_places_query(kind="poi", descriptors="national park", near="Yosemite", radius="20mi")
    assert query == 'type:Place not(types:"AdministrativeArea") descriptors:"national park" near(type:Place name:"Yosemite", 20mi)'
    query, notes = build_places_query(kind="country", continent="Europe")
    assert query == 'type:Country description:"in Europe"'
    assert notes and "text-matched" in notes[0]


# --- deals ------------------------------------------------------------------------

def test_deals_funding_rounds():
    query, fields, mode = build_deals_query(kind="funding", investor="Sequoia Capital", sort="newest")
    assert query == 'type:Investment investment.investors.name:"Sequoia Capital" revSortBy:investment.date'
    assert mode == "rows" and fields.startswith("investee.name,Company")
    query, _, _ = build_deals_query(kind="funding", series="Series A", since="2026-01-01", sort="largest")
    assert query == 'type:Investment investment.series:"Series A" investment.date>="2026-01-01" revSortBy:investment.amount.value'
    query, _, _ = build_deals_query(kind="funding", min_amount=100000000)
    assert query == 'type:Investment investment.amount.value>=100000000 investment.amount.currency:"USD" revSortBy:investment.date'


def test_deals_acquisitions_route_through_the_target_organization():
    query, fields, _ = build_deals_query(kind="acquisitions", acquirer="Microsoft", sort="largest")
    assert query == 'type:Organization isAcquired:true acquiredBy.name:"Microsoft" revSortBy:acquiredBy.amount.value'
    assert fields.startswith("name,Target")


def test_deals_industry_moves_to_the_company_side_with_a_subquery():
    query, fields, mode = build_deals_query(kind="funding", industry="Artificial Intelligence Software", min_amount=50000000, since="2026-01-01")
    assert query == 'type:Organization categories.name:"Artificial Intelligence Software" investments.{amount.value>=50000000 amount.currency:"USD" date>="2026-01-01"} revSortBy:investments.date'
    assert mode == "industry" and fields is None


def test_deals_facets_and_invalid_combinations():
    query, _, _ = build_deals_query(kind="funding", since="2026-01-01", facet="series")
    assert query == 'type:Investment investment.date>="2026-01-01" facet:investment.series'
    with pytest.raises(ToolError):
        build_deals_query(kind="acquisitions", series="Series A")
    with pytest.raises(ToolError):
        build_deals_query(kind="funding")


# --- resolver -------------------------------------------------------------------------------

TAXONOMY = [
    "Software Companies", "Software As A Service Companies", "Loan Software", "Mortgage And Loans Lenders",
    "Electric Vehicles", "Electric Vehicle Charging Stations", "Government Agencies", "Federal Agencies",
    "Food And Drink Companies", "Food Companies", "Accounting Services", "Restaurants",
]


def test_rank_values_exact_then_substring():
    assert rank_values(TAXONOMY, "government agencies") == ["Government Agencies"]
    assert rank_values(TAXONOMY, "Software")[:2] == ["Software Companies", "Software As A Service Companies"]
    assert rank_values(TAXONOMY, "food and drink") == ["Food And Drink Companies"]


def test_rank_values_tokens_ignore_filler_and_plurals():
    assert rank_values(TAXONOMY, "loan companies") == ["Loan Software", "Mortgage And Loans Lenders"]
    assert rank_values(TAXONOMY, "electric vehicle companies")[0] == "Electric Vehicles"
    assert rank_values(TAXONOMY, "agencies of the government") == ["Government Agencies"]


def test_rank_values_acronym_without_alias_table():
    assert rank_values(TAXONOMY, "SaaS") == ["Software As A Service Companies"]
    assert rank_values(TAXONOMY, "EV")[0] == "Electric Vehicles"
    assert rank_values(TAXONOMY, "xyzzy") == []


def test_rank_names_puts_whole_and_prefix_matches_first():
    import re
    ranked = rank_names(["AB Testing Software", "Software Companies", "Software As A Service Companies", "Loan Software"], re.compile("software", re.I))
    assert ranked[:2] == ["Software Companies", "Software As A Service Companies"]
    assert ranked[-1] == "AB Testing Software"


def test_organizations_founder():
    query = build_organizations_query(founder="Elon Musk")
    assert query == 'type:Organization founders.name:"Elon Musk"'


def test_search_web_page_lookup():
    assert is_page_lookup("url:https://example.com/docs")
    assert is_page_lookup("  URL:example.com/docs ")
    assert not is_page_lookup("url:https://example.com/docs rate limits")
    assert not is_page_lookup("example.com docs")
