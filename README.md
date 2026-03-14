# Football Value Bet Finder

A statistical betting recommendation engine that identifies value bets in professional football matches. It fetches live odds, models match outcomes using Poisson distributions and Dixon-Coles ratings, and surfaces bets where the bookmaker's implied probability is lower than the model's estimate.

## How It Works

For each upcoming match across supported leagues, the pipeline:

1. **Fetches live odds** from The Odds API (Winamax lines)
2. **Loads historical results** from football-data.co.uk (domestic leagues) or football-data.org (Champions League)
3. **Builds team ratings** using a Dixon-Coles MLE model (with rolling-window fallback), blended with head-to-head stats
4. **Computes expected goals** (λ) per team, adjusted for fatigue, rest days, and UCL second-leg aggregate dynamics
5. **Builds a score probability matrix** via Poisson distribution with Dixon-Coles low-score correction
6. **Calculates Expected Value** (EV = true_prob × decimal_odds − 1) for each outcome
7. **Generates a report** — HTML dashboard + JSON — and opens it in the browser

Bets are recommended when EV exceeds a configurable threshold (default: 5%).

### Supported Markets
- 1X2 (Home Win / Draw / Away Win)
- Over/Under 2.5 goals

### Supported Leagues

| Key | League |
|-----|--------|
| `epl` | Premier League (England) |
| `ligue1` | Ligue 1 (France) |
| `laliga` | La Liga (Spain) |
| `bundesliga` | Bundesliga (Germany) |
| `seriea` | Serie A (Italy) |
| `ucl` | UEFA Champions League |
| `worldcup` | FIFA World Cup |

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API keys

```bash
cp .env.example .env
```

Edit `.env` and fill in your keys:

```env
THE_ODDS_API_KEY=your_key_here         # required — https://the-odds-api.com (500 free req/month)
FOOTBALL_DATA_ORG_API_KEY=your_key     # required for Champions League — https://www.football-data.org (free tier)
```

### 3. Run

```bash
python main.py
```

The report opens automatically in your browser. Results are also saved to `data/latest_report.json`.

---

## Automated Daily Updates

A GitHub Actions workflow (`.github/workflows/daily_update.yml`) runs every 6 hours and commits the updated `index.html` directly to the repository. This lets you host the report as a static GitHub Pages site with no manual intervention.

The workflow can also be triggered manually via `workflow_dispatch`.

---

## Usage

```bash
# Normal run (skips API calls if already run today)
python main.py

# Force re-fetch odds and fixtures regardless of cache
python main.py --force

# Always fetch fresh data from external APIs (use in CI / scheduled runs)
python main.py --fetch

# Enable debug-level logging
python main.py --debug
```

---

## Configuration

All settings can be overridden via `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `THE_ODDS_API_KEY` | — | The Odds API key (required) |
| `FOOTBALL_DATA_ORG_API_KEY` | `""` | football-data.org key (required for UCL) |
| `ENABLED_LEAGUES` | all | Comma-separated league keys, e.g. `epl,laliga` |
| `EV_THRESHOLD` | `0.05` | Minimum EV to surface a bet (5%) |
| `ROLLING_WINDOW` | `5` | Number of recent matches for rolling stats |
| `POISSON_MAX_GOALS` | `8` | Score matrix size (0–N goals) |
| `ODDS_TOTALS_BOOKMAKERS` | `""` | Fallback bookmaker for O/U 2.5 when Winamax has no line, e.g. `pinnacle` |

---

## Project Structure

```
.
├── main.py                          # Pipeline entry point
├── config.py                        # Configuration and league definitions
├── requirements.txt
├── .env.example
├── index.html                       # Generated report (committed by CI for GitHub Pages)
│
├── .github/workflows/
│   └── daily_update.yml             # Runs every 6 hours, auto-commits index.html
│
├── extractors/
│   ├── odds.py                      # The Odds API client (1X2, O/U)
│   ├── footballdata_client.py       # football-data.co.uk CSV client (domestic leagues)
│   ├── footballdataorg_client.py    # football-data.org API client (UCL)
│   ├── soccerdata_client.py         # Alternative data source
│   └── stats.py                     # Stats processing utilities
│
├── models/
│   ├── features.py                  # Feature engineering (Dixon-Coles, H2H, fatigue)
│   └── evaluator.py                 # Poisson probability + EV calculation
│
├── db/
│   └── schema.py                    # SQLAlchemy models (matches, odds, fixtures, bet_history)
│
├── notifications/
│   └── reporter.py                  # HTML + JSON report generation
│
└── data/
    ├── team_name_map.json           # Name mapping (Winamax → canonical)
    ├── crest_map.json               # Team crest URLs
    ├── bets.db                      # SQLite database
    └── latest_report.json           # Most recent report output
```

---

## Statistical Model

### Dixon-Coles Rating
The primary rating system fits a Maximum Likelihood Estimation model over historical fixtures to derive each team's attack and defense strength. A ρ (rho) parameter corrects for the known over/under-frequency of low-score results (0-0, 1-0, 0-1, 1-1).

When fewer than 10 fixtures are available, the model falls back to rolling-window averages.

### Adjustments
- **Head-to-head blending:** H2H stats receive 30% weight when ≥3 historical meetings exist
- **Fatigue:** Teams with <4 days since their last match concede 8% more goals
- **UCL second legs:** Trailing teams receive an attack boost proportional to their goal deficit; leading teams receive a slight defensive orientation

### Expected Value
```
EV = (model_probability × decimal_odds) − 1
```

A positive EV indicates the model estimates a higher probability than the bookmaker's implied odds. Bets are only surfaced when EV > threshold.

---

## Output

### HTML Report (`index.html`)
Interactive dashboard showing:
- Today's value bets grouped by league, with odds, true probability, and EV
- Team form, standings position, rest days
- UCL aggregate context for second legs
- Bet history with settled outcomes (won/lost)
- Filter drawer to narrow bets by league, market, or EV range
- Bet types modal explaining each market in the page header

### JSON Report (`data/latest_report.json`)
Machine-readable version of the same data, suitable for further processing or integration.

### Database (`data/bets.db`)
SQLite database with four tables:
- `matches` — upcoming match metadata
- `odds` — bookmaker odds (h2h and totals)
- `fixtures` — finished match results with xG
- `bet_history` — all recommended bets and their resolved outcomes

---

## External Data Sources

| Source | Usage | Cost |
|--------|-------|------|
| [The Odds API](https://the-odds-api.com) | Live odds (Winamax) | 500 req/month free |
| [football-data.co.uk](https://football-data.co.uk) | Historical results for domestic leagues | Free |
| [football-data.org](https://www.football-data.org) | Champions League fixtures and results | Free tier available |
