import React from 'react';
import ReactDOM from 'react-dom/client';
import { MantineProvider } from '@mantine/core';
import { ModalsProvider } from '@mantine/modals';
import { Notifications } from '@mantine/notifications';
import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';
import './styles.css';
import { theme } from './theme';
import App from './App';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="dark">
      <ModalsProvider labels={{ confirm: 'OK', cancel: 'Cancel' }}>
        <Notifications position="bottom-right" limit={4} containerWidth={380} />
        <App />
      </ModalsProvider>
    </MantineProvider>
  </React.StrictMode>,
);
