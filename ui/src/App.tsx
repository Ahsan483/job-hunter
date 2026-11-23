import { useEffect, useRef } from 'react';
import { Button, Center, Loader, Stack, Text, useMantineColorScheme } from '@mantine/core';
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels';
import { api, onServerEvent } from './api';
import { checkUpdate, findJobs, guard, loadJobs, onRun, onUpdate, openKeys } from './actions';
import { setSoundsEnabled } from './sounds';
import { useApp } from './store';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { JobList } from './components/JobList';
import { JobDetail } from './components/JobDetail';
import { ActivityLog } from './components/ActivityLog';
import { Logo } from './components/Logo';

function useBootstrap() {
  // setColorScheme is a new function on every render: keep the latest in a ref so the effect runs once.
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useRef(setColorScheme);
  scheme.current = setColorScheme;
  useEffect(() => {
    let alive = true;
    const off = onServerEvent((e) => {
      const s = useApp.getState();
      switch (e.kind) {
        case 'log': s.addLog(e.data); break;
        case 'run': onRun(e); break;
        case 'jobs-changed': if (!s.run) void loadJobs(); break;
        case 'models': s.set({ models: e.data }); break;
        case 'external-run':
          s.set({ external: e.data });
          if (!e.data) void loadJobs();
          break;
        case 'update': onUpdate(e); break;
      }
    });

    void api.bootstrap().then((boot) => {
      if (!alive) return;
      setSoundsEnabled(boot.prefs.sounds);
      scheme.current(boot.prefs.theme);
      useApp.getState().set({
        boot, filter: boot.filter, profile: boot.profile, setup: boot.setup, models: boot.models,
        autorun: boot.autorun, prefs: boot.prefs, external: boot.running,
      });
      void loadJobs();
      if (!boot.setup.find((s) => s.id === 'gemini')?.done) {
        setTimeout(() => openKeys('Welcome to Job Hunter. Connect Gemini first: it is free, needs no card and ' +
          'takes about a minute. It writes every tailored CV.'), 600);
      }
      setTimeout(() => void checkUpdate(true), 4000);
    }).catch((e: unknown) => {
      useApp.getState().set({ bootError: e instanceof Error ? e.message : String(e) });
    });
    return () => { alive = false; off(); };
  }, []);
}

function useShortcuts() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement).closest('input, textarea, select, [contenteditable="true"]');
      const dialog = document.querySelector('.mantine-Modal-content');
      if (e.key === 'F5') {
        e.preventDefault(); // never reload the page
        if (!dialog) void findJobs();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        document.getElementById('job-search')?.focus();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'r') {
        e.preventDefault();
      } else if (e.key === 'Enter' && !typing && !dialog) {
        const id = useApp.getState().selected;
        if (id) void guard(() => api.openJob(id));
      } else if (e.key === 'Escape' && !typing && !dialog) {
        useApp.getState().set({ selected: null });
      }
    };
    window.addEventListener('keydown', onKey);
    // No browser right-click menu (Reload, Inspect) outside text fields.
    const onMenu = (e: MouseEvent) => {
      if (!(e.target as HTMLElement).closest('input, textarea, .job-text') && !import.meta.env.DEV) e.preventDefault();
    };
    window.addEventListener('contextmenu', onMenu);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('contextmenu', onMenu);
    };
  }, []);
}

export default function App() {
  useBootstrap();
  useShortcuts();
  const boot = useApp((s) => s.boot);
  const bootError = useApp((s) => s.bootError);

  if (!boot) {
    return (
      <Center h="100vh">
        <Stack align="center" gap="md">
          <Logo size={64} />
          {bootError ? (
            <>
              <Text fw={600}>Job Hunter could not start</Text>
              <Text size="sm" c="dimmed" maw={420} ta="center">{bootError}</Text>
              <Button variant="default" onClick={() => location.reload()}>Try again</Button>
            </>
          ) : (
            <>
              <Loader type="dots" />
              <Text size="sm" c="dimmed">Starting Job Hunter...</Text>
            </>
          )}
        </Stack>
      </Center>
    );
  }

  return (
    <div className="app">
      <Header />
      <PanelGroup direction="horizontal" autoSaveId="jh-main" className="main">
        <Panel defaultSize={22} minSize={17} maxSize={34}>
          <Sidebar />
        </Panel>
        <PanelResizeHandle className="resize-handle vertical" />
        <Panel defaultSize={46} minSize={30}>
          <PanelGroup direction="vertical" autoSaveId="jh-center">
            <Panel defaultSize={64} minSize={25}>
              <JobList />
            </Panel>
            <PanelResizeHandle className="resize-handle horizontal" />
            <Panel defaultSize={36} minSize={14}>
              <ActivityLog />
            </Panel>
          </PanelGroup>
        </Panel>
        <PanelResizeHandle className="resize-handle vertical" />
        <Panel defaultSize={32} minSize={22}>
          <div className="pane"><JobDetail /></div>
        </Panel>
      </PanelGroup>
    </div>
  );
}
