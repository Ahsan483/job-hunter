import { useEffect, useState } from 'react';
import {
  Alert, Anchor, Badge, Button, Divider, Group, Loader, Paper, ScrollArea, SimpleGrid, Skeleton, Stack, Text, ThemeIcon,
  Title, Tooltip,
} from '@mantine/core';
import {
  IconBan, IconCheck, IconCircleCheckFilled, IconCopy, IconExternalLink, IconFileText, IconFolderOpen, IconMail,
  IconSearch, IconSparkles, IconUpload, IconBrandGmail, IconWorld,
} from '@tabler/icons-react';
import { api } from '../api';
import { findJobs, guard, jobAction, openCoverage, openKeys, toastError, toastOk, uploadCv } from '../actions';
import { sound } from '../sounds';
import { busy, useApp } from '../store';
import type { JobDetail as Job, SetupStep } from '../types';
import { STATUS } from './JobList';

/** Job posts arrive with stray indents and runs of blank lines: one clean paragraph per block. */
function paragraphs(text: string): string[] {
  return text.replace(/\r/g, '').split(/\n\s*\n+/)
    .map((p) => p.split('\n').map((l) => l.replace(/\s+/g, ' ').trim()).filter(Boolean).join('\n'))
    .filter(Boolean);
}

function host(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

const MATCH_HELP: Record<string, string> = {
  strong: 'Strong: a keyword is in the job title',
  partial: 'Partial: part of a keyword is in the title, or a keyword is only in the description',
};

export async function copy(text: string, what: string) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const t = document.createElement('textarea');
    t.value = text;
    document.body.appendChild(t);
    t.select();
    document.execCommand('copy');
    t.remove();
  }
  sound.tap();
  toastOk(`${what} copied`, undefined, false);
}

function GettingStarted() {
  const setup = useApp((s) => s.setup);
  const run: Record<SetupStep['id'], () => void> = {
    gemini: () => openKeys(), cv: () => void uploadCv(), find: () => void findJobs(), gmail: () => openKeys(),
  };
  const icon = { gemini: IconSparkles, cv: IconUpload, find: IconSearch, gmail: IconBrandGmail };
  const done = setup.filter((s) => s.done).length;
  const coverage = useApp((s) => s.boot?.coverage);
  return (
    <ScrollArea className="detail" type="hover">
      <Stack p="xl" gap="md" maw={640}>
        <div>
          <Title order={3}>{done === setup.length ? 'You are all set' : 'Getting started'}</Title>
          <Text c="dimmed" size="sm" mt={4}>
            {done === setup.length ? 'Pick a job in the list to see it here.'
              : `Pick a job in the list to see it here. New to Job Hunter? ${done} of ${setup.length} steps done.`}
          </Text>
        </div>
        {coverage && (
          <Paper className="coverage-card" p="md" radius="md" onClick={openCoverage}>
            <Group wrap="nowrap" gap="md">
              <ThemeIcon size={40} radius="md" variant="filled"><IconWorld size={22} /></ThemeIcon>
              <div style={{ flex: 1, minWidth: 0 }}>
                <Text fw={600}>One click searches {coverage.sites} job sites and {coverage.companies.length} company
                  career pages</Text>
                <Text size="sm" c="dimmed" mt={2}>Remote boards, national job services and companies like
                  {' '}{coverage.companies.filter((c) => ['OpenAI', 'Stripe', 'Spotify', 'Canva'].includes(c)).join(', ')}.
                  Over 17,000 open jobs, checked in about a minute.</Text>
              </div>
              <Button size="xs" variant="light" onClick={(e) => { e.stopPropagation(); openCoverage(); }}>
                See all</Button>
            </Group>
          </Paper>
        )}
        {setup.map((s) => {
          const Icon = icon[s.id];
          return (
            <Paper key={s.id} className={`step${s.done ? ' done' : ''}`} p="md" withBorder
              onClick={s.done ? undefined : run[s.id]}>
              <Group wrap="nowrap" align="center" gap="md">
                <ThemeIcon size={34} radius="xl" variant="light" color={s.done ? 'green' : 'brand'}>
                  {s.done ? <IconCheck size={18} stroke={2.5} /> : <Icon size={18} />}
                </ThemeIcon>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Text fw={600} size="md">{s.title}</Text>
                  <Text size="sm" c="dimmed" mt={2}>{s.note}</Text>
                </div>
                {s.done
                  ? <Badge color="green" variant="light" size="md">Done</Badge>
                  : <Button size="xs" onClick={run[s.id]}>Set up</Button>}
              </Group>
            </Paper>
          );
        })}
        <Text size="sm"><b>Then, for each job:</b> Draft email + CV when it has an email, or CV + cover letter to
          apply on the company's site. Press Applied when you have sent it. Read every CV and email before you send
          it.</Text>
        <Text size="xs" c="dimmed"><b>Shortcuts:</b> F5 find jobs · Ctrl+F search the list · ↑ ↓ move through jobs ·
          Enter open the job page · Esc back to this page</Text>
      </Stack>
    </ScrollArea>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  if (!children) return null;
  return (
    <div className="fact">
      <Text size="xs" c="dimmed" fw={500}>{label}</Text>
      <Text size="sm">{children}</Text>
    </div>
  );
}

export function JobDetail() {
  const selected = useApp((s) => s.selected);
  const jobs = useApp((s) => s.jobs);
  const isBusy = useApp(busy);
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let live = true;
    if (!selected) return setJob(null);
    setLoading(true);
    void guard(() => api.job(selected)).then((j) => {
      if (!live) return;
      setLoading(false);
      setJob(j ?? null);
    });
    return () => { live = false; };
  }, [selected, jobs]);

  if (!selected) return <GettingStarted />;
  const preview = !job && !loading ? useApp.getState().live.find((j) => j.id === selected) : undefined;
  if (preview) {
    return (
      <ScrollArea className="detail" type="hover">
        <Stack p="xl" gap="md">
          <div>
            <Title order={3} lh={1.25}>{preview.title}</Title>
            <Text c="dimmed" size="sm" mt={4}>{preview.company} · {preview.where}</Text>
          </div>
          <Group gap={6}>
            <Badge color="teal" variant="light">Found just now</Badge>
            {preview.match && <Badge variant="outline" color={preview.match === 'strong' ? 'green' : 'yellow'}>
              {preview.match} match</Badge>}
            {preview.salary && <Badge variant="default">{preview.salary}</Badge>}
          </Group>
          <Alert variant="light" color="brand" icon={<Loader size={16} />}>
            Still searching the other sites. The full description, the application email and the CV buttons appear
            here when the search ends.
          </Alert>
          {preview.link && (
            <Button variant="default" leftSection={<IconExternalLink size={16} />} w="fit-content"
              onClick={() => void api.openUrl(preview.link)}>Open the job post on {host(preview.link)}</Button>
          )}
          <Text size="xs" c="dimmed">Source: {preview.source}</Text>
        </Stack>
      </ScrollArea>
    );
  }
  if (!job) return loading ? <Stack p="lg"><Skeleton h={28} w="70%" /><Skeleton h={16} w="40%" />
    <Skeleton h={120} mt="md" /><Skeleton h={300} /></Stack> : <GettingStarted />;

  const open = job.status === 'ready' || job.status === 'apply on site';
  const st = STATUS[job.status] ?? { label: job.status, color: 'gray' };
  const copyLetter = async () => {
    const text = await guard(() => api.coverLetter(job.id));
    if (text) void copy(text, 'Cover letter');
    else toastError('The cover letter text file is missing. Make the CV + cover letter again.');
  };

  return (
    <div className="detail-wrap">
      <div className="detail-head">
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <div style={{ minWidth: 0 }}>
            <Title order={3} lh={1.25}>{job.title}</Title>
            <Text c="dimmed" size="sm">{job.company} · {job.where}</Text>
          </div>
          {loading && <Loader size="xs" />}
        </Group>
        <Group gap={6} mt="xs">
          <Badge color={st.color} variant="light">{st.label}{job.why ? ` · ${job.why}` : ''}</Badge>
          {job.match && <Tooltip label={MATCH_HELP[job.match]}><Badge variant="outline"
            color={job.match === 'strong' ? 'brand' : 'yellow'}>{job.match} match</Badge></Tooltip>}
          {job.ago && <Badge variant="default">{job.ago}</Badge>}
          {job.cv && <Badge variant="light" color="teal" leftSection={<IconCircleCheckFilled size={12} />}>
            CV made</Badge>}
        </Group>

        <SimpleGrid cols={2} spacing={6} mt="md" className="actions">
          <Tooltip label="Gemini writes a tailored CV and an email for this job and saves them as a Gmail draft. Nothing is sent.">
            <Button leftSection={<IconMail size={16} />} disabled={!(open && job.email) || isBusy}
              onClick={() => void jobAction(job.id, 'draft')}>Draft email + CV</Button>
          </Tooltip>
          <Tooltip label="A tailored CV and cover letter (PDF) to upload on the company's site. Needs no Gmail.">
            <Button variant="light" leftSection={<IconFileText size={16} />}
              disabled={job.status === 'rejected' || isBusy}
              onClick={() => void jobAction(job.id, 'cv')}>CV + cover letter</Button>
          </Tooltip>
        </SimpleGrid>
        <SimpleGrid cols={3} spacing={6} mt={6} className="actions secondary">
          <Tooltip label="Open the job post in your browser (Enter).">
            <Button size="xs" variant="default" leftSection={<IconExternalLink size={16} />} disabled={!job.link}
              onClick={() => void api.openJob(job.id)}>Job page</Button>
          </Tooltip>
          <Tooltip label="Open the CV and cover letter already made for this job.">
            <Button size="xs" variant="default" leftSection={<IconFolderOpen size={16} />} disabled={!job.cv}
              onClick={() => void api.openJobFiles(job.id)}>My CV for it</Button>
          </Tooltip>
          <Tooltip label="Copy the application email address.">
            <Button size="xs" variant="default" leftSection={<IconCopy size={16} />} disabled={!job.email}
              onClick={() => void copy(job.email, 'Email address')}>Email</Button>
          </Tooltip>
          <Tooltip label="Copy the cover letter text, to paste into an application form.">
            <Button size="xs" variant="default" leftSection={<IconCopy size={16} />} disabled={!job.letterText}
              onClick={() => void copyLetter()}>Cover letter</Button>
          </Tooltip>
          <Tooltip label="You applied (on the site or by email): move it to Done and note it in tracker.csv.">
            <Button size="xs" variant="default" color="brand" leftSection={<IconCheck size={16} />}
              disabled={job.why === 'applied by you' || isBusy}
              onClick={() => void jobAction(job.id, 'applied')}>Applied</Button>
          </Tooltip>
          <Tooltip label="Hide this job. Auto-draft will not draft it.">
            <Button size="xs" variant="default" leftSection={<IconBan size={16} />} disabled={!open || isBusy}
              onClick={() => void jobAction(job.id, 'skip')}>Skip</Button>
          </Tooltip>
        </SimpleGrid>
      </div>

      <ScrollArea className="detail" type="hover">
        <Stack p="lg" pt="md" gap="md">
          <SimpleGrid cols={{ base: 2, lg: 3 }} spacing="sm" className="facts">
            <Fact label="Salary">{job.salary}</Fact>
            <Fact label="Type">{job.job_type}</Fact>
            <Fact label="Level">{job.level}</Fact>
            <Fact label="Posted">{job.date ? `${job.date.slice(0, 10)} · ${job.ago}` : ''}</Fact>
            <Fact label="Email">{job.email}</Fact>
            <Fact label="Email found on">{job.email_src}</Fact>
            <Fact label="Source">{job.source}</Fact>
            <Fact label="Tags">{job.tags}</Fact>
            <Fact label="Note">{job.note}</Fact>
          </SimpleGrid>
          {job.link && (
            <Anchor size="sm" onClick={() => void api.openJob(job.id)} className="job-link" title={job.link}>
              <Group gap={4} wrap="nowrap">View the original post on {host(job.link)}<IconExternalLink size={14} /></Group>
            </Anchor>
          )}
          <Divider label="Job description" labelPosition="left" />
          <div className="job-text">
            {job.text ? paragraphs(job.text).map((p, i) => <p key={i}>{p}</p>)
              : <Text c="dimmed" size="sm">This job came without a description. Open the job page.</Text>}
          </div>
        </Stack>
      </ScrollArea>
    </div>
  );
}
