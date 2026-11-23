-- One row per install per day it was used. Only a random id, the day and the version.
CREATE TABLE IF NOT EXISTS pings (
  id TEXT NOT NULL,
  day TEXT NOT NULL,
  version TEXT NOT NULL,
  PRIMARY KEY (id, day)
);
CREATE INDEX IF NOT EXISTS pings_day ON pings (day);

-- The first day each install was seen (for the all-time install count).
CREATE TABLE IF NOT EXISTS installs (
  id TEXT PRIMARY KEY,
  first_day TEXT NOT NULL
);
