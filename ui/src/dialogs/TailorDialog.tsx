import { useState } from 'react';
import { Button, Group, SimpleGrid, Stack, Text, TextInput, Textarea } from '@mantine/core';
import { modals } from '@mantine/modals';
import { submitTailor } from '../actions';

/** A job from anywhere (LinkedIn, a company site, a friend): paste it, get a tailored CV + cover letter. */
export function TailorDialog() {
  const [job, setJob] = useState({ company: '', title: '', url: '', text: '' });
  const [sending, setSending] = useState(false);
  const set = (k: keyof typeof job) => (e: { currentTarget: { value: string } }) =>
    setJob((j) => ({ ...j, [k]: e.currentTarget.value }));
  const short = job.text.trim().length < 100;

  const go = async () => {
    setSending(true);
    const ok = await submitTailor(job);
    setSending(false);
    if (ok) modals.closeAll();
  };

  return (
    <Stack gap="sm">
      <Text size="sm" c="dimmed">For a job Job Hunter did not find. Gemini writes a CV and cover letter from your
        profile, using only facts from your own CV. The PDFs open when they are ready.</Text>
      <SimpleGrid cols={2}>
        <TextInput label="Company" required value={job.company} onChange={set('company')} data-autofocus />
        <TextInput label="Job title" required value={job.title} onChange={set('title')} />
      </SimpleGrid>
      <TextInput label="Link to the job (optional)" value={job.url} onChange={set('url')} placeholder="https://" />
      <Textarea label="Full job description" required autosize minRows={10} maxRows={18} value={job.text}
        onChange={set('text')} placeholder="Paste the whole ad: responsibilities, requirements, about the company."
        description={short && job.text ? `${100 - job.text.trim().length} more characters, please` : undefined} />
      <Group justify="flex-end">
        <Button variant="default" onClick={() => modals.closeAll()}>Cancel</Button>
        <Button onClick={() => void go()} loading={sending}
          disabled={!job.company.trim() || !job.title.trim() || short}>Make CV + cover letter</Button>
      </Group>
    </Stack>
  );
}
