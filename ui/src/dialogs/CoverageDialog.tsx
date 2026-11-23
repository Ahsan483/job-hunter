import { useState } from 'react';
import { Badge, Group, Paper, ScrollArea, SimpleGrid, Stack, Text, TextInput, ThemeIcon } from '@mantine/core';
import { IconBriefcase, IconBuildingSkyscraper, IconSearch, IconWorld } from '@tabler/icons-react';
import { useApp } from '../store';

/** Every job site and company career page one search reads (bot.coverage). */
export function CoverageDialog() {
  const coverage = useApp((s) => s.boot?.coverage);
  const [query, setQuery] = useState('');
  if (!coverage) return null;
  const q = query.trim().toLowerCase();
  const companies = q ? coverage.companies.filter((c) => c.toLowerCase().includes(q)) : coverage.companies;

  return (
    <Stack gap="lg">
      <SimpleGrid cols={3} spacing="sm">
        <Stat icon={<IconWorld size={18} />} value={coverage.sites} label="job sites" />
        <Stat icon={<IconBuildingSkyscraper size={18} />} value={coverage.companies.length} label="company career pages" />
        <Stat icon={<IconBriefcase size={18} />} value="17,000+" label="open jobs checked each search" />
      </SimpleGrid>
      <Text size="sm" c="dimmed">
        Every search reads all of these at once and shows matches as each one answers. Company career pages are where
        sites like Wellfound and HiringCafe get most of their jobs; Job Hunter reads them at the source, so you see
        each job early and apply on the company's own page. With <b>Search Google too</b> on, Gemini also finds posts
        on LinkedIn, Indeed, Glassdoor, Wellfound and HiringCafe.
      </Text>

      {coverage.groups.map((g) => (
        <div key={g.name}>
          <Text fw={600} size="sm" mb={6}>{g.name}</Text>
          <Group gap={6}>
            {g.sites.map((s) => <Badge key={s} variant="light" color="gray" size="lg">{s}</Badge>)}
          </Group>
        </div>
      ))}

      <div>
        <Group justify="space-between" mb={6} wrap="nowrap">
          <Text fw={600} size="sm">Company career pages ({coverage.companies.length})</Text>
          <TextInput size="xs" w={200} placeholder="Find a company" leftSection={<IconSearch size={14} />}
            value={query} onChange={(e) => setQuery(e.currentTarget.value)} aria-label="Find a company" />
        </Group>
        <ScrollArea.Autosize mah={220} type="auto">
          <Group gap={6}>
            {companies.map((c) => <Badge key={c} variant="outline" color="gray" size="md">{c}</Badge>)}
            {!companies.length && <Text size="sm" c="dimmed">Not on the list yet. Its jobs may still turn up through
              the job sites above.</Text>}
          </Group>
        </ScrollArea.Autosize>
      </div>
    </Stack>
  );
}

function Stat({ icon, value, label }: { icon: React.ReactNode; value: number | string; label: string }) {
  return (
    <Paper withBorder p="sm" radius="md">
      <Group gap="sm" wrap="nowrap">
        <ThemeIcon variant="light" size={36} radius="md">{icon}</ThemeIcon>
        <div style={{ minWidth: 0 }}>
          <Text fw={700} size="xl" lh={1.1}>{typeof value === 'number' ? value.toLocaleString() : value}</Text>
          <Text size="xs" c="dimmed" lh={1.3}>{label}</Text>
        </div>
      </Group>
    </Paper>
  );
}
