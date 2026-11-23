import { useEffect, useRef, useState } from 'react';
import { Alert, Badge, CloseButton, Group, Loader, Progress, SegmentedControl, Text, TextInput, Tooltip } from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { useVirtualizer } from '@tanstack/react-virtual';
import {
  IconArrowDown, IconArrowUp, IconBulb, IconFileCheck, IconMail, IconSearch, IconWorld,
} from '@tabler/icons-react';
import { loadJobs, setSort, setView } from '../actions';
import { useApp } from '../store';
import type { JobRow, JobStatus, LiveJob } from '../types';

export const STATUS: Record<JobStatus, { label: string; color: string }> = {
  ready: { label: 'Ready', color: 'green' },
  'apply on site': { label: 'On site', color: 'brand' },
  done: { label: 'Done', color: 'gray' },
  rejected: { label: 'Rejected', color: 'red' },
  found: { label: 'Found', color: 'teal' },
};

function sinceDays(iso: string) {
  const d = Math.floor((Date.now() - Date.parse(iso)) / 86400000);
  return Number.isNaN(d) ? '' : d <= 0 ? 'today' : `${d}d ago`;
}

const liveRow = (j: LiveJob): JobRow => ({
  id: j.id, status: 'found', why: '', match: j.match, date: j.date, ago: sinceDays(j.date), company: j.company,
  title: j.title, where: j.where, salary: j.salary, email: false, hasCv: false,
});

const VIEWS = [
  { value: 'ready', label: 'Ready to draft' },
  { value: 'site', label: 'Apply on site' },
  { value: 'matches', label: 'All matches' },
  { value: 'done', label: 'Done' },
  { value: 'all', label: 'Everything' },
];

const COLUMNS: { key: string; label: string; tip: string }[] = [
  { key: 'match', label: '', tip: 'Strong matches first (a keyword is in the title)' },
  { key: 'status', label: 'Status', tip: 'Ready: has an email for a draft. On site: apply on the company site.' },
  { key: 'company', label: 'Company', tip: '' },
  { key: 'role', label: 'Role', tip: '' },
  { key: 'location', label: 'Location', tip: '' },
  { key: 'salary', label: 'Salary', tip: '' },
  { key: 'posted', label: 'Posted', tip: '' },
];

function Row({ job, selected, onClick }: { job: JobRow; selected: boolean; onClick: () => void }) {
  const st = STATUS[job.status] ?? { label: job.status, color: 'gray' };
  return (
    <div className={`job-row${selected ? ' selected' : ''}`} onClick={onClick} role="row" aria-selected={selected}>
      <span className="cell">
        <Tooltip label={job.match === 'strong' ? 'Strong match: a keyword is in the title'
          : 'Partial match: a keyword is only in the description, or part of one is in the title'}>
          <span className={`match-dot ${job.match || 'none'}`} />
        </Tooltip>
      </span>
      <span className="cell">
        <Badge size="sm" variant="light" color={st.color} leftSection={job.email ? <IconMail size={11} />
          : job.status === 'apply on site' ? <IconWorld size={11} /> : undefined}>{st.label}</Badge>
      </span>
      <span className="cell strong" title={job.company}>{job.company}</span>
      <span className="cell" title={job.title}>
        {job.title}
        {job.hasCv && <Tooltip label="You have a CV for this job"><IconFileCheck size={14} className="has-cv" /></Tooltip>}
      </span>
      <span className="cell dim" title={job.where}>{job.where}</span>
      <span className="cell dim" title={job.salary}>{job.salary}</span>
      <span className="cell dim">{job.ago}</span>
    </div>
  );
}

export function JobList() {
  const jobs = useApp((s) => s.jobs);
  const loading = useApp((s) => s.jobsLoading);
  const view = useApp((s) => s.view);
  const sort = useApp((s) => s.sort);
  const desc = useApp((s) => s.desc);
  const selected = useApp((s) => s.selected);
  const set = useApp((s) => s.set);
  const [query, setQuery] = useState(useApp.getState().query);
  const [debounced] = useDebouncedValue(query, 200);
  const parent = useRef<HTMLDivElement>(null);
  const live = useApp((s) => s.live);
  const run = useApp((s) => s.run);
  const total = useApp((s) => s.boot?.sources ?? 0);
  // Sites that have answered in this run: the "source" lines Activity got since the run started.
  const sitesDone = useApp((s) => {
    let n = 0;
    for (let i = s.log.length - 1; i >= 0 && s.log[i].type !== 'run'; i--) if (s.log[i].type === 'source') n++;
    return n;
  });
  const searching = run !== null && (live.length > 0 || sitesDone > 0);
  const rows = searching ? live.map(liveRow) : (jobs?.rows ?? []);

  useEffect(() => {
    if (debounced === useApp.getState().query) return;
    set({ query: debounced });
    void loadJobs();
  }, [debounced, set]);

  const virtual = useVirtualizer({ count: rows.length, getScrollElement: () => parent.current,
    estimateSize: () => 38, overscan: 12 });

  // Arrow keys move through the list; the selected row stays in view.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!['ArrowDown', 'ArrowUp'].includes(e.key)) return;
      const t = e.target as HTMLElement;
      if (t.closest('input, textarea, [role="listbox"], .mantine-Modal-content')) return;
      const { jobs: j, selected: sel } = useApp.getState();
      if (!j?.rows.length) return;
      e.preventDefault();
      const i = j.rows.findIndex((r) => r.id === sel);
      const next = Math.max(0, Math.min(j.rows.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)));
      set({ selected: j.rows[next].id });
      virtual.scrollToIndex(next, { align: 'auto' });
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [set, virtual]);

  const counts: Record<string, number | undefined> = { ready: jobs?.ready, site: jobs?.site };

  return (
    <div className="joblist">
      <Group className="joblist-bar" gap="sm" wrap="nowrap" justify="space-between">
        <SegmentedControl size="xs" value={view} onChange={setView} data={VIEWS.map((v) => ({
          value: v.value,
          label: counts[v.value] !== undefined ? `${v.label} · ${counts[v.value]}` : v.label,
        }))} />
        <TextInput id="job-search" size="xs" placeholder="Search jobs  (Ctrl+F)"
          leftSection={<IconSearch size={14} />} value={query} onChange={(e) => setQuery(e.currentTarget.value)}
          rightSection={query ? <CloseButton size="xs" onClick={() => setQuery('')} aria-label="Clear" /> : null}
          onKeyDown={(e) => e.key === 'Escape' && setQuery('')} style={{ flex: 1, minWidth: 140, maxWidth: 320 }} />
      </Group>

      <Group className="joblist-meta" gap="xs" justify="space-between" wrap="nowrap">
        <Text size="xs" c="dimmed">
          {searching ? <>Live results · <b>{live.length}</b> found so far</> : jobs ? <>
            <b>{rows.length.toLocaleString()}</b> shown · {jobs.ready} ready · {jobs.site} on company sites ·{' '}
            {jobs.total.toLocaleString()} jobs checked{jobs.updated ? ` · updated ${jobs.updated}` : ''}
          </> : 'Loading...'}
        </Text>
        {loading && <Loader size={12} />}
      </Group>
      {searching && (
        <div className="live-bar">
          <Group justify="space-between" mb={6} wrap="nowrap">
            <Group gap={8} wrap="nowrap">
              <Loader size={14} />
              <Text size="sm" fw={600}>Searching job sites: {Math.min(sitesDone, total)} of {total} done</Text>
            </Group>
            <Text size="sm" c="dimmed">{live.length} match{live.length === 1 ? '' : 'es'} so far</Text>
          </Group>
          <Progress value={total ? (Math.min(sitesDone, total) / total) * 100 : 0} size="sm" animated />
          <Text size="xs" c="dimmed" mt={6}>Matches appear here as each site answers. Click one to read it while the
            rest are searched; the full list with emails replaces this when the search ends.</Text>
        </div>
      )}
      {!searching && jobs?.hint && (
        <Alert className="hint" variant="light" color="yellow" icon={<IconBulb size={16} />} p="xs">
          <Text size="xs">Few matches. {jobs.hint}</Text>
        </Alert>
      )}

      <div className="job-head" role="row">
        {COLUMNS.map((c) => (
          <Tooltip key={c.key} label={c.tip} disabled={!c.tip}>
            <button className={`cell head${sort === c.key ? ' active' : ''}`} onClick={() => setSort(c.key)}>
              {c.label || <span className="match-dot strong" />}
              {sort === c.key && (desc ? <IconArrowUp size={12} /> : <IconArrowDown size={12} />)}
            </button>
          </Tooltip>
        ))}
      </div>

      <div className="job-scroll" ref={parent} role="grid">
        {rows.length === 0 && jobs && !searching && (
          <div className="empty">
            <Text fw={600}>{jobs.total ? 'No jobs in this view' : 'No jobs yet'}</Text>
            <Text size="sm" c="dimmed">{query ? 'Nothing matches your search.' : jobs.total
              ? 'Try another tab above, or loosen the filter on the left.'
              : 'Pick a job type and your country on the left, then press Find jobs (F5).'}</Text>
          </div>
        )}
        <div style={{ height: virtual.getTotalSize(), position: 'relative' }}>
          {virtual.getVirtualItems().map((v) => {
            const job = rows[v.index];
            return (
              <div key={job.id} style={{ position: 'absolute', top: 0, left: 0, right: 0, height: v.size,
                transform: `translateY(${v.start}px)` }}>
                <Row job={job} selected={job.id === selected} onClick={() => set({ selected: job.id })} />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
