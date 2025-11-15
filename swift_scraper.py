import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Optional: comment out if you don't use Mongo
from pymongo import MongoClient

BASE_URL = "https://www.theswiftcodes.com"
BROWSE_URL = f"{BASE_URL}/browse-by-country/"
FRESHNESS_FILE = "swift_freshness.json"  # stores lastScrapedAt per iso2
DATA_FILE = "swift_data.json"  # stores scraped SWIFT codes
FRESHNESS_WEEKS = 4


# ---------- utils ----------

def load_freshness() -> Dict[str, str]:
    """Load lastScrapedAt per iso2 from JSON file."""
    if not os.path.exists(FRESHNESS_FILE):
        return {}
    with open(FRESHNESS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_freshness(data: Dict[str, str]) -> None:
    """Persist lastScrapedAt per iso2."""
    with open(FRESHNESS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def normalize_country_name(raw: str) -> str:
    """Mimics your n8n normalize function."""
    if not raw:
        return ""
    s = str(raw).strip()
    # trim slashes, underscores, dots, whitespace at ends
    s = s.strip("/_. \t\r\n")
    # replace underscores / dashes with spaces
    s = s.replace("_", " ").replace("-", " ")
    # collapse multiple spaces
    s = " ".join(s.split())
    return s


def lookup_iso(country_name: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Lookup ISO codes using RestCountries API."""
    if not country_name:
        return None, None, None

    url = f"https://restcountries.com/v3.1/name/{requests.utils.quote(country_name)}"
    params = {
        "fullText": "false",
        "fields": "cca2,cca3,name",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            c = data[0]
            return c.get("cca2"), c.get("cca3"), c.get("name", {}).get("common")
    except Exception as e:
        print(f"[ISO lookup] Error for '{country_name}': {e}")
    return None, None, None


def should_scrape(iso2: Optional[str], freshness: Dict[str, str]) -> Tuple[bool, str]:
    """Decide whether to scrape this country based on last scrape."""
    if not iso2:
        return True, "No iso2 code; defaulting to scrape."

    last_str = freshness.get(iso2)
    if not last_str:
        return True, "No previous scrape recorded."

    try:
        last_dt = datetime.fromisoformat(last_str)
    except Exception:
        return True, f"Invalid stored date '{last_str}', scraping."

    age = datetime.now(timezone.utc) - last_dt
    if age < timedelta(weeks=FRESHNESS_WEEKS):
        return False, f"Scraped recently at {last_dt.isoformat()}."
    return True, f"Data stale; last scrape at {last_dt.isoformat()}."


# ---------- HTML helpers ----------

def fetch_html(url: str) -> BeautifulSoup:
    print(f"[HTTP] GET {url}")
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def get_country_links() -> List[Tuple[str, str]]:
    """
    Scrape /browse-by-country/ to get (href, label) for each country.
    Corresponds to HTML Extract: cssSelector 'ol > li > a', attribute href.
    """
    soup = fetch_html(BROWSE_URL)
    links = []
    for a in soup.select("ol > li > a"):
        href = a.get("href")
        text = a.get_text(strip=True)
        if href:
            links.append((href, text))
    print(f"[COUNTRIES] Found {len(links)} countries")
    return links


def parse_country_page(path: str) -> Tuple[List[dict], Optional[str]]:
    """
    Parse a single country page.
    - path: e.g. '/netherlands_swift_codes.html' or '/netherlands_swift_codes_page_2.html'
    Returns:
      - list of bank documents
      - next page href (relative) or None
    """
    url = f"{BASE_URL}{path}"
    soup = fetch_html(url)

    # Next-page link: 'span.next > a'
    next_link = soup.select_one("span.next > a")
    next_href = next_link.get("href") if next_link else None

    # table columns
    names = [td.get_text(strip=True) for td in soup.select("td.table-name")]
    swifts = [td.get_text(strip=True) for td in soup.select("td.table-swift")]
    cities = [td.get_text(strip=True) for td in soup.select("td.table-city")]
    branches = [td.get_text(strip=True) for td in soup.select("td.table-branch")]

    # Ensure same length; ignore trailing mismatches if any
    rows = []
    for i in range(min(len(names), len(swifts), len(cities), len(branches))):
        rows.append({
            "name": names[i],
            "swift_code": swifts[i],
            "city": cities[i],
            "branch": branches[i],
        })

    print(f"[PAGE] {url} -> {len(rows)} rows, next={next_href}")
    return rows, next_href


# ---------- Mongo (optional) ----------

def get_mongo_collection():
    """
    Get a Mongo collection using env vars when available.
    Env:
      - MONGODB_URI (e.g., mongodb+srv://user:pass@cluster/...)
      - MONGODB_DB (default: 'swifts')
      - MONGODB_COLLECTION (default: 'meetup')
    Validates connectivity with a ping.
    """
    uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
    db_name = os.environ.get("MONGODB_DB", "swifts")
    coll_name = os.environ.get("MONGODB_COLLECTION", "meetup")

    # 5s server selection to fail fast if unreachable
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    # Validate connection
    client.admin.command("ping")

    db = client[db_name]
    print(f"[MONGO] Connected (db={db_name}, coll={coll_name})")
    return db[coll_name]


def save_documents_mongo(coll, docs: List[dict]) -> None:
    if not docs:
        return
    # ensure createdAt / updatedAt
    now = datetime.now(timezone.utc)
    for d in docs:
        d.setdefault("createdAt", now)
        d["updatedAt"] = now
    result = coll.insert_many(docs)
    print(f"[MONGO] Inserted {len(result.inserted_ids)} documents")


# ---------- main scraping logic ----------

def scrape_country(
    country_href: str,
    country_label: str,
    coll=None,
    freshness: Dict[str, str] = None,
    all_docs: List[dict] = None,
) -> None:
    """
    Scrape all SWIFT codes for a single country.
    Mirrors the n8n loop:
      - normalize & lookup ISO
      - freshness decision
      - pagination through pages
    """
    # Important: only create a new dict if freshness is None. Using `or {}`
    # would drop a passed-in empty dict and prevent updates from persisting.
    if freshness is None:
        freshness = {}
    all_docs = all_docs if all_docs is not None else []

    # 'country_href' looks like '/netherlands_swift_codes.html'
    # Use this to derive a 'raw' country name (similar to your n8n replace(/[-\/0-9]/g,""))
    raw_country_from_href = country_href.strip("/").split("_")[0]
    country_name = normalize_country_name(raw_country_from_href or country_label)
    iso2, iso3, matched_name = lookup_iso(country_name)

    print(
        f"[COUNTRY] {country_label} -> normalized='{country_name}', "
        f"iso2={iso2}, iso3={iso3}, matched='{matched_name}'"
    )

    ok, reason = should_scrape(iso2, freshness)
    print(f"[FRESHNESS] {country_label}: {reason}")
    if not ok:
        return

    current_path = country_href
    total_rows = 0

    while current_path:
        rows, next_href = parse_country_page(current_path)

        # decorate rows with country + iso info
        docs = []
        for row in rows:
            doc = {
                "iso_code": iso2,
                "iso3": iso3,
                "country": country_name,
                "page": current_path,
                **row,
            }
            docs.append(doc)

        if coll is not None:
            try:
                save_documents_mongo(coll, docs)
            except Exception as e:
                print(f"[MONGO ERROR] Failed to save to MongoDB: {e}")

        # Always add to all_docs for JSON output
        all_docs.extend(docs)
        total_rows += len(docs)

        current_path = next_href
        # be nice to the server
        time.sleep(1)

    # Update freshness
    if iso2:
        freshness[iso2] = datetime.now(timezone.utc).isoformat()
        print(f"[FRESHNESS] Updated iso2={iso2} to now. Total rows: {total_rows}")


def main():
    # 1) Load freshness map (similar to workflowStaticData('global').lastScrapedAt)
    freshness = load_freshness()

    # 2) Get country links
    country_links = get_country_links()

    # Optional: connect to Mongo (make it truly optional)
    coll = None
    try:
        coll = get_mongo_collection()
    except Exception as e:
        print(f"[MONGO] MongoDB not available: {e}")
        print("[MONGO] Will save to JSON file instead")

    # 3) Collect all documents
    all_docs = []

    # 4) Iterate countries (similar to SplitInBatches in n8n)
    for href, label in country_links:
        try:
            scrape_country(href, label, coll=coll, freshness=freshness, all_docs=all_docs)
        except Exception as e:
            print(f"[ERROR] While scraping {label} ({href}): {e}")

    # 5) Save to JSON file
    if all_docs:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(all_docs, f, indent=2, default=str)
        print(f"[JSON] Saved {len(all_docs)} documents to {DATA_FILE}")

    # 6) Persist updated freshness map
    save_freshness(freshness)
    print("[DONE] Scrape finished.")


if __name__ == "__main__":
    main()

