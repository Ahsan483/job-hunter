import { Button, Code, Group, Stack, Text } from '@mantine/core';
import { checkUpdate, openPlace, openReport } from '../actions';
import { useApp } from '../store';
import { Logo } from '../components/Logo';

export function AboutDialog() {
  const boot = useApp((s) => s.boot);
  if (!boot) return null;
  return (
    <Stack gap="lg" align="center" ta="center" py="xs">
      <Logo size={64} />
      <div>
        <Text fw={600} size="lg">Job Hunter {boot.version}</Text>
        <Text size="sm" c="dimmed" mt={4}>Finds remote and local jobs on 15 sites, and writes a tailored CV and
          cover letter for each with Gemini.</Text>
      </div>
      <Stack gap={4} w="100%">
        <Text size="xs" c="dimmed">Your files are in</Text>
        <Code block style={{ textAlign: 'left' }}>{boot.dataFolder}</Code>
      </Stack>
      <Group gap="sm">
        <Button variant="default" onClick={() => void openPlace('data')}>Open data folder</Button>
        <Button variant="default" onClick={() => void checkUpdate(false)}>Check for updates</Button>
        <Button variant="default" onClick={openReport}>Report a problem</Button>
      </Group>
      <Text size="xs" c="dimmed">© Code Projects Official · codeprojectsofficial.com</Text>
    </Stack>
  );
}
