// A stand-in backend for `npm run dev` in a normal browser (no Python). Only enough to draw every screen.
import type { Boot, JobsResult } from './types';

const boot: Boot = {
  version: 'dev', frozen: false, dataFolder: 'C:\\Users\\you\\AppData\\Roaming\\Job Hunter',
  configFile: 'config.json', downloadPage: 'https://www.codeprojectsofficial.com/tools',
  repo: 'https://github.com/Ahsan483/job-hunter',
  filter: { keywords: '.NET, C#, ASP.NET', exclude: '', maxAge: 14, modes: ['remote'], openTo: 'me',
    region: 'Pakistan', countries: '', visa: false, google: true, titleOnly: false, jobTypes: ['Software / .NET'],
    presetKeywords: '.NET, C#, ASP.NET' },
  presets: ['Software / .NET', 'Software (any stack)', 'Design'],
  openTo: [{ value: 'me', label: 'Worldwide + my country' }, { value: 'countries', label: 'Countries I pick' },
    { value: 'anywhere', label: 'Any country' }],
  workModes: [{ value: 'remote', label: 'Remote' }, { value: 'hybrid', label: 'Hybrid' },
    { value: 'onsite', label: 'On-site' }],
  views: [{ value: 'matches', label: 'All matches' }],
  profile: { name: 'Jane Doe', title: 'Full-Stack Engineer', roles: 4 },
  setup: [
    { id: 'gemini', done: true, title: 'Connect Gemini (free)', note: 'Gemini writes your tailored CVs.' },
    { id: 'cv', done: true, title: 'Upload your CV  (Jane Doe)', note: 'Gemini reads it once.' },
    { id: 'find', done: true, title: 'Find jobs', note: 'Pick a job type, then press Find jobs.' },
    { id: 'gmail', done: false, title: 'Connect Gmail (optional)', note: 'Saves each application as a draft.' },
  ],
  models: { options: [{ value: 'gemini-flash-latest', ok: true, status: 'working' }], selected: '',
    note: '1 of 1 models usable right now.', tone: 'dim' },
  autorun: 'off', running: false, prefs: { sounds: true, theme: 'auto' }, usageStats: true, sources: 22,
  coverage: { sites: 19, groups: [{ name: 'Remote jobs, worldwide', sites: ['Remotive', 'RemoteOK'] }],
    companies: ['Anthropic', 'OpenAI', 'Stripe'] },
};

const jobs: JobsResult = {
  updated: '2026-11-24 02:29', total: 4455, ready: 1, site: 3, hint: '',
  rows: ['Fuku', 'Creative Chaos', 'Secure Privacy', 'MacroAgility Systems'].map((company, i) => ({
    id: `m-${i}`, status: i ? 'apply on site' : 'ready', why: '', match: i < 3 ? 'strong' : 'partial',
    date: '2026-11-22T00:00:00+00:00', ago: `${i + 2}d ago`, company, title: 'Software Engineer (.NET + React)',
    where: 'Remote · Worldwide', salary: i === 0 ? '2k USD / month' : '', email: i === 0, hasCv: false,
  })),
};

const answers: Record<string, unknown> = {
  bootstrap: boot, jobs, job: null, models: boot.models, setup: boot.setup, profile: boot.profile,
  settings: [], keys: { fields: [], file: 'config.json' }, check_update: { latest: 'vdev', newer: false,
    current: 'dev', reachable: true, frozen: false },
};

export const mockBridge = new Proxy({}, {
  get: (_t, name: string) => async () => answers[name] ?? { ok: true },
});
