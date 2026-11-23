import {
  ActionIcon, Avatar, Badge, Button, Chip, Group, MultiSelect, NumberInput, Paper, ScrollArea, Select, Stack,
  Switch, TagsInput, Text, Tooltip,
} from '@mantine/core';
import {
  IconCircleCheckFilled, IconCircleXFilled, IconDeviceFloppy, IconFileUpload, IconRefresh, IconSparkles,
  IconUser, IconWand,
} from '@tabler/icons-react';
import { api } from '../api';
import { checkModels, guard, openPlace, openTailor, saveFilter, setModel, uploadCv } from '../actions';
import { busy, useApp } from '../store';
import type { FilterState } from '../types';

const split = (s: string) => s.split(',').map((w) => w.trim()).filter(Boolean);
const join = (w: string[]) => w.join(', ');

const MODE_TIPS: Record<string, string> = {
  remote: 'Work from home, for a company anywhere.',
  hybrid: 'Some days in the office: the office must be in your country (or offer a visa).',
  onsite: 'Every day in the office: the office must be in your country (or offer a visa).',
};

function Section({ title, right, children }: { title: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <Paper className="card" p="md">
      <Group justify="space-between" mb="sm" wrap="nowrap">
        <Text className="section-title">{title}</Text>
        {right}
      </Group>
      {children}
    </Paper>
  );
}

function CvCard() {
  const profile = useApp((s) => s.profile);
  const isBusy = useApp(busy);
  return (
    <Section title="Your CV">
      {profile ? (
        <Group gap="sm" wrap="nowrap" mb="sm">
          <Avatar color="brand" radius="xl">{profile.name.split(' ').map((p) => p[0]).slice(0, 2).join('')}</Avatar>
          <div style={{ minWidth: 0 }}>
            <Text fw={600} truncate>{profile.name}</Text>
            <Text size="xs" c="dimmed" truncate>{profile.title} · {profile.roles} roles</Text>
          </div>
        </Group>
      ) : (
        <Text size="sm" c="dimmed" mb="sm">No CV yet. Gemini reads it once and builds your profile; every tailored
          CV uses only facts from it.</Text>
      )}
      <Group gap="xs" grow>
        <Tooltip label="Gemini reads your CV (PDF, Word, text or a photo) once and builds your profile.">
          <Button size="xs" variant={profile ? 'default' : 'filled'} leftSection={<IconFileUpload size={15} />}
            onClick={() => void uploadCv()} disabled={isBusy}>{profile ? 'Replace CV' : 'Upload my CV'}</Button>
        </Tooltip>
        <Tooltip label="Paste any job post (LinkedIn, a company site...) and get a tailored CV + cover letter for it.">
          <Button size="xs" variant="default" leftSection={<IconWand size={15} />} onClick={openTailor}
            disabled={isBusy}>Tailor CV</Button>
        </Tooltip>
      </Group>
      {profile && (
        <Button size="compact-xs" variant="subtle" color="gray" mt={6} leftSection={<IconUser size={13} />}
          onClick={() => void openPlace('profile')}>Check or correct my profile</Button>
      )}
    </Section>
  );
}

function ModelCard() {
  const models = useApp((s) => s.models);
  const isBusy = useApp(busy);
  if (!models) return null;
  const data = [{ value: '', label: 'Auto (best free model)' },
    ...models.options.map((o) => ({ value: o.value, label: o.value }))];
  const status = Object.fromEntries(models.options.map((o) => [o.value, o]));
  return (
    <Section title="AI model" right={
      <Tooltip label="Ask Google which models your key can use right now (also done once a day).">
        <ActionIcon variant="subtle" color="gray" onClick={() => void checkModels()} disabled={isBusy}
          aria-label="Check models"><IconRefresh size={16} /></ActionIcon>
      </Tooltip>}>
      <Select data={data} value={models.selected} allowDeselect={false} leftSection={<IconSparkles size={16} />}
        onChange={(v) => v !== null && void setModel(v)} comboboxProps={{ shadow: 'lg' }}
        renderOption={({ option }) => {
          const s = status[option.value];
          return (
            <Group gap={8} wrap="nowrap" w="100%">
              {s ? (s.ok ? <IconCircleCheckFilled size={15} color="var(--mantine-color-brand-6)" />
                : <IconCircleXFilled size={15} color="var(--mantine-color-red-6)" />) : <IconSparkles size={15} />}
              <div style={{ minWidth: 0 }}>
                <Text size="sm">{option.label}</Text>
                {s?.status && <Text size="xs" c="dimmed">{s.status}</Text>}
              </div>
            </Group>
          );
        }} />
      <Text size="xs" mt={6} c={models.tone === 'error' ? 'red' : 'dimmed'}>{models.note}</Text>
    </Section>
  );
}

function FilterCard() {
  const boot = useApp((s) => s.boot);
  const f = useApp((s) => s.filter);
  const error = useApp((s) => s.filterError);
  const isBusy = useApp(busy);
  const setFilter = useApp((s) => s.setFilter);
  if (!boot || !f) return null;
  const err = (field: string) => (error?.field === field ? error.message : undefined);

  const pickTypes = async (names: string[]) => {
    setFilter({ jobTypes: names });
    const res = await guard(() => api.jobTypes(names));
    if (!res) return;
    const patch: Partial<FilterState> = { presetKeywords: res.presetKeywords };
    if (res.keywords !== null) patch.keywords = res.keywords;
    if (res.titleOnly !== null) patch.titleOnly = res.titleOnly;
    setFilter(patch);
  };

  const setKeywords = (list: string[]) => {
    const keywords = join(list);
    // Your own keywords replace the job types (the bot does the same when it saves).
    setFilter(keywords.toLowerCase() === f.presetKeywords.toLowerCase() ? { keywords }
      : { keywords, jobTypes: [], presetKeywords: '' });
  };

  return (
    <Section title="What to look for" right={
      f.jobTypes.length ? <Badge variant="light" size="sm">{f.jobTypes.length} job type{f.jobTypes.length > 1 ? 's' : ''}</Badge>
        : <Badge variant="light" color="gray" size="sm">Custom</Badge>}>
      <Stack gap="sm">
        <MultiSelect label="Job type" data={boot.presets} value={f.jobTypes} onChange={(v) => void pickTypes(v)}
          placeholder={f.jobTypes.length ? '' : 'Pick one or more fields'} searchable clearable
          description="Fills in the usual job titles. Type your own keywords below for anything else."
          comboboxProps={{ shadow: 'lg' }} />
        <TagsInput label="Keywords (any of)" value={split(f.keywords)} onChange={setKeywords} error={err('keywords')}
          description="A job is kept if any keyword matches. Press Enter or comma after each." clearable
          splitChars={[',']} acceptValueOnBlur />
        <Tooltip label="Broad words like Sales or Finance appear in almost every job ad: this keeps only jobs with a keyword in the title.">
          <Switch label="Keywords in the job title only" checked={f.titleOnly}
            onChange={(e) => setFilter({ titleOnly: e.currentTarget.checked })} />
        </Tooltip>
        <TagsInput label="Exclude in title" value={split(f.exclude)} onChange={(v) => setFilter({ exclude: join(v) })}
          placeholder="e.g. Senior, Intern, PHP" splitChars={[',']} acceptValueOnBlur clearable />

        <div>
          <Text size="sm" fw={500} mb={6}>Work type</Text>
          <Chip.Group multiple value={f.modes} onChange={(v) => setFilter({ modes: v })}>
            <Group gap={6}>
              {boot.workModes.map((m) => (
                <Tooltip key={m.value} label={MODE_TIPS[m.value] ?? m.label}>
                  <div><Chip value={m.value} size="sm" variant="light">{m.label}</Chip></div>
                </Tooltip>
              ))}
            </Group>
          </Chip.Group>
          {err('modes') && <Text size="xs" c="red" mt={4}>{err('modes')}</Text>}
        </div>

        <Select label="Open to" data={boot.openTo} value={f.openTo} allowDeselect={false}
          onChange={(v) => v && setFilter({ openTo: v })} comboboxProps={{ shadow: 'lg' }}
          description={{
            me: 'Remote jobs that hire worldwide or name your country; office jobs in your country.',
            countries: 'The same, for the countries you list below.',
            anywhere: 'No limit, including remote jobs for one country only.',
          }[f.openTo]} />
        {f.openTo !== 'anywhere' && (
          <TagsInput label="My country / region" value={split(f.region)} error={err('region')}
            onChange={(v) => setFilter({ region: join(v) })} placeholder="e.g. Pakistan, South Asia"
            splitChars={[',']} acceptValueOnBlur />
        )}
        {f.openTo === 'countries' && (
          <TagsInput label="Countries I would work for" value={split(f.countries)} error={err('countries')}
            onChange={(v) => setFilter({ countries: join(v) })} placeholder="e.g. UAE, Germany, Europe"
            splitChars={[',']} acceptValueOnBlur />
        )}
        <Switch label="Visa / relocation abroad" checked={f.visa}
          description="Keep office jobs abroad that offer visa sponsorship or relocation."
          onChange={(e) => setFilter({ visa: e.currentTarget.checked })} />

        <Group grow align="flex-start">
          <NumberInput label="Max age (days)" min={1} max={60} value={f.maxAge} error={err('maxAge')}
            onChange={(v) => setFilter({ maxAge: Number(v) || 1 })} allowDecimal={false} />
          <Tooltip label="Gemini searches Google for posts on LinkedIn, Indeed, Glassdoor and company sites. Google allows this only for keys with billing on; on a free key Job Hunter says so once and tries again the next day.">
            <Switch label="Search Google too" checked={f.google} mt={30}
              onChange={(e) => setFilter({ google: e.currentTarget.checked })} />
          </Tooltip>
        </Group>

        <Tooltip label="Save this filter (Auto-run uses it too) and search now.">
          <Button fullWidth leftSection={<IconDeviceFloppy size={17} />} onClick={() => void saveFilter()}
            disabled={isBusy}>Save & search</Button>
        </Tooltip>
      </Stack>
    </Section>
  );
}

export function Sidebar() {
  return (
    <ScrollArea className="sidebar" type="hover" scrollbarSize={8}>
      <Stack gap="sm" p="sm">
        <CvCard />
        <ModelCard />
        <FilterCard />
      </Stack>
    </ScrollArea>
  );
}
