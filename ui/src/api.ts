// The bridge to backend.py. pywebview exposes the Api object's public methods as window.pywebview.api.<name>,
// each returning a Promise. During `npm run dev` in a normal browser there is no pywebview: a small mock
// backend (mock.ts) answers instead, so the layout can be worked on without Python.
import type {
  ActionResult, AutoRun, Boot, FilterState, JobDetail, JobsResult, KeyField, Models, Prefs, ServerEvent,
  SettingField,
} from './types';

type Bridge = Record<string, (...args: unknown[]) => Promise<unknown>>;

declare global {
  interface Window {
    pywebview?: { api: Bridge };
  }
}

let bridge: Promise<Bridge> | null = null;

function connect(): Promise<Bridge> {
  if (bridge) return bridge;
  bridge = new Promise<Bridge>((resolve) => {
    if (window.pywebview?.api) return resolve(window.pywebview.api);
    window.addEventListener('pywebviewready', () => resolve(window.pywebview!.api), { once: true });
    if (import.meta.env.DEV) {
      setTimeout(() => {
        if (!window.pywebview) import('./mock').then((m) => resolve(m.mockBridge as Bridge));
      }, 400);
    }
  });
  return bridge;
}

export class BackendError extends Error {}

async function call<T>(name: string, ...args: unknown[]): Promise<T> {
  const api = await connect();
  const fn = api[name];
  if (!fn) throw new BackendError(`Job Hunter's engine has no "${name}" action. Reinstall the latest version.`);
  try {
    return (await fn(...args)) as T;
  } catch (e) {
    const text = e instanceof Error ? e.message : String(e);
    throw new BackendError(text || 'Something went wrong inside Job Hunter.');
  }
}

export const api = {
  bootstrap: () => call<Boot>('bootstrap'),
  jobTypes: (names: string[]) =>
    call<{ keywords: string | null; titleOnly: boolean | null; presetKeywords: string }>('job_types', names),
  jobs: (view: string, query: string, sort: string, desc: boolean) => call<JobsResult>('jobs', view, query, sort, desc),
  job: (id: string) => call<JobDetail | null>('job', id),
  findJobs: (f: FilterState) => call<ActionResult>('find_jobs', f),
  autoDraft: (f: FilterState) => call<ActionResult>('auto_draft', f),
  saveFilter: (f: FilterState) => call<ActionResult>('save_filter', f),
  jobAction: (id: string, mode: 'draft' | 'cv' | 'skip' | 'applied') => call<ActionResult>('job_action', id, mode),
  stop: () => call<{ state: 'idle' | 'cleared' | 'stopped' }>('stop'),
  pickCvFile: () => call<string | null>('pick_cv_file'),
  importCv: (path: string) => call<ActionResult>('import_cv', path),
  tailor: (job: { company: string; title: string; url: string; text: string }) => call<ActionResult>('tailor', job),
  openUrl: (url: string) => call<boolean>('open_url', url),
  openJob: (id: string) => call<boolean>('open_job', id),
  openJobFiles: (id: string) => call<number>('open_job_files', id),
  coverLetter: (id: string) => call<string | null>('cover_letter', id),
  openPath: (path: string) => call<boolean>('open_path', path),
  openPlace: (what: string) => call<true | { missing: string }>('open_place', what),
  models: () => call<Models>('models'),
  setModel: (model: string, force = false) =>
    call<{ ok?: boolean; confirm?: string; error?: string; models?: Models }>('set_model', model, force),
  checkModels: () => call<{ ok?: boolean; error?: string; need?: 'gemini'; models?: Models }>('check_models'),
  keys: () => call<{ fields: KeyField[]; file: string }>('keys'),
  testKeys: (values: Record<string, string>) =>
    call<{ error?: string; errors?: Record<string, string | null> }>('test_keys', values),
  saveKeys: (values: Record<string, string>) =>
    call<{ ok: boolean; setup: Boot['setup']; models: Models }>('save_keys', values),
  settings: () => call<SettingField[]>('settings'),
  saveSettings: (values: Record<string, number | string>) => call<ActionResult>('save_settings', values),
  setAutorun: (on: boolean) => call<{ ok?: boolean; error?: string; state: AutoRun }>('set_autorun', on),
  checkUpdate: () =>
    call<{ latest: string | null; newer: boolean; current: string; reachable: boolean; frozen: boolean }>(
      'check_update'),
  updateNow: () => call<{ state: 'source' | 'downloading' }>('update_now'),
  setPrefs: (prefs: Partial<Prefs>) => call<Prefs>('set_prefs', prefs),
  setup: () => call<Boot['setup']>('setup'),
  setUsageStats: (on: boolean) => call<{ ok: boolean; on: boolean }>('set_usage_stats', on),
  users: () => call<number | null>('users'),
  diagnostics: () => call<{ version: string; windows: string; installed: boolean; runs: string }>('diagnostics'),
  profile: () => call<Boot['profile']>('profile'),
};

/** Live updates pushed by backend.py (log lines, run start/end, file changes, update progress). */
export function onServerEvent(handler: (e: ServerEvent) => void): () => void {
  const listener = (e: Event) => handler((e as CustomEvent<ServerEvent>).detail);
  window.addEventListener('jh', listener);
  return () => window.removeEventListener('jh', listener);
}
