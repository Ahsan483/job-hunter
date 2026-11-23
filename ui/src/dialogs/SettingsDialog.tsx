import { useEffect, useState } from 'react';
import { Button, Group, Loader, NumberInput, Stack, Switch, Text } from '@mantine/core';
import { modals } from '@mantine/modals';
import { IconKey } from '@tabler/icons-react';
import { api } from '../api';
import { guard, openKeys, toastError, toastOk } from '../actions';
import { useApp } from '../store';
import type { SettingField } from '../types';

/** The limits from config.json, one per row, each checked against its allowed range. */
export function SettingsDialog() {
  const [fields, setFields] = useState<SettingField[] | null>(null);
  const [values, setValues] = useState<Record<string, number | string>>({});
  const [error, setError] = useState<{ field?: string; message: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const boot = useApp((s) => s.boot);
  const [usage, setUsage] = useState(boot?.usageStats ?? true);

  useEffect(() => {
    void guard(() => api.settings()).then((res) => {
      if (!res) return;
      setFields(res);
      setValues(Object.fromEntries(res.map((f) => [f.key, f.value])));
    });
  }, []);

  if (!fields) return <Group justify="center" py="xl"><Loader size="sm" /></Group>;

  const save = async () => {
    setSaving(true);
    const res = await guard(() => api.saveSettings(values));
    if (res?.ok && boot && usage !== boot.usageStats) {
      await guard(() => api.setUsageStats(usage));
      useApp.getState().set({ boot: { ...boot, usageStats: usage } });
    }
    setSaving(false);
    if (!res) return;
    if (res.error) {
      setError({ field: res.field, message: res.error });
      return toastError(res.error, 'Not saved');
    }
    toastOk('Settings saved', 'The next run uses them.');
    modals.closeAll();
  };

  return (
    <Stack gap={0}>
      {fields.map((f) => (
        <div key={f.key} className="setting-row">
          <div>
            <Text size="sm" fw={500}>{f.label}</Text>
            <Text size="xs" c="dimmed" mt={2}>{f.note}</Text>
            {error?.field === f.key && <Text size="xs" c="red" mt={4}>{error.message}</Text>}
          </div>
          <NumberInput aria-label={f.label} min={f.min} max={f.max} allowDecimal={false} clampBehavior="none"
            value={values[f.key]} error={error?.field === f.key} rightSectionWidth={28}
            onChange={(v) => { setValues((s) => ({ ...s, [f.key]: v })); setError(null); }}
            description={undefined} />
        </div>
      ))}
      <div className="setting-row">
        <div>
          <Text size="sm" fw={500}>Count me as an active user</Text>
          <Text size="xs" c="dimmed" mt={2}>Once a day Job Hunter sends an anonymous "in use" signal: a random
            number and the version. Never your name, email, keys, jobs or CV.</Text>
        </div>
        <Group justify="flex-end"><Switch checked={usage} onChange={(e) => setUsage(e.currentTarget.checked)}
          aria-label="Count me as an active user" /></Group>
      </div>
      <Group justify="space-between" mt="lg">
        <Button variant="subtle" leftSection={<IconKey size={16} />}
          onClick={() => { modals.closeAll(); openKeys(); }}>Gmail & Gemini keys</Button>
        <Group gap="sm">
          <Button variant="default" onClick={() => modals.closeAll()}>Cancel</Button>
          <Button onClick={() => void save()} loading={saving}>Save</Button>
        </Group>
      </Group>
    </Stack>
  );
}
