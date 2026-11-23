// Data exchanged with backend.py (see the Api class there). Field names match its return values.

export type Tone = 'info' | 'good' | 'warn' | 'error' | 'dim';
export type Need = 'gemini' | 'profile' | 'gmail';
export type AutoRun = 'on' | 'off' | null;
export type JobStatus = 'ready' | 'apply on site' | 'done' | 'rejected' | 'found';

export interface Option {
  value: string;
  label: string;
}

export interface FilterState {
  keywords: string;
  exclude: string;
  maxAge: number;
  modes: string[];
  openTo: string;
  region: string;
  countries: string;
  visa: boolean;
  google: boolean;
  titleOnly: boolean;
  jobTypes: string[];
  presetKeywords: string;
}

export interface Profile {
  name: string;
  title: string;
  roles: number;
}

export interface SetupStep {
  id: 'gemini' | 'cv' | 'find' | 'gmail';
  done: boolean;
  title: string;
  note: string;
}

export interface ModelOption {
  value: string;
  ok: boolean;
  status: string;
}

export interface Models {
  options: ModelOption[];
  selected: string;
  note: string;
  tone: Tone;
}

export interface Prefs {
  sounds: boolean;
  theme: 'dark' | 'light' | 'auto';
}

export interface Boot {
  version: string;
  frozen: boolean;
  dataFolder: string;
  configFile: string;
  downloadPage: string;
  repo: string;
  filter: FilterState;
  presets: string[];
  openTo: Option[];
  workModes: Option[];
  views: Option[];
  profile: Profile | null;
  setup: SetupStep[];
  models: Models;
  autorun: AutoRun;
  running: boolean;
  prefs: Prefs;
  usageStats: boolean;
  sources: number;
  coverage: Coverage;
}

/** What one search reads (bot.coverage): job sites by group, and the company career pages. */
export interface Coverage {
  sites: number;
  groups: { name: string; sites: string[] }[];
  companies: string[];
}

/** A match reported while the search is still running (bot.show_found). */
export interface LiveJob {
  id: string;
  company: string;
  title: string;
  match: '' | 'strong' | 'partial';
  where: string;
  salary: string;
  date: string;
  source: string;
  link: string;
}

export interface JobRow {
  id: string;
  status: JobStatus;
  why: string;
  match: '' | 'strong' | 'partial';
  date: string;
  ago: string;
  company: string;
  title: string;
  where: string;
  salary: string;
  email: boolean;
  hasCv: boolean;
}

export interface JobsResult {
  updated: string;
  total: number;
  ready: number;
  site: number;
  rows: JobRow[];
  hint: string;
}

export interface JobDetail {
  id: string;
  status: JobStatus;
  why: string;
  title: string;
  company: string;
  location: string;
  salary: string;
  job_type: string;
  level: string;
  match: string;
  note: string;
  tags: string;
  email: string;
  email_src: string;
  source: string;
  text: string;
  date: string;
  ago: string;
  where: string;
  link: string;
  cv: string;
  letter: string;
  letterText: boolean;
}

export interface KeyField {
  key: string;
  label: string;
  secret: boolean;
  steps: string[];
  links: { label: string; url: string }[];
  value: string;
}

export interface SettingField {
  key: string;
  label: string;
  min: number;
  max: number;
  note: string;
  value: number;
}

export interface Summary {
  type: 'summary';
  at: string;
  dry: boolean;
  fetched: number;
  candidates: number;
  gemini: number;
  drafts: number;
  notes: string[];
}

export type LogEntry =
  | { type: 'job'; status: 'READY' | 'ON WEBSITE' | 'DRAFTED' | 'NOT A FIT'; source: string; company: string;
      role: string; link: string; reason?: string }
  | { type: 'source'; name: string; count?: number; state: 'ok' | 'failed' | 'skipped'; note?: string }
  | { type: 'filter'; counts: Record<string, number> }
  | Summary
  | { type: 'text'; text: string; tone: Tone; files: string[] }
  | { type: 'run'; what: string; at: string };

export type LoggedEntry = LogEntry & { id: number };

/** Result shapes most actions share: ok, a plain-English error, or something the user must set up first. */
export interface ActionResult {
  ok?: boolean;
  error?: string;
  field?: string;
  need?: Need;
}

export type ServerEvent =
  | { kind: 'log'; data: LogEntry[] }
  | { kind: 'run'; data: { state: 'start'; what: string } }
  | { kind: 'run'; data: { state: 'end'; what: string; stopped: boolean; code: number; summary: Summary | null;
      profile: Profile | null; setup: SetupStep[] } }
  | { kind: 'found'; data: LiveJob[] }
  | { kind: 'jobs-changed'; data: null }
  | { kind: 'models'; data: Models }
  | { kind: 'external-run'; data: boolean }
  | { kind: 'update'; data: { state: 'downloading'; pct: number } | { state: 'installing' }
      | { state: 'failed'; error: string } };
