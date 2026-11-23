import {
  ActionIcon, Badge, Button, Divider, Group, Menu, Progress, Switch, Text, Tooltip, UnstyledButton,
  useMantineColorScheme,
} from '@mantine/core';
import {
  IconBook, IconBrandGmail, IconBug, IconChartBar, IconDownload, IconFileText, IconFolder, IconFolderOpen,
  IconHelp, IconInfoCircle, IconMoon, IconPlayerStopFilled, IconRefresh, IconRocket, IconSearch, IconSend,
  IconSettings, IconSun, IconUser, IconVolume, IconVolumeOff, IconWorld,
} from '@tabler/icons-react';
import {
  autoDraft, checkUpdate, findJobs, openAbout, openCoverage, openPlace, openReport, openSettings, setAutorun, setPrefs, stopRun, updateNow,
} from '../actions';
import { setSoundsEnabled, sound } from '../sounds';
import { busy, useApp } from '../store';
import { Logo } from './Logo';

export function Header() {
  const version = useApp((s) => s.boot?.version);
  const run = useApp((s) => s.run);
  const isBusy = useApp(busy);
  const autorun = useApp((s) => s.autorun);
  const prefs = useApp((s) => s.prefs);
  const update = useApp((s) => s.update);
  const coverage = useApp((s) => s.boot?.coverage);
  const { colorScheme, setColorScheme } = useMantineColorScheme();
  const dark = colorScheme !== 'light';

  return (
    <Group className="header" justify="space-between" wrap="nowrap" px="md" gap="md">
      <Group gap="sm" wrap="nowrap">
        <Logo />
        <div>
          <Text fw={700} lh={1.1}>Job Hunter</Text>
          <Text size="xs" c="dimmed" lh={1.1}>{version}</Text>
        </div>
        <Divider orientation="vertical" mx="xs" />
        <Tooltip label="Search every job site with your filter (F5). Uses no Gmail, and Gemini only for the Google search. Takes about a minute.">
          <Button leftSection={<IconSearch size={18} />} onClick={() => void findJobs()}
            loading={run?.what.startsWith('Searching')} disabled={isBusy && !run?.what.startsWith('Searching')}>
            Find jobs
          </Button>
        </Tooltip>
        <Tooltip label="Find jobs, then let Gemini check the best matches and write a tailored CV + email for each. Saved as Gmail drafts (or as files without Gmail). Nothing is sent.">
          <Button variant="light" leftSection={<IconSend size={18} />} onClick={() => void autoDraft()}
            disabled={isBusy}>
            Auto-draft best matches
          </Button>
        </Tooltip>
        {isBusy && (
          <Tooltip label="Stop the run in progress, from this window or from Auto-run.">
            <Button color="red" variant="light" leftSection={<IconPlayerStopFilled size={16} />}
              onClick={() => void stopRun()}>Stop</Button>
          </Tooltip>
        )}
      </Group>

      {coverage && (
        <Tooltip label="Every search reads all of these at once. Click to see the full list.">
          <UnstyledButton className="coverage-pill" onClick={openCoverage}>
            <IconWorld size={16} />
            <span><b>{coverage.sites}</b> job sites</span>
            <span className="coverage-plus">+</span>
            <span><b>{coverage.companies.length}</b> company career pages</span>
          </UnstyledButton>
        </Tooltip>
      )}

      <Group gap="xs" wrap="nowrap">
        {update && (
          <Tooltip label={`You have ${version}. One click downloads ${update.latest}, installs it and reopens Job Hunter. Your keys, profile and CVs are kept.`}>
            <Button color="brand" variant="filled" leftSection={<IconDownload size={16} />}
              onClick={() => void updateNow()} loading={update.installing}
              disabled={update.downloading !== null && !update.installing}>
              {update.downloading !== null && !update.installing
                ? `Downloading ${update.downloading}%` : `Update to ${update.latest}`}
            </Button>
          </Tooltip>
        )}
        {update?.downloading != null && !update.installing &&
          <Progress value={update.downloading} w={80} size="sm" animated />}
        <Tooltip label="Run Auto-draft every 30 minutes in the background while you are signed in to Windows, even with this window closed.">
          <Group gap={6} wrap="nowrap" className="autorun">
            <Switch checked={autorun === 'on'} onChange={(e) => void setAutorun(e.currentTarget.checked)}
              size="sm" label="Auto-run" labelPosition="left" />
            {autorun === 'on' && <Badge size="xs" variant="dot">every 30 min</Badge>}
          </Group>
        </Tooltip>
        <Divider orientation="vertical" />
        <Menu shadow="lg" width={250} position="bottom-end">
          <Menu.Target>
            <Button variant="subtle" color="gray" leftSection={<IconFolderOpen size={18} />}>Open</Button>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Item leftSection={<IconBrandGmail size={16} />} onClick={() => void openPlace('gmail')}>
              Gmail drafts</Menu.Item>
            <Menu.Item leftSection={<IconFileText size={16} />} onClick={() => void openPlace('cvs')}>
              My CVs and cover letters</Menu.Item>
            <Menu.Item leftSection={<IconChartBar size={16} />} onClick={() => void openPlace('tracker')}>
              Tracker (every job handled)</Menu.Item>
            <Menu.Item leftSection={<IconBook size={16} />} onClick={() => void openPlace('runs')}>Run log</Menu.Item>
            <Menu.Item leftSection={<IconUser size={16} />} onClick={() => void openPlace('profile')}>
              My profile (profile.json)</Menu.Item>
            <Menu.Divider />
            <Menu.Item leftSection={<IconFolder size={16} />} onClick={() => void openPlace('data')}>
              Job Hunter data folder</Menu.Item>
          </Menu.Dropdown>
        </Menu>
        <Menu shadow="lg" width={230} position="bottom-end">
          <Menu.Target>
            <Button variant="subtle" color="gray" leftSection={<IconHelp size={18} />}>Help</Button>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Item leftSection={<IconRocket size={16} />}
              onClick={() => useApp.getState().set({ selected: null })}>Getting started</Menu.Item>
            <Menu.Item leftSection={<IconWorld size={16} />} onClick={() => void openPlace('guide')}>
              User guide</Menu.Item>
            <Menu.Item leftSection={<IconBug size={16} />} onClick={openReport}>Report a problem</Menu.Item>
            <Menu.Divider />
            <Menu.Item leftSection={<IconRefresh size={16} />} onClick={() => void checkUpdate(false)}>
              Check for updates</Menu.Item>
            <Menu.Item leftSection={<IconDownload size={16} />} onClick={() => void openPlace('download')}>
              Download page</Menu.Item>
            <Menu.Item leftSection={<IconInfoCircle size={16} />} onClick={openAbout}>About Job Hunter</Menu.Item>
          </Menu.Dropdown>
        </Menu>
        <Tooltip label={prefs.sounds ? 'Sounds on' : 'Sounds off'}>
          <ActionIcon variant="subtle" color="gray" size="lg" aria-label="Sounds"
            onClick={() => {
              const on = !prefs.sounds;
              setSoundsEnabled(on);
              if (on) sound.tap();
              void setPrefs({ sounds: on });
            }}>
            {prefs.sounds ? <IconVolume size={19} /> : <IconVolumeOff size={19} />}
          </ActionIcon>
        </Tooltip>
        <Tooltip label={dark ? 'Light theme' : 'Dark theme'}>
          <ActionIcon variant="subtle" color="gray" size="lg" aria-label="Theme"
            onClick={() => {
              const next = dark ? 'light' : 'dark';
              setColorScheme(next);
              void setPrefs({ theme: next });
            }}>
            {dark ? <IconSun size={19} /> : <IconMoon size={19} />}
          </ActionIcon>
        </Tooltip>
        <Tooltip label="Settings: limits, and your Gmail & Gemini keys">
          <ActionIcon variant="subtle" color="gray" size="lg" aria-label="Settings" onClick={openSettings}>
            <IconSettings size={19} />
          </ActionIcon>
        </Tooltip>
      </Group>
    </Group>
  );
}
