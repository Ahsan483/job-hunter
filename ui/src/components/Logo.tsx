/** The Job Hunter app icon (the same one as the taskbar and the installer). */
export function Logo({ size = 28 }: { size?: number }) {
  return <img src="./icon.png" width={size} height={size} alt="" draggable={false} style={{ display: 'block' }} />;
}
