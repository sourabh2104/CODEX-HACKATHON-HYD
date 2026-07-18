import type { SVGProps } from 'react';

type IconName = 'grid' | 'link' | 'bot' | 'shield' | 'bolt' | 'search' | 'bell' | 'chevron' | 'arrow' | 'plus' | 'check' | 'alert' | 'activity' | 'rocket' | 'flask' | 'clock' | 'more' | 'sliders' | 'external' | 'eye' | 'refresh' | 'x' | 'spark' | 'terminal' | 'filter' | 'pause' | 'play' | 'user' | 'settings';

const paths: Record<IconName, string> = {
  grid: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',
  link: 'M10 13a5 5 0 0 0 7.07.07l2-2a5 5 0 0 0-7.07-7.07l-1.15 1.15m-1.7 1.7-2 2a5 5 0 0 0 7.07 7.07l1.15-1.15M8 12h8',
  bot: 'M12 3v3m-5 4h.01M17 10h.01M8 21h8a3 3 0 0 0 3-3v-6a3 3 0 0 0-3-3H8a3 3 0 0 0-3 3v6a3 3 0 0 0 3 3Zm1-5h6',
  shield: 'M12 3 20 6v5c0 5-3.4 8.4-8 10-4.6-1.6-8-5-8-10V6l8-3Zm-3 9 2 2 4-4',
  bolt: 'm13 2-9 11h7l-1 9 9-11h-7l1-9Z',
  search: 'm21 21-4.35-4.35m2.35-5.65a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z',
  bell: 'M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4',
  chevron: 'm6 9 6 6 6-6',
  arrow: 'M5 12h14m-6-6 6 6-6 6',
  plus: 'M12 5v14M5 12h14',
  check: 'm5 12 4 4L19 6',
  alert: 'M12 9v4m0 4h.01M10.3 4.2 2.5 18a2 2 0 0 0 1.7 3h15.6a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0Z',
  activity: 'M3 12h4l2-7 4 14 2-7h6',
  rocket: 'M14 5c3-3 6-3 6-3s0 3-3 6l-4 4-3-3 4-4ZM10 9l-4 1-3 3 5 1m2 0 4 4-1 4-3-3 1-4M6 18l-3 3',
  flask: 'M9 3h6m-5 0v6l-5.5 9A2 2 0 0 0 6.2 21h11.6a2 2 0 0 0 1.7-3L14 9V3M7 16h10',
  clock: 'M12 7v5l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  sliders: 'M4 6h16M7 6v4m10-4v4M4 18h16M7 14v4m10-4v4',
  external: 'M14 5h5v5m0-5-7 7m-2-5H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4',
  eye: 'M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6Zm10 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
  refresh: 'M20 11a8 8 0 0 0-14.9-3M4 5v4h4m-4 2a8 8 0 0 0 14.9 3M20 19v-4h-4',
  x: 'M6 6l12 12M18 6 6 18',
  spark: 'm12 3-1.2 5.8L5 10l5.8 1.2L12 17l1.2-5.8L19 10l-5.8-1.2L12 3ZM19 16l-.6 2.4L16 19l2.4.6L19 22l.6-2.4L22 19l-2.4-.6L19 16Z',
  terminal: 'm5 7 5 5-5 5m7 0h7',
  filter: 'M4 5h16l-6 7v5l-4 2v-7L4 5Z',
  pause: 'M8 5v14m8-14v14',
  play: 'm8 5 11 7-11 7V5Z',
  user: 'M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2m7-10a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
  settings: 'M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm7.4-3.5a7.7 7.7 0 0 0-.1-1.1l2-1.5-2-3.4-2.4 1a8 8 0 0 0-1.9-1.1L14.7 3h-4l-.4 2.9a8 8 0 0 0-1.9 1.1l-2.4-1-2 3.4 2 1.5a7.7 7.7 0 0 0 0 2.2l-2 1.5 2 3.4 2.4-1a8 8 0 0 0 1.9 1.1l.4 2.9h4l.4-2.9a8 8 0 0 0 1.9-1.1l2.4 1 2-3.4-2-1.5c.1-.4.1-.8.1-1.1Z',
};

export function Icon({ name, size = 18, strokeWidth = 1.8, ...props }: { name: IconName; size?: number; strokeWidth?: number } & Omit<SVGProps<SVGSVGElement>, 'name'>) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}><path d={paths[name]} /></svg>;
}
