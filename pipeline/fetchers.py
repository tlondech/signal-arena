"""Sport-specific fetch strategies.

Each concrete class handles the data-gathering phase for one sport and returns
a ``FetchResult``.  The ``FETCHERS`` registry maps ``LeagueConfig.sport_type``
strings to the appropriate singleton.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date as _date
from typing import Protocol

from config import LeagueConfig, _current_season
from extractors.espn_basketball_client import ESPNBasketballClient
from extractors.espn_soccer_client import ESPNSoccerClient
from extractors.espn_tennis_client import ESPNTennisClient
from pipeline.evaluate import build_features
from pipeline.fetch import fetch_league_data
from pipeline.helpers import build_leg2_map

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data contract
# ---------------------------------------------------------------------------

@dataclass
class FetchResult:
    """Uniform return type from any LeagueFetcher.fetch() call."""
    upcoming_events: list[dict] = field(default_factory=list)
    raw_fixtures:    list[dict] = field(default_factory=list)
    stage_map:       dict       = field(default_factory=dict)
    crest_map:       dict       = field(default_factory=dict)
    round_map:       dict | None = None   # tennis only
    seed_map:        dict | None = None   # tennis only; {frozenset({p1, p2}): {player_name_lower: int}}
    short_name_map:  dict | None = None   # {full_name: short_name} (all sports)
    features:        dict       = field(default_factory=dict)  # football only
    odds_client:     object | None = None


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class LeagueFetcher(Protocol):
    """Contract for sport-specific data fetch and preparation strategies."""

    def fetch(
        self,
        league: LeagueConfig,
        cfg,
        name_map: dict,
        dry_run: bool,
    ) -> FetchResult: ...


# ---------------------------------------------------------------------------
# Concrete fetchers
# ---------------------------------------------------------------------------

class FootballFetcher:
    """Fetches ESPN fixture history, builds features and leg-2 context."""

    _short_name_map_cache: dict | None = None
    _pool_fixtures_cache: dict[tuple[str, int], list[dict]] = {}  # (pool_key, season) → fixtures

    def fetch(
        self,
        league: LeagueConfig,
        cfg,
        name_map: dict,
        dry_run: bool,
    ) -> FetchResult:
        season = league.season_override if league.season_override is not None else _current_season()
        logger.debug(
            "--- League: %s (key=%s, season=%d) ---",
            league.display_name, league.key, season,
        )
        upcoming_events, raw_fixtures, stage_map, crest_map, odds_client = fetch_league_data(
            league, cfg, name_map, season=season, dry_run=dry_run,
        )

        if dry_run or not upcoming_events:
            return FetchResult(
                upcoming_events=upcoming_events,
                raw_fixtures=raw_fixtures,
                stage_map=stage_map,
                crest_map=crest_map,
                odds_client=odds_client,
            )

        # Cache primary fixtures so other leagues can pool this league without a second fetch
        if raw_fixtures:
            cache_key = (league.key, season)
            if cache_key not in FootballFetcher._pool_fixtures_cache:
                tagged = [{**f, "_pool_source": league.key} for f in raw_fixtures]
                FootballFetcher._pool_fixtures_cache[cache_key] = tagged

        # Fetch auxiliary fixtures for cross-league DC pooling (covers last season + current)
        auxiliary_fixtures: list[dict] = []
        if league.pool_leagues:
            espn_pool = ESPNSoccerClient()
            for pool_key in league.pool_leagues:
                if pool_key not in ESPNSoccerClient.LEAGUE_MAP:
                    logger.warning(
                        "[%s] pool_leagues key %r not in LEAGUE_MAP — skipping.",
                        league.key, pool_key,
                    )
                    continue
                cache_key = (pool_key, season)
                if cache_key in FootballFetcher._pool_fixtures_cache:
                    pool_fixtures = FootballFetcher._pool_fixtures_cache[cache_key]
                    logger.info(
                        "[%s] Pooled %d fixture(s) from %r (cached).",
                        league.key, len(pool_fixtures), pool_key,
                    )
                else:
                    try:
                        pool_fixtures = espn_pool.fetch_fixtures(
                            _date(season - 1, 7, 1), _date.today(), leagues=[pool_key],
                        )
                        for f in pool_fixtures:
                            f["_pool_source"] = pool_key
                        FootballFetcher._pool_fixtures_cache[cache_key] = pool_fixtures
                        logger.info(
                            "[%s] Pooled %d fixture(s) from %r.",
                            league.key, len(pool_fixtures), pool_key,
                        )
                    except Exception as exc:
                        logger.warning(
                            "[%s] Pool fetch from %r failed: %s — continuing without.",
                            league.key, pool_key, exc,
                        )
                        continue
                auxiliary_fixtures.extend(pool_fixtures)

            # Extend name auto-patching with pool fixture names to resolve
            # promoted-team Winamax names that have no primary-league ESPN history yet.
            if auxiliary_fixtures:
                from models.features import auto_patch_name_map
                winamax_names = (
                    {ev["home_team"] for ev in upcoming_events}
                    | {ev["away_team"] for ev in upcoming_events}
                )
                pool_espn_names = (
                    {f["home_team"] for f in auxiliary_fixtures}
                    | {f["away_team"] for f in auxiliary_fixtures}
                )
                auto_patch_name_map(
                    league.key, winamax_names, pool_espn_names, name_map, cfg.team_map_dir,
                )

        leg2_map = build_leg2_map(upcoming_events, raw_fixtures, name_map, league.key)
        if leg2_map:
            logger.info("[%s] Detected %d Leg 2 fixture(s).", league.display_name, len(leg2_map))

        features = build_features(raw_fixtures, name_map, league, cfg, auxiliary_fixtures=auxiliary_fixtures)
        features["leg2_map"] = leg2_map

        if FootballFetcher._short_name_map_cache is None:
            FootballFetcher._short_name_map_cache = _build_football_short_name_map()

        return FetchResult(
            upcoming_events=upcoming_events,
            raw_fixtures=raw_fixtures,
            stage_map=stage_map,
            crest_map=crest_map,
            features=features,
            short_name_map=FootballFetcher._short_name_map_cache,
            odds_client=odds_client,
        )


class TennisFetcher:
    """Fetches live odds for tennis; builds round and seed maps once per run."""

    _round_map_cache:      dict | None = None  # class-level: shared across all league iterations
    _seed_map_cache:       dict | None = None
    _short_name_map_cache: dict | None = None

    def fetch(
        self,
        league: LeagueConfig,
        cfg,
        name_map: dict,
        dry_run: bool,
    ) -> FetchResult:
        season = league.season_override if league.season_override is not None else _current_season()
        upcoming_events, _, _, _, odds_client = fetch_league_data(
            league, cfg, name_map, season=season, dry_run=dry_run,
        )

        if dry_run:
            return FetchResult(upcoming_events=upcoming_events, odds_client=odds_client)

        if TennisFetcher._round_map_cache is None:
            TennisFetcher._round_map_cache, TennisFetcher._seed_map_cache, TennisFetcher._short_name_map_cache = _build_tennis_maps()

        return FetchResult(
            upcoming_events=upcoming_events,
            round_map=TennisFetcher._round_map_cache,
            seed_map=TennisFetcher._seed_map_cache,
            short_name_map=TennisFetcher._short_name_map_cache,
            odds_client=odds_client,
        )


class NBAFetcher:
    """Fetches live NBA odds; builds stage map once per run."""

    _stage_map_cache:      dict | None = None
    _short_name_map_cache: dict | None = None

    def fetch(
        self,
        league: LeagueConfig,
        cfg,
        name_map: dict,
        dry_run: bool,
    ) -> FetchResult:
        upcoming_events, _, _, _, odds_client = fetch_league_data(
            league, cfg, name_map, season=0, dry_run=dry_run,
        )

        if dry_run:
            return FetchResult(upcoming_events=upcoming_events, odds_client=odds_client)

        if NBAFetcher._stage_map_cache is None:
            NBAFetcher._stage_map_cache, NBAFetcher._short_name_map_cache = _build_nba_maps()
        stage_map, short_name_map = NBAFetcher._stage_map_cache, NBAFetcher._short_name_map_cache
        return FetchResult(
            upcoming_events=upcoming_events,
            stage_map=stage_map,
            short_name_map=short_name_map,
            odds_client=odds_client,
        )


# ---------------------------------------------------------------------------
# Short name map builders (one per sport, keyed by ESPN displayName)
# ---------------------------------------------------------------------------

def _build_football_short_name_map() -> dict[str, str]:
    """Fetches ESPN upcoming football matches; returns {espn_displayName: shortDisplayName}."""
    try:
        matches = ESPNSoccerClient().fetch_upcoming_matches()
        short_name_map: dict[str, str] = {}
        for m in matches:
            if m.metadata.get("home_short_name"):
                short_name_map[m.home_team] = m.metadata["home_short_name"]
            if m.metadata.get("away_short_name"):
                short_name_map[m.away_team] = m.metadata["away_short_name"]
        return short_name_map
    except Exception as e:
        logger.debug("Football short name map fetch failed (non-fatal): %s", e)
        return {}

def _build_tennis_maps() -> tuple[dict, dict, dict]:
    """Fetches ESPN upcoming tennis matches; returns (round_map, seed_map, short_name_map).

    round_map:       {frozenset({p1, p2}): compact_round}
    seed_map:        {frozenset({p1, p2}): {player_name_lower: int}}
    short_name_map:  {full_name: short_name}  (e.g. "Carlos Alcaraz" → "C. Alcaraz")
    """
    try:
        matches = ESPNTennisClient().fetch_upcoming_matches()
        round_map = {
            frozenset({m.home_team.lower(), m.away_team.lower()}): m.metadata["round"]
            for m in matches
            if m.metadata.get("round")
        }
        seed_map: dict = {}
        for m in matches:
            home_seed = m.metadata.get("home_seed")
            away_seed = m.metadata.get("away_seed")
            if home_seed is not None or away_seed is not None:
                entry: dict = {}
                if home_seed is not None:
                    entry[m.home_team.lower()] = home_seed
                if away_seed is not None:
                    entry[m.away_team.lower()] = away_seed
                seed_map[frozenset({m.home_team.lower(), m.away_team.lower()})] = entry
        short_name_map: dict[str, str] = {}
        for m in matches:
            for espn_name, meta_key in [(m.home_team, "home_short_name"), (m.away_team, "away_short_name")]:
                short = m.metadata.get(meta_key)
                if short:
                    short_name_map[espn_name] = short
                    # Also index reversed word order so "Zheng Qinwen" (ESPN last-first)
                    # matches "Qinwen Zheng" (Odds API first-last)
                    parts = espn_name.split()
                    if len(parts) == 2:
                        short_name_map[f"{parts[1]} {parts[0]}"] = short
        return round_map, seed_map, short_name_map
    except Exception as e:
        logger.debug("Tennis maps fetch failed (non-fatal): %s", e)
        return {}, {}, {}


def _build_nba_maps() -> tuple[dict, dict]:
    """Fetches ESPN upcoming NBA games; returns (stage_map, short_name_map).

    stage_map:      {frozenset({home, away}): stage_label}
    short_name_map: {full_name: short_name}  (e.g. "Charlotte Hornets" → "Hornets")
    """
    try:
        matches = ESPNBasketballClient().fetch_upcoming_matches()
        stage_map = {
            frozenset({m.home_team.lower(), m.away_team.lower()}): m.metadata["stage"]
            for m in matches
            if m.metadata.get("stage")
        }
        short_name_map: dict[str, str] = {}
        for m in matches:
            if m.metadata.get("home_short_name"):
                short_name_map[m.home_team] = m.metadata["home_short_name"]
            if m.metadata.get("away_short_name"):
                short_name_map[m.away_team] = m.metadata["away_short_name"]
        return stage_map, short_name_map
    except Exception as e:
        logger.debug("NBA maps fetch failed (non-fatal): %s", e)
        return {}, {}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

FETCHERS: dict[str, LeagueFetcher] = {
    "football":   FootballFetcher(),
    "tennis":     TennisFetcher(),
    "basketball": NBAFetcher(),
}
