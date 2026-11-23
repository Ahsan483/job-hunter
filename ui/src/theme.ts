import { createTheme, type MantineColorsTuple } from '@mantine/core';

// The blue of the Job Hunter icon, as a calm Windows-style accent ramp.
const brand: MantineColorsTuple = [
  '#ebf3fe', '#d3e4fd', '#a9c9fb', '#7cacf8', '#5894f6', '#3f83f5', '#2f74ec', '#2563d6', '#1d56bd', '#12489f',
];

// Neutral greys for the dark theme (no blue tint): reads like a native Windows app.
const dark: MantineColorsTuple = [
  '#f2f2f4', '#d9d9de', '#b4b4bc', '#8e8e98', '#5a5a63', '#3f3f46', '#2f2f35', '#242429', '#1c1c20', '#141417',
];

export const theme = createTheme({
  primaryColor: 'brand',
  primaryShade: { light: 7, dark: 6 },
  colors: { brand, dark },
  fontFamily: '"Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif',
  fontFamilyMonospace: '"Cascadia Mono", Consolas, monospace',
  headings: { fontFamily: '"Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif', fontWeight: '600' },
  fontSizes: { xs: '12px', sm: '13px', md: '14px', lg: '16px', xl: '18px' },
  defaultRadius: 'sm',
  radius: { xs: '3px', sm: '5px', md: '7px', lg: '9px', xl: '12px' },
  cursorType: 'pointer',
  focusRing: 'auto',
  components: {
    Button: { defaultProps: { fw: 500, radius: 'sm' } },
    Badge: { defaultProps: { radius: 'sm', tt: 'none', fw: 600 } },
    Tooltip: { defaultProps: { openDelay: 400, withArrow: true, multiline: true, maw: 300, fz: 'xs' } },
    Modal: {
      defaultProps: { centered: true, radius: 'md', overlayProps: { backgroundOpacity: 0.4 }, transitionProps: { duration: 150 } },
      styles: { title: { fontWeight: 600, fontSize: '16px' } },
    },
    Notification: { defaultProps: { radius: 'md', withBorder: true } },
    InputWrapper: { styles: { label: { fontWeight: 500, marginBottom: 2 }, description: { marginBottom: 6 } } },
    Menu: { defaultProps: { radius: 'md', shadow: 'md' } },
  },
});
