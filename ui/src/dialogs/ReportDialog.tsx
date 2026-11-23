import { useState } from 'react';
import { Alert, Button, Checkbox, Group, Stack, Text, TextInput, Textarea } from '@mantine/core';
import { modals } from '@mantine/modals';
import { IconInfoCircle } from '@tabler/icons-react';
import { api } from '../api';
import { guard, toastError, toastOk } from '../actions';
import { useApp } from '../store';
import type { LoggedEntry } from '../types';

// Reports go to the Code Projects inbox through Web3Forms, the same service as the website's contact form.
// The access key only lets someone send a message to that inbox, so it is fine for it to be public.
const WEB3FORMS = 'https://api.web3forms.com/submit';
const ACCESS_KEY = 'e7126761-d75c-4aae-9da6-d4538a083607';

function line(e: LoggedEntry): string {
  switch (e.type) {
    case 'run': return `> ${e.what} (${e.at})`;
    case 'job': return `${e.status} ${e.company} | ${e.role}${e.reason ? ` | ${e.reason}` : ''}`;
    case 'source': return `${e.name}: ${e.state === 'ok' ? `${e.count} jobs` : `${e.state} (${e.note ?? ''})`}`;
    case 'filter': return `left out: ${JSON.stringify(e.counts)}`;
    case 'summary': return `summary: fetched ${e.fetched}, candidates ${e.candidates}, drafts ${e.drafts} ${e.notes.join('; ')}`;
    case 'text': return e.text;
  }
}

/** Tell the developer what went wrong, without leaving the app. Nothing private is sent: no keys, no CV. */
export function ReportDialog() {
  const [message, setMessage] = useState('');
  const [email, setEmail] = useState('');
  const [details, setDetails] = useState(true);
  const [sending, setSending] = useState(false);
  const boot = useApp((s) => s.boot);

  const send = async () => {
    setSending(true);
    try {
      const diag = details ? await guard(() => api.diagnostics()) : undefined;
      const recent = details ? useApp.getState().log.slice(-60).map(line).join('\n') : '';
      const res = await fetch(WEB3FORMS, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({
          access_key: ACCESS_KEY,
          subject: `Job Hunter ${boot?.version ?? ''} problem report`,
          from_name: 'Job Hunter app',
          replyto: email.trim() || undefined,
          email: email.trim() || 'not given',
          message: message.trim(),
          ...(diag ? { version: diag.version, windows: diag.windows, installed: diag.installed ? 'yes' : 'from source',
            run_log: diag.runs } : {}),
          ...(recent ? { activity: recent } : {}),
        }),
      });
      const answer = await res.json().catch(() => ({}));
      if (!res.ok || answer.success === false) throw new Error(answer.message || `error ${res.status}`);
      toastOk('Report sent', 'Thank you. It goes straight to the developer' + (email.trim() ? ', who can reply by email.' : '.'));
      modals.closeAll();
    } catch (e) {
      toastError(`The report could not be sent (${e instanceof Error ? e.message : String(e)}). Check your internet ` +
        'connection and try again.', 'Not sent');
    } finally {
      setSending(false);
    }
  };

  const short = message.trim().length < 10;
  return (
    <Stack gap="md">
      <Text size="sm" c="dimmed">Describe what happened and what you expected. The report goes straight to the
        developer.</Text>
      <Textarea label="What went wrong?" required autosize minRows={5} maxRows={12} value={message} data-autofocus
        onChange={(e) => setMessage(e.currentTarget.value)}
        placeholder="For example: I pressed CV + cover letter for a job and got an error about the PDF." />
      <TextInput label="Your email (optional)" description="Only if you would like a reply." value={email}
        onChange={(e) => setEmail(e.currentTarget.value)} placeholder="you@example.com" />
      <Checkbox checked={details} onChange={(e) => setDetails(e.currentTarget.checked)}
        label="Include technical details"
        description="Job Hunter version, Windows version and the recent activity. Never your keys, passwords or CV." />
      <Alert variant="light" color="gray" icon={<IconInfoCircle size={16} />} p="xs">
        <Text size="xs">Sent over a secure connection. Nothing is sent until you press Send report.</Text>
      </Alert>
      <Group justify="flex-end" gap="sm">
        <Button variant="default" onClick={() => modals.closeAll()}>Cancel</Button>
        <Button onClick={() => void send()} loading={sending} disabled={short}>Send report</Button>
      </Group>
    </Stack>
  );
}
