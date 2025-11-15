# Swift Scraper

A Python web scraper that extracts SWIFT/BIC bank codes from [theswiftcodes.com](https://www.theswiftcodes.com) and stores them in MongoDB or JSON format.

## Features

- **Comprehensive Coverage**: Scrapes SWIFT codes from 205+ countries
- **Smart Freshness Tracking**: Automatically skips countries scraped within the last 4 weeks
- **Pagination Support**: Handles multi-page country listings automatically
- **ISO Code Enrichment**: Augments data with ISO country codes via RestCountries API
- **Dual Storage**: Saves to both MongoDB (optional) and JSON file
- **Graceful Degradation**: Falls back to JSON-only storage if MongoDB is unavailable
- **Environment-based Configuration**: Secure credential management with `.env` support

## Installation

### Prerequisites

- Python 3.8+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Setup

1. Clone the repository:
```bash
git clone https://github.com/Schravenralph/Swift-Scraper.git
cd Swift-Scraper
```

2. Install dependencies:
```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -r requirements.txt
```

3. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your MongoDB credentials
```

## Configuration

Create a `.env` file in the project root with the following variables:

```env
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/?appName=cluster-name
MONGODB_DB=swifts
MONGODB_COLLECTION=meetup
```

**MongoDB is optional** - the scraper will save to `swift_data.json` if MongoDB is not configured.

## Usage

Run the scraper:

```bash
# Using uv
uv run swift_scraper.py

# Or with activated virtual environment
source .venv/bin/activate
python swift_scraper.py
```

### Output Files

- `swift_data.json` - All scraped SWIFT codes with metadata
- `swift_freshness.json` - Tracks last scrape timestamp per country

## How It Works

1. **Country Discovery**: Fetches all country links from the browse page
2. **Freshness Check**: Determines if country data needs updating (4-week threshold)
3. **Data Scraping**: Extracts bank information with pagination support
4. **ISO Enrichment**: Looks up ISO country codes via RestCountries API
5. **Storage**: Saves to MongoDB and/or JSON file
6. **Freshness Update**: Records scrape timestamp for future runs

### Data Structure

Each scraped record contains:

```json
{
  "iso_code": "NL",
  "iso3": "NLD",
  "country": "netherlands",
  "page": "/netherlands_swift_codes.html",
  "name": "ABN AMRO BANK N.V.",
  "swift_code": "ABNANL2A",
  "city": "AMSTERDAM",
  "branch": "HEAD OFFICE",
  "createdAt": "2025-11-15T14:28:12.600999+00:00",
  "updatedAt": "2025-11-15T14:28:12.600999+00:00"
}
```

## Configuration Options

Edit constants in `swift_scraper.py`:

- `FRESHNESS_WEEKS`: Number of weeks before re-scraping (default: 4)
- `BASE_URL`: Source website URL
- Rate limiting: 1-second delay between page requests

## Development

This project was designed to replicate an n8n workflow in Python, maintaining the same data structure and logic flow.

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
