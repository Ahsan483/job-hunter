// Everything a button does: call backend.py, then show the outcome (notification, dialog, sound).
import { createElement } from 'react';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import { api } from './api';
import { sound } from './sounds';
import { useApp } from './store';
import type { ActionResult, Need, ServerEvent } from './types';
import { KeysDialog } from './dialogs/KeysDialog';
import { SettingsDialog } from './dialogs/SettingsDialog';
import { TailorDialog } from './dialogs/TailorDialog';
import { AboutDialog } from './dialogs/AboutDialog';
import { ReportDialog } from './dialogs/ReportDialog';
import { CoverageDialog } from './dialogs/CoverageDialog';

const get = useApp.getState;

// ---------- feedback ----------

export function toastOk(title: string, message?: string, withSound = true) {
  if (withSound) sound.success();
  notifications.show({ color: 'brand', title, message, autoClose: 4500 });
}

export function toastInfo(title: string, message?: string) {
  sound.notify();
  notifications.show({ color: 'blue', title, message, autoClose: 6000 });
}

export function toastWarn(title: string, message?: string) {
  sound.notify();
  notifications.show({ color: 'yellow', title, message, autoClose: 8000 });
}

export function toastError(message: string, title = 'That did not work') {
  sound.error();
  notifications.show({ color: 'red', title, message, autoClose: 10000 });
}

/** Run an API call; anything thrown is shown as an error notification instead of disappearing. */
export async function guard<T>(work: () => Promise<T>): Promise<T | undefined> {
  try {
    return await work();
  } catch (e) {
    toastError(e instanceof Error ? e.message : String(e), 'Job Hunter hit a problem');
    return undefined;
  }
}

/** The common shapes of an action's answer: ok, a plain-English error, or something to set up first. */
function handle(res: ActionResult | undefined, retryAsCv?: () => void): boolean {
  if (!res) return false;
  if (res.need) {
    askFor(res.need, retryAsCv);
    return false;
  }
  if (res.error) {
    if (res.field && ['keywords', 'maxAge', 'modes', 'countries', 'region'].includes(res.field)) {
      get().set({ filterError: { field: res.field, message: res.error } });
    }
    toastError(res.error, 'Check this first');
    return false;
  }
  return true;
}

/** Something an action needs that is not set up yet: explain it and offer the way to set it up. */
export function askFor(need: Need, retryAsCv?: () => void) {
  sound.notify();
  if (need === 'gemini') {
    openKeys('Connect Gemini first: it is free, takes a minute, and writes every tailored CV.');
    return;
  }
  if (need === 'profile') {
    modals.openConfirmModal({
      title: 'Upload your CV first',
      children: createElement('p', { className: 'modal-text' },
        'Job Hunter writes every tailored CV from the facts in your own CV. Gemini reads it once and builds your ' +
        'profile; nothing is invented.'),
      labels: { confirm: 'Upload my CV', cancel: 'Not now' },
      onConfirm: () => void uploadCv(),
    });
    return;
  }
  modals.openConfirmModal({
    title: 'Gmail is not connected',
    children: createElement('p', { className: 'modal-text' },
      'A draft is saved in your Gmail for you to check and send. Connect Gmail with an app password, or make the ' +
      'CV and cover letter as PDFs instead and apply yourself.'),
    labels: { confirm: 'Connect Gmail', cancel: retryAsCv ? 'Make CV + letter instead' : 'Not now' },
    onConfirm: () => openKeys(),
    onCancel: () => retryAsCv?.(),
  });
}

// ---------- the job list ----------

let jobsSeq = 0;

export async function loadJobs() {
  const { view, query, sort, desc } = get();
  const seq = ++jobsSeq;
  get().set({ jobsLoading: true });
  const res = await guard(() => api.jobs(view, query, sort, desc));
  if (seq !== jobsSeq) return; // a newer request is on its way
  if (!res) return get().set({ jobsLoading: false });
  const selected = get().selected;
  get().set({
    jobsLoading: false,
    jobs: res,
    selected: selected && res.rows.some((r) => r.id === selected) ? selected : (res.rows[0]?.id ?? null),
  });
}

export function setView(view: string) {
  get().set({ view });
  void loadJobs();
}

export function setSort(sort: string) {
  const s = get();
  get().set(s.sort === sort ? { desc: !s.desc } : { sort, desc: false });
  void loadJobs();
}

// ---------- runs ----------

export async function findJobs() {
  const f = get().filter;
  if (!f) return;
  handle(await guard(() => api.findJobs(f)));
}

export async function autoDraft() {
  const f = get().filter;
  if (!f) return;
  handle(await guard(() => api.autoDraft(f)));
}

export async function saveFilter() {
  const f = get().filter;
  if (!f) return;
  if (handle(await guard(() => api.saveFilter(f)))) void findJobs();
}

export async function jobAction(id: string, mode: 'draft' | 'cv' | 'skip' | 'applied') {
  const res = await guard(() => api.jobAction(id, mode));
  handle(res, mode === 'draft' ? () => void jobAction(id, 'cv') : undefined);
}

export async function stopRun() {
  const res = await guard(() => api.stop());
  if (res?.state === 'idle') toastInfo('Nothing is running');
  if (res?.state === 'cleared') toastOk('Cleared', 'A leftover lock from an old run was removed.');
}

export async function uploadCv() {
  const path = await guard(() => api.pickCvFile());
  if (!path) return;
  handle(await guard(() => api.importCv(path)));
}

export function openTailor() {
  modals.open({ title: 'Tailor my CV to a job', size: 'xl', children: createElement(TailorDialog) });
}

export async function submitTailor(job: { company: string; title: string; url: string; text: string }) {
  return handle(await guard(() => api.tailor(job)));
}

const ago = (since: number) => {
  const s = Math.round((Date.now() - since) / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
};

/** Run start and end: a live notification while it works, then the result with a sound. */
export function onRun(e: Extract<ServerEvent, { kind: 'run' }>) {
  const at = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (e.data.state === 'start') {
    get().set({ run: { what: e.data.what, since: Date.now() }, lastSummary: null, live: [] });
    get().addLog([{ type: 'run', what: e.data.what, at }]);
    notifications.show({
      id: 'run', loading: true, title: e.data.what, autoClose: false, withCloseButton: false,
      message: 'Working in the background. Live progress is in Activity.',
    });
    return;
  }
  const d = e.data;
  const since = get().run?.since ?? Date.now();
  get().set({ run: null, lastSummary: d.summary, profile: d.profile, setup: d.setup });
  // Swap the live rows for the finished list in one step, so the list never flashes empty.
  void loadJobs().then(() => get().set({ live: [] }));
  void guard(() => api.models()).then((m) => m && get().set({ models: m }));
  const took = ago(since);
  // What this run wrote to Activity: its matches, and any problem it reported in plain words.
  const log = get().log;
  let first = log.length;
  while (first > 0 && log[first - 1].type !== 'run') first--;
  const mine = log.slice(first);
  const found = mine.filter((x) => x.type === 'job' && (x.status === 'READY' || x.status === 'ON WEBSITE')).length;
  const problem = mine.find((x) => x.type === 'text' && x.tone === 'error');
  const done = (color: string, title: string, message: string) =>
    notifications.update({ id: 'run', loading: false, color, title, message, autoClose: 9000, withCloseButton: true });

  if (d.stopped) {
    sound.notify();
    return done('yellow', 'Run stopped', `${d.what} was stopped after ${took}.`);
  }
  if (d.code !== 0) {
    sound.error();
    return done('red', 'The run ended with a problem', 'The reason is in Activity, in plain words.');
  }
  if (problem && problem.type === 'text') {
    sound.error();
    return done('red', 'Finished with a problem', `${problem.text.slice(0, 160)} Details are in Activity.`);
  }
  const s = d.summary;
  if (!s) {
    sound.success();
    return done('brand', 'Done', `${d.what} finished in ${took}.`);
  }
  const notes = s.notes.length ? ` ${s.notes.length} heads-up in Activity.` : '';
  if (s.dry) {
    const ready = s.candidates ? ` ${s.candidates} have an email for a draft.` : '';
    if (found) sound.success();
    else sound.notify();
    return done(found ? 'brand' : 'yellow', found ? `${found} matching job${found > 1 ? 's' : ''}` : 'No matches',
      found ? `Searched ${s.fetched.toLocaleString()} jobs in ${took}.${ready}${notes}`
        : `Searched ${s.fetched.toLocaleString()} jobs in ${took}. The tip above the list says what to loosen.${notes}`);
  }
  if (s.drafts) sound.success();
  else sound.notify();
  return done(s.drafts ? 'brand' : 'yellow', s.drafts ? `${s.drafts} applications ready` : 'No drafts this time',
    `${s.candidates} matches, ${s.gemini} checked by Gemini, in ${took}.${notes}`);
}

// ---------- AI model ----------

export async function setModel(model: string) {
  let res = await guard(() => api.setModel(model));
  if (res?.confirm) {
    const message = res.confirm;
    const yes = await new Promise<boolean>((resolve) =>
      modals.openConfirmModal({
        title: 'This model is at its limit',
        children: createElement('p', { className: 'modal-text' }, message),
        labels: { confirm: 'Use it anyway', cancel: 'Keep the current model' },
        onConfirm: () => resolve(true), onCancel: () => resolve(false),
      }));
    if (!yes) return;
    res = await guard(() => api.setModel(model, true));
  }
  if (res?.error) return toastError(res.error);
  if (res?.models) get().set({ models: res.models });
}

export async function checkModels() {
  const res = await guard(() => api.checkModels());
  if (!res) return;
  if (res.need) return askFor(res.need);
  if (res.error) return toastError(res.error);
  if (res.models) {
    get().set({ models: res.models });
    toastOk('Models checked', res.models.note);
  }
}

// ---------- accounts, settings, auto-run ----------

export function openKeys(intro?: string) {
  modals.open({ title: 'Connect your accounts', size: 'lg', children: createElement(KeysDialog, { intro }) });
}

export function openSettings() {
  modals.open({ title: 'Settings', size: 'lg', children: createElement(SettingsDialog) });
}

export function openReport() {
  modals.closeAll();
  modals.open({ title: 'Report a problem', size: 'lg', children: createElement(ReportDialog) });
}

export function openCoverage() {
  modals.open({ title: 'What Job Hunter searches', size: 'xl', children: createElement(CoverageDialog) });
}

export function openAbout() {
  modals.open({ title: 'About Job Hunter', size: 'md', children: createElement(AboutDialog) });
}

export async function setAutorun(on: boolean) {
  const res = await guard(() => api.setAutorun(on));
  if (!res) return;
  get().set({ autorun: res.state });
  if (res.error) return toastError(res.error, 'Auto-run could not be changed');
  if (on) toastOk('Auto-run is on', 'Job Hunter searches and drafts every 30 minutes, even with this window closed.');
  else toastInfo('Auto-run is off', 'Searches now run only when you press a button.');
}

export async function openPlace(what: string) {
  const res = await guard(() => api.openPlace(what));
  if (res && typeof res === 'object' && 'missing' in res) toastInfo('Nothing to open yet', res.missing);
}

export async function setPrefs(patch: Partial<{ sounds: boolean; theme: 'dark' | 'light' | 'auto' }>) {
  get().set({ prefs: { ...get().prefs, ...patch } });
  await guard(() => api.setPrefs(patch));
}

// ---------- updates ----------

export async function checkUpdate(quiet: boolean) {
  const res = await guard(() => api.checkUpdate());
  if (!res) return;
  if (res.newer && res.latest) {
    get().set({ update: { latest: res.latest, downloading: null, installing: false } });
    notifications.show({
      id: 'update-available', color: 'brand', autoClose: 15000,
      title: `Job Hunter ${res.latest} is available`,
      message: 'Press Update in the top bar. It installs in a few seconds and keeps all your settings.',
    });
    sound.notify();
  } else if (!quiet) {
    if (!res.reachable) toastError('GitHub could not be reached. Check your internet connection and try again.',
      'Could not check for updates');
    else toastOk('You are up to date', `Job Hunter ${res.current} is the newest version.`);
  }
}

export async function updateNow() {
  const u = get().update;
  if (!u) return;
  const res = await guard(() => api.updateNow());
  if (res?.state === 'source') {
    toastInfo('Running from source', 'The download page is open. Pull the new code with git, or install the app.');
    return;
  }
  get().set({ update: { ...u, downloading: 0 } });
  notifications.show({
    id: 'update', loading: true, autoClose: false, withCloseButton: false,
    title: `Downloading Job Hunter ${u.latest}`, message: 'Starting...',
  });
}

export function onUpdate(e: Extract<ServerEvent, { kind: 'update' }>) {
  const u = get().update;
  const d = e.data;
  if (d.state === 'downloading') {
    if (u) get().set({ update: { ...u, downloading: d.pct } });
    notifications.update({ id: 'update', loading: true, autoClose: false, withCloseButton: false,
      title: `Downloading Job Hunter ${u?.latest ?? ''}`, message: `${d.pct}% downloaded` });
  } else if (d.state === 'installing') {
    if (u) get().set({ update: { ...u, installing: true } });
    sound.success();
    notifications.update({ id: 'update', loading: true, autoClose: false, withCloseButton: false,
      title: 'Installing the update', message: 'Job Hunter closes now and opens again by itself in a few seconds.' });
  } else {
    if (u) get().set({ update: { ...u, downloading: null, installing: false } });
    sound.error();
    notifications.update({ id: 'update', loading: false, color: 'red', autoClose: false, withCloseButton: true,
      title: 'The update could not be downloaded',
      message: `${d.error}. Try again later, or download it from the website (Help > Download page).` });
  }
}
