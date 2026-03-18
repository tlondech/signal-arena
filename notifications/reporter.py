import logging
import webbrowser
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

OUTCOME_LABELS = {
    "home_win": "Home Win",
    "draw": "Draw",
    "away_win": "Away Win",
}


def open_report(html_path: str = "index.html") -> None:
    """Opens index.html in the default browser."""
    abs_path = Path(html_path).resolve()
    url = abs_path.as_uri()
    logger.info("Opening report in browser: %s", url)
    webbrowser.open(url)


def print_summary(signals: list[dict]) -> None:
    """Prints a concise summary to stdout."""
    today = date.today().strftime("%Y-%m-%d")
    print(f"\n{'='*50}")
    print(f"  Signal Arena — {today}")
    print(f"{'='*50}")

    if not signals:
        print("  No signals detected today.")
        print(f"{'='*50}\n")
        return

    total_signals = 0
    for match in signals:
        kickoff = match.get("kickoff_local", match.get("kickoff", ""))
        league = match.get("league_name", "")
        league_prefix = f"{league} | " if league else ""
        print(f"\n  [ {league_prefix}{match['home_team']} vs {match['away_team']} | {kickoff} ]")
        for s in match["signals"]:
            ev_pct = s["ev"] * 100
            print(f"    {s['outcome_label']:<12} @ {s['odds']:.2f}  "
                  f"(prob {s['true_prob'] * 100:.1f}%  EV {ev_pct:+.1f}%)")
            total_signals += 1

    print(f"\n  Total signals detected: {total_signals} across {len(signals)} match(es)")
    print(f"{'='*50}\n")
