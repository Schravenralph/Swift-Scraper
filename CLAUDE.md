# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Swift Scraper is a Python web scraper that extracts SWIFT/BIC bank codes from theswiftcodes.com and stores them in either MongoDB or a JSON file. The project was designed to replicate functionality from an n8n workflow, converting it to a standalone Python script.

## Development Commands

### Running the Scraper

```bash
# Run with UV (recommended - manages dependencies automatically)
uv run swift_scraper.py

# Or activate the virtual environment first
source .venv/bin/activate
python swift_scraper.py
```

### Dependency Management

```bash
# Install/sync dependencies from pyproject.toml
uv sync

# Add a new dependency
uv add <package-name>
```

## Architecture

### Core Components

The scraper follows a sequential workflow:

1. **Country Discovery** (`get_country_links()`) - Scrapes the browse-by-country page to get all country links
2. **Freshness Check** (`should_scrape()`) - Determines if a country needs re-scraping based on 4-week staleness threshold
3. **Page Parsing** (`parse_country_page()`) - Extracts bank data from country-specific pages with pagination support
4. **Data Enrichment** - Augments scraped data with ISO country codes via RestCountries API
5. **Storage** - Saves to MongoDB (optional) and always to `swift_data.json`

### Data Flow

```
theswiftcodes.com/browse-by-country/
  → Extract country links
  → For each country:
    → Check freshness (swift_freshness.json)
    → If stale:
      → Scrape all paginated pages
      → Lookup ISO codes (restcountries.com API)
      → Save to MongoDB (if configured) + JSON file
      → Update freshness timestamp
```

### Key Files

- `swift_scraper.py` - Main scraper logic (single file)
- `swift_data.json` - Output file containing all scraped SWIFT codes
- `swift_freshness.json` - Tracks last scrape timestamp per country (ISO2 code)
- `pyproject.toml` - Dependencies and project metadata

### Important Implementation Details

**Test Mode Limiter**: Line 285 limits scraping to first 3 countries with `[:3]`. Remove this slice to scrape all countries.

**MongoDB is Optional**: The scraper gracefully degrades to JSON-only output if MongoDB is unavailable. Set these environment variables to enable MongoDB:
- `MONGODB_URI` - Connection string (defaults to localhost)
- `MONGODB_DB` - Database name (defaults to "swifts")
- `MONGODB_COLLECTION` - Collection name (defaults to "meetup")

**Freshness Logic**: Countries are only re-scraped if:
- No previous scrape exists in `swift_freshness.json`
- Last scrape was more than 4 weeks ago (`FRESHNESS_WEEKS` constant)
- ISO2 code is missing (fallback to always scrape)

**Rate Limiting**: 1-second delay between page requests (line 257) to avoid overwhelming the server.

**n8n Workflow Equivalence**: The code structure mirrors the original n8n workflow nodes:
- `normalize_country_name()` replicates n8n's text normalization
- `lookup_iso()` calls the same RestCountries API
- Freshness tracking mimics `workflowStaticData('global').lastScrapedAt`
- Pagination logic follows n8n's "Loop Over Items" pattern

### HTML Selectors

The scraper relies on these CSS selectors from theswiftcodes.com:
- Country links: `ol > li > a`
- Pagination: `span.next > a`
- Bank data table: `td.table-name`, `td.table-swift`, `td.table-city`, `td.table-branch`

If the scraper breaks, these selectors may have changed on the website.
