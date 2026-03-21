alter table signal_history
  add column if not exists home_short_name text,
  add column if not exists away_short_name text;
