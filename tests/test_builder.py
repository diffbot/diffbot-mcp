"""Generated-DQL assertions for the typed tools. No network: the builders are pure."""

import pytest
from fastmcp.exceptions import ToolError

from diffbot_mcp import dql_builder as b
from diffbot_mcp.dql import clean_row, clean_value, default_fields
from diffbot_mcp.tools.deals import build_deals_query
from diffbot_mcp.tools.news import build_news_query
from diffbot_mcp.dql_builder import parse_date_range, parse_range, split_near
from diffbot_mcp.tools.organizations import build_organizations_query
from diffbot_mcp.tools.people import build_leadership_query, build_people_query, pick_employment
from diffbot_mcp.tools.places import build_places_query


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

def test_news_defaults_to_newest_without_a_date_and_relevance_with_one():
    query, _ = build_news_query(mentions=["OpenAI"])
    assert query == 'type:Article tags.label:"OpenAI" sortBy:date'
    query, _ = build_news_query(mentions=["OpenAI"], since="2026-08-01")
    assert query == 'type:Article tags.label:"OpenAI" date>="2026-08-01"'
    query, _ = build_news_query(mentions=["OpenAI"], sort="oldest")
    assert query.endswith("revSortBy:date")


def test_news_entity_sentiment_is_co_constrained_on_the_tag():
    query, _ = build_news_query(mentions=["Nvidia"], mention_sentiment_max=-0.3)
    assert query == 'type:Article tags.{label:"Nvidia" sentiment<-0.3} sortBy:date'


def test_news_facet_has_no_sort():
    query, _ = build_news_query(mentions=["Anthropic"], facet="siteName")
    assert query == 'type:Article tags.label:"Anthropic" facet:siteName'


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
    assert query == 'type:Investment investment.amount.value>=100000000 investment.amount.currency:"USD"'


def test_deals_acquisitions_route_through_the_target_organization():
    query, fields, _ = build_deals_query(kind="acquisitions", acquirer="Microsoft", sort="largest")
    assert query == 'type:Organization isAcquired:true acquiredBy.name:"Microsoft" revSortBy:acquiredBy.amount.value'
    assert fields.startswith("name,Target")


def test_deals_industry_moves_to_the_company_side_with_a_subquery():
    query, fields, mode = build_deals_query(kind="funding", industry="Artificial Intelligence Software", min_amount=50000000, since="2026-01-01")
    assert query == 'type:Organization categories.name:"Artificial Intelligence Software" investments.{amount.value>=50000000 amount.currency:"USD" date>="2026-01-01"}'
    assert mode == "industry" and fields is None


def test_deals_facets_and_invalid_combinations():
    query, _, _ = build_deals_query(kind="funding", since="2026-01-01", facet="series")
    assert query == 'type:Investment investment.date>="2026-01-01" facet:investment.series'
    with pytest.raises(ToolError):
        build_deals_query(kind="acquisitions", series="Series A")
    with pytest.raises(ToolError):
        build_deals_query(kind="funding")
