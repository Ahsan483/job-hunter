import { useEffect, useRef, useState } from 'react';
import { ActionIcon, Badge, Group, Loader, Paper, SimpleGrid, Text, Tooltip } from '@mantine/core';
import {
  IconAlertTriangle, IconCircleCheck, IconCircleMinus, IconFile, IconPlayerPlayFilled, IconTrash,
} from '@tabler/icons-react';
import { api } from '../api';
import { useApp } from '../store';
import type { LoggedEntry, Summary } from '../types';

const JOB_COLOR = { READY: 'green', 'ON WEBSITE': 'brand', DRAFTED: 'violet', 'NOT A FIT': 'yellow' } as const;
const JOB_LABEL = { READY: 'Ready', 'ON WEBSITE': 'On site', DRAFTED: 'Drafted', 'NOT A FIT': 'Not a fit' } as const;

function FileLink({ path }: { path: string }) {
  const name = path.split('\\').pop();
  return (
    <button className="file-link" onClick={() => void api.openPath(path)} title={path}>
      <IconFile size={12} /> {name}
    </button>
  );
}

function Link({ to }: { to: string }) {
  if (/^https?:\/\//i.test(to)) {
    return <button className="log-link" onClick={() => void api.openUrl(to)} title={to}>
      {to.replace(/^https?:\/\/(www\.)?/i, '')}</button>;
  }
  return <span className="dim">{to}</span>;
}

function SummaryCard({ s }: { s: Summary }) {
  const stats = s.dry
    ? [['Jobs checked', s.fetched], ['Ready to draft (have an email)', s.candidates]]
    : [['Jobs checked', s.fetched], ['Matches', s.candidates], ['Checked by Gemini', s.gemini], ['Drafts', s.drafts]];
  return (
    <Paper className="summary" p="sm" radius="md">
      <Group justify="space-between" mb={6}>
        <Text size="sm" fw={600}>{s.dry ? 'Search finished' : 'Run finished'}</Text>
        <Text size="xs" c="dimmed">{s.at}</Text>
      </Group>
      <SimpleGrid cols={stats.length} spacing="xs">
        {stats.map(([label, n]) => (
          <div key={label as string}>
            <Text fw={700} size="lg" lh={1.1}>{(n as number).toLocaleString()}</Text>
            <Text size="xs" c="dimmed">{label}</Text>
          </div>
        ))}
      </SimpleGrid>
      {s.notes.length > 0 && (
        <div className="notes">
          {s.notes.map((n) => (
            <Group key={n} gap={6} wrap="nowrap" align="flex-start">
              <IconAlertTriangle size={14} color="var(--mantine-color-yellow-5)" style={{ flexShrink: 0, marginTop: 2 }} />
              <Text size="xs">{n}</Text>
            </Group>
          ))}
        </div>
      )}
    </Paper>
  );
}

function Entry({ e }: { e: LoggedEntry }) {
  switch (e.type) {
    case 'run':
      return (
        <div className="log-run">
          <IconPlayerPlayFilled size={11} /> <span>{e.what}</span><span className="dim">{e.at}</span>
        </div>
      );
    case 'job':
      return (
        <div className="log-job">
          <Badge size="sm" variant="light" color={JOB_COLOR[e.status]} fullWidth>{JOB_LABEL[e.status]}</Badge>
          <span className="company">{e.company}</span>
          <span className="role">{e.role}</span>
          {e.link && <Link to={e.link} />}
          {e.reason && <div className="reason">{e.reason}</div>}
        </div>
      );
    case 'source': {
      const Icon = e.state === 'ok' ? IconCircleCheck : e.state === 'failed' ? IconAlertTriangle : IconCircleMinus;
      return (
        <div className={`log-source ${e.state}`}>
          <Icon size={13} />
          <span className="name">{e.name}</span>
          {e.state !== 'ok' ? <span className="note">{e.note}</span>
            : e.count ? <span>{e.count.toLocaleString()} job{e.count === 1 ? "" : "s"}</span> : <span className="dim">none right now</span>}
        </div>
      );
    }
    case 'filter': {
      const parts = Object.entries(e.counts).filter(([, n]) => n);
      if (!parts.length) return null;
      return <div className="log-text dim">Left out: {parts.map(([k, n]) => `${k} ${n}`).join(' · ')}</div>;
    }
    case 'summary':
      return <SummaryCard s={e} />;
    case 'text':
      return (
        <div className={`log-text ${e.tone}`}>
          {e.tone === 'error' && <IconAlertTriangle size={13} className="icon" />}
          {e.text}
          {e.files.length > 0 && <div className="files">{e.files.map((f) => <FileLink key={f} path={f} />)}</div>}
        </div>
      );
  }
}

function Elapsed({ since }: { since: number }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);
  const s = Math.floor((Date.now() - since) / 1000);
  return <>{s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`}</>;
}

export function ActivityLog() {
  const log = useApp((s) => s.log);
  const run = useApp((s) => s.run);
  const external = useApp((s) => s.external);
  const clear = useApp((s) => s.clearLog);
  const box = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  useEffect(() => {
    const el = box.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [log]);

  return (
    <div className="activity">
      <Group className="activity-head" justify="space-between" wrap="nowrap">
        <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
          <Text className="section-title">Activity</Text>
          {run ? (
            <Group gap={6} wrap="nowrap" style={{ minWidth: 0 }}>
              <Loader size={12} type="dots" />
              <Text size="xs" truncate>{run.what}</Text>
              <Text size="xs" c="dimmed"><Elapsed since={run.since} /></Text>
            </Group>
          ) : external ? (
            <Group gap={6} wrap="nowrap"><Loader size={12} type="dots" />
              <Text size="xs">Auto-run is working in the background</Text></Group>
          ) : <Text size="xs" c="dimmed">Ready</Text>}
        </Group>
        <Tooltip label="Clear the activity log">
          <ActionIcon variant="subtle" color="gray" size="sm" onClick={clear} aria-label="Clear">
            <IconTrash size={14} /></ActionIcon>
        </Tooltip>
      </Group>
      <div className="activity-body" ref={box}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}>
        {log.length === 0 && <Text size="xs" c="dimmed" p="xs">What Job Hunter does shows up here: every site it
          searches, every match, and anything that needs your attention.</Text>}
        {log.map((e) => <Entry key={e.id} e={e} />)}
      </div>
    </div>
  );
}
