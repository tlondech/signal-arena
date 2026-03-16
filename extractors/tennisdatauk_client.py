"""
Fetches finished tennis match results from tennis-data.co.uk free CSV files.
No auth — plain HTTP GET of a CSV, same pattern as FootballDataClient.

ATP URL:  http://www.tennis-data.co.uk/{year}/{slug}.csv
WTA URL:  http://www.tennis-data.co.uk/{year}wta/{slug}.csv

Columns used: Winner, Loser, Date
"""
import io
import logging
import urllib.request
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)

BASE_URL = "http://www.tennis-data.co.uk"
TIMEOUT  = 20

# Maps the tournament portion of an Odds API league key to the tennis-data.co.uk slug.
# Key = everything after "tennis_atp_" / "tennis_wta_" in the league key.
_SLUG_MAP: dict[str, str] = {
    "australian_open":      "ausopen",
    "french_open":          "frenchopen",
    "roland_garros":        "frenchopen",
    "wimbledon":            "wimbledon",
    "us_open":              "usopen",
    "miami_open":           "miami",
    "indian_wells_masters": "indianwells",
    "indian_wells":         "indianwells",
    "monte_carlo_masters":  "montecarlo",
    "madrid_open":          "madrid",
    "italian_open":         "rome",
    "rome":                 "rome",
    "canadian_open":        "canada",
    "western_southern_open":"cincinnati",
    "cincinnati":           "cincinnati",
    "shanghai_masters":     "shanghai",
    "paris_masters":        "paris",
    "vienna":               "vienna",
    "basel":                "basel",
    "stuttgart":            "stuttgart",
    "halle":                "halle",
    "queens_club":          "queens",
    "eastbourne":           "eastbourne",
    "dubai":                "dubai",
    "doha":                 "doha",
    "barcelona_open":       "barcelona",
    "hamburg_open":         "hamburg",
    "washington":           "washington",
    "us_open_series":       "washington",
}


def _league_key_to_slug(league_key: str) -> str | None:
    """Extracts the tournament slug for tennis-data.co.uk from an Odds API league key."""
    for prefix in ("tennis_atp_", "tennis_wta_"):
        if league_key.startswith(prefix):
            tour_part = league_key[len(prefix):]
            return _SLUG_MAP.get(tour_part, tour_part.replace("_", ""))
    return None


def fetch_tennis_results(league_key: str, year: int) -> list[dict]:
    """
    Fetches completed match results for one tournament/year.

    Returns a list of:
      {"winner": str, "loser": str, "match_date": datetime}

    Returns [] on any failure (non-fatal — settlement just skips this tournament).
    """
    slug = _league_key_to_slug(league_key)
    if slug is None:
        logger.debug("No tennis-data.co.uk slug for league key '%s' — skipping.", league_key)
        return []

    is_wta = league_key.startswith("tennis_wta_")
    url = f"{BASE_URL}/{year}wta/{slug}.csv" if is_wta else f"{BASE_URL}/{year}/{slug}.csv"

    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            raw = r.read()
    except Exception as e:
        logger.debug("tennis-data.co.uk: could not fetch %s: %s", url, e)
        return []

    try:
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding="utf-8", on_bad_lines="skip")
        except UnicodeDecodeError:
            df = pd.read_csv(io.BytesIO(raw), encoding="latin-1", on_bad_lines="skip")
    except Exception as e:
        logger.debug("tennis-data.co.uk: could not parse CSV from %s: %s", url, e)
        return []

    results = []
    for _, row in df.iterrows():
        winner = row.get("Winner")
        loser  = row.get("Loser")
        date   = row.get("Date")
        try:
            if pd.isna(winner) or pd.isna(loser) or pd.isna(date):
                continue
        except (TypeError, ValueError):
            continue
        try:
            match_date = pd.to_datetime(str(date), dayfirst=True).to_pydatetime()
        except Exception:
            continue
        results.append({
            "winner":     str(winner).strip(),
            "loser":      str(loser).strip(),
            "match_date": match_date,
        })

    logger.debug("tennis-data.co.uk: %d results from %s", len(results), url)
    return results
