"""Shared ESPN public API client.

Thin HTTP transport for all ESPN scoreboard requests.
No API key required. No caching — that is a caller concern.
Subclass this to build sport-specific ESPN clients.
"""

import calendar
import logging
import time
from abc import ABC, abstractmethod
from datetime import date, timedelta, timezone
from datetime import datetime as _datetime

import requests

from constants import ESPN_API_BASE_URL
from extractors.base import MatchData

logger = logging.getLogger(__name__)
_RATE_LIMIT_SECONDS = 0.3
_TIMEOUT = 30


class ESPNClient(ABC):
    """
    Abstract ESPN client. Each sport subclass defines LEAGUE_MAP and implements fetch_recent_results().

    fetch_scoreboard() is the concrete HTTP transport — do not override.
    """

    SPORT: str = ""                  # e.g. "soccer", "basketball", "tennis"
    LEAGUE_MAP: dict[str, str] = {}  # league_key → ESPN slug; override in each subclass

    def fetch_scoreboard(
        self,
        sport: str,
        league: str,
        start_date: date,
        end_date: date,
        limit: int = 500,
    ) -> list[dict]:
        """
        Fetches raw events from the ESPN scoreboard for a date range.

        ESPN rejects ranges longer than ~1 month, so requests spanning multiple
        months are automatically split into per-month chunks and merged.

        Returns the combined raw ``events`` array, or [] on failure.
        """
        url = f"{ESPN_API_BASE_URL}/{sport}/{league}/scoreboard"
        all_events: list[dict] = []

        # Build list of (chunk_start, chunk_end) month-sized windows
        chunks: list[tuple[date, date]] = []
        cur = start_date.replace(day=1)
        while cur <= end_date:
            last_day = calendar.monthrange(cur.year, cur.month)[1]
            chunk_start = max(cur, start_date)
            chunk_end   = min(date(cur.year, cur.month, last_day), end_date)
            chunks.append((chunk_start, chunk_end))
            # Advance to first day of next month
            if cur.month == 12:
                cur = date(cur.year + 1, 1, 1)
            else:
                cur = date(cur.year, cur.month + 1, 1)

        for chunk_start, chunk_end in chunks:
            date_range = f"{chunk_start.strftime('%Y%m%d')}-{chunk_end.strftime('%Y%m%d')}"
            try:
                time.sleep(_RATE_LIMIT_SECONDS)
                r = requests.get(
                    url,
                    params={"dates": date_range, "limit": limit},
                    timeout=_TIMEOUT,
                )
                r.raise_for_status()
                all_events.extend(r.json().get("events", []))
            except Exception as exc:
                logger.warning(
                    "ESPN scoreboard fetch failed (%s/%s %s): %s",
                    sport, league, date_range, exc,
                )

        return all_events

    @abstractmethod
    def fetch_recent_results(self, days_back: int = 7) -> list[MatchData]:
        """
        Returns completed matches from the last N days as MatchData objects.
        Non-fatal — returns [] on failure.
        """
        ...

    # ------------------------------------------------------------------
    # Convenience helper — available to all subclasses
    # ------------------------------------------------------------------

    def _fetch_scoreboard_recent(
        self,
        sport: str,
        league: str,
        days_back: int,
    ) -> list[dict]:
        """Fetches scoreboard events from today-N through today."""
        today = _datetime.now(timezone.utc).date()
        start = today - timedelta(days=days_back)
        return self.fetch_scoreboard(sport, league, start, today)
