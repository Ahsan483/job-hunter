// One store for the whole window. Components read slices with useApp(s => s.x); actions.ts changes it.
import { create } from 'zustand';
import type {
  AutoRun, Boot, FilterState, JobsResult, LiveJob, LogEntry, LoggedEntry, Models, Prefs, Profile, SetupStep, Summary,
} from './types';

const MAX_LOG = 2500;
let nextId = 1;

export interface AppState {
  boot: Boot | null;
  bootError: string | null;
  filter: FilterState | null;
  filterError: { field?: string; message: string } | null;
  profile: Profile | null;
  setup: SetupStep[];
  models: Models | null;
  autorun: AutoRun;
  prefs: Prefs;

  /** What this window's run is doing ("Searching 15 job sources"), or null when idle. */
  run: { what: string; since: number } | null;
  /** Auto-run (or another window) holds the lock. */
  external: boolean;
  lastSummary: Summary | null;

  view: string;
  query: string;
  sort: string;
  desc: boolean;
  jobs: JobsResult | null;
  /** Matches found so far by the search in progress; replaced by the full list when it ends. */
  live: LiveJob[];
  jobsLoading: boolean;
  selected: string | null;

  log: LoggedEntry[];
  update: { latest: string; downloading: number | null; installing: boolean } | null;

  set: (patch: Partial<AppState>) => void;
  setFilter: (patch: Partial<FilterState>) => void;
  addLog: (entries: LogEntry[]) => void;
  clearLog: () => void;
}

export const useApp = create<AppState>((set) => ({
  boot: null,
  bootError: null,
  filter: null,
  filterError: null,
  profile: null,
  setup: [],
  models: null,
  autorun: null,
  prefs: { sounds: true, theme: 'dark' },
  run: null,
  external: false,
  lastSummary: null,
  view: 'matches',
  query: '',
  sort: 'match',
  desc: false,
  jobs: null,
  live: [],
  jobsLoading: false,
  selected: null,
  log: [],
  update: null,

  set: (patch) => set(patch),
  setFilter: (patch) =>
    set((s) => ({
      filter: s.filter ? { ...s.filter, ...patch } : s.filter,
      filterError: s.filterError && s.filterError.field && s.filterError.field in patch ? null : s.filterError,
    })),
  addLog: (entries) =>
    set((s) => {
      const log = s.log.concat(entries.map((e) => ({ ...e, id: nextId++ }) as LoggedEntry));
      return { log: log.length > MAX_LOG ? log.slice(log.length - MAX_LOG) : log };
    }),
  clearLog: () => set({ log: [] }),
}));

export const busy = (s: AppState) => s.run !== null || s.external;
