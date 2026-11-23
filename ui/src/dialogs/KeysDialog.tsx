import { useEffect, useState } from 'react';
import {
  Alert, Anchor, Button, Group, List, Loader, PasswordInput, Stack, Text, TextInput, ThemeIcon,
} from '@mantine/core';
import { modals } from '@mantine/modals';
import { IconCheck, IconExternalLink, IconInfoCircle, IconX } from '@tabler/icons-react';
import { api } from '../api';
import { guard, toastError, toastOk } from '../actions';
import { useApp } from '../store';
import type { KeyField } from '../types';

/** The Gemini key and the optional Gmail app password, each with step-by-step help. Tested before saving. */
export function KeysDialog({ intro }: { intro?: string }) {
  const [fields, setFields] = useState<KeyField[] | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string | null>>({});
  const [busy, setBusy] = useState(false);
  const [passed, setPassed] = useState(false);

  useEffect(() => {
    void guard(() => api.keys()).then((res) => {
      if (!res) return;
      setFields(res.fields);
      setValues(Object.fromEntries(res.fields.map((f) => [f.key, f.value])));
    });
  }, []);

  if (!fields) return <Group justify="center" py="xl"><Loader /></Group>;

  const change = (key: string, value: string) => {
    setValues((v) => ({ ...v, [key]: value }));
    setErrors((e) => ({ ...e, [key]: null }));
    setPassed(false);
  };

  const testAndSave = async () => {
    setBusy(true);
    const res = await guard(() => api.testKeys(values));
    if (!res) return setBusy(false);
    if (res.error) {
      setBusy(false);
      return toastError(res.error, 'Check your keys');
    }
    const errs = res.errors ?? {};
    setErrors(errs);
    if (Object.values(errs).some(Boolean)) {
      setBusy(false);
      return toastError('One of the keys was not accepted. The reason is under it.', 'Not saved yet');
    }
    setPassed(true);
    const saved = await guard(() => api.saveKeys(values));
    setBusy(false);
    if (!saved) return;
    useApp.getState().set({ setup: saved.setup, models: saved.models });
    toastOk('Accounts connected', values.gmail_address ? 'Gemini and Gmail both work.' : 'Gemini works.');
    modals.closeAll();
  };

  return (
    <Stack gap="lg">
      {intro && <Alert variant="light" color="brand" icon={<IconInfoCircle />}>{intro}</Alert>}
      {fields.map((f) => (
        <Stack key={f.key} gap={6}>
          {f.secret ? (
            <PasswordInput label={f.label} value={values[f.key] ?? ''} error={errors[f.key]}
              onChange={(e) => change(f.key, e.currentTarget.value)} autoComplete="off" spellCheck={false}
              data-autofocus={f.key === 'gemini_api_key' || undefined} />
          ) : (
            <TextInput label={f.label} value={values[f.key] ?? ''} error={errors[f.key]} placeholder="you@gmail.com"
              onChange={(e) => change(f.key, e.currentTarget.value)} autoComplete="off" spellCheck={false} />
          )}
          {f.steps.length > 0 && (
            <List size="xs" c="dimmed" type="ordered" spacing={2} withPadding>
              {f.steps.map((s) => <List.Item key={s}>{s}</List.Item>)}
            </List>
          )}
          {f.links.length > 0 && (
            <Group gap="md">
              {f.links.map((l) => (
                <Anchor key={l.url} size="xs" onClick={() => void api.openUrl(l.url)}>
                  <Group gap={4} wrap="nowrap">{l.label}<IconExternalLink size={12} /></Group>
                </Anchor>
              ))}
            </Group>
          )}
        </Stack>
      ))}
      <Text size="xs" c="dimmed">Saved only on this PC, in config.json. Job Hunter sends the Gemini key only to Google
        and the Gmail password only to Gmail.</Text>
      <Group justify="space-between">
        <Group gap={6}>
          {busy && <><Loader size="xs" /><Text size="sm" c="dimmed">Testing with Google...</Text></>}
          {passed && !busy && <><ThemeIcon size="sm" radius="xl"><IconCheck size={14} /></ThemeIcon>
            <Text size="sm">Both work</Text></>}
          {!busy && Object.values(errors).some(Boolean) &&
            <><ThemeIcon size="sm" radius="xl" color="red"><IconX size={14} /></ThemeIcon>
              <Text size="sm" c="red">Not accepted</Text></>}
        </Group>
        <Group>
          <Button variant="default" onClick={() => modals.closeAll()}>Cancel</Button>
          <Button onClick={() => void testAndSave()} loading={busy}>Test and save</Button>
        </Group>
      </Group>
    </Stack>
  );
}
