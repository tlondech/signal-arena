// ── Centralised application state ─────────────────────────────
// All module files import this object and mutate its properties
// directly (e.g. `state.activeSport = "basketball"`).
// This keeps a single source of truth without a bundler.

export const state = {
  // ── UI ──────────────────────────────────────────────────────
  mainTab:          "bets",     // "bets" | "history"
  burgerDrawerOpen: false,

  // ── Data ────────────────────────────────────────────────────
  betsData: [],
  histData: [],

  // ── Filters ─────────────────────────────────────────────────
  activeSport:    "football",   // "football" | "basketball" | "tennis"
  activeLeague:   "all",
  activeBetType:  "all",
  teamSearch:     "",
  activeDateBets: "all",        // "all" | "today" | "tomorrow" | "week"
  activeDateHist: "all",        // "all" | "7d" | "30d" | "3m"

  // ── History table ───────────────────────────────────────────
  histSortCol:      "kickoff",
  histSortDir:      "desc",
  histStatusFilter: "settled",

  // ── History pagination ───────────────────────────────────────
  HISTORY_PAGE_SIZE: 50,
  historyPage:       0,
  historyTotal:      0,
  historyLoaded:     [],
  historyFetching:   false,
  historyObserver:   null,
};
