import type { SVGProps } from 'react';

const base = { width: 16, height: 16, viewBox: '0 0 20 20', fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round', strokeLinejoin: 'round' } as const;
type P = SVGProps<SVGSVGElement>;

export const LogoMark = (p: P) => (
  <svg viewBox="0 0 32 22" width={30} height={20} {...p}>
    <path d="M1 20 L10 4 L15 12 L19 7 L31 20 Z" fill="#2c6e9b" />
    <path d="M1 17c3-2 5-2 8 0s5 2 8 0 5-2 8 0 4 2 6 1v4H1z" fill="#8cc0e0" />
  </svg>
);
export const MapIcon = (p: P) => (
  <svg {...base} {...p}><path d="M3 5l4.5-2 5 2L17 3v12l-4.5 2-5-2L3 17z" /><path d="M7.5 3v12M12.5 5v12" /></svg>
);
export const PinIcon = (p: P) => (
  <svg {...base} {...p}><path d="M10 18s5.5-5.2 5.5-9.5a5.5 5.5 0 0 0-11 0C4.5 12.8 10 18 10 18z" /><circle cx="10" cy="8.5" r="2" /></svg>
);
export const DroneIcon = (p: P) => (
  <svg {...base} {...p}><circle cx="4.5" cy="4.5" r="2.2" /><circle cx="15.5" cy="4.5" r="2.2" /><circle cx="4.5" cy="15.5" r="2.2" /><circle cx="15.5" cy="15.5" r="2.2" /><path d="M6.5 6.5l7 7M13.5 6.5l-7 7" /></svg>
);
export const TruckIcon = (p: P) => (
  <svg {...base} {...p}><path d="M2 6h9v7H2zM11 9h4l3 3v1h-7" /><circle cx="5.5" cy="14.5" r="1.6" /><circle cx="14.5" cy="14.5" r="1.6" /></svg>
);
export const CalendarIcon = (p: P) => (
  <svg {...base} {...p}><rect x="3" y="4" width="14" height="13" rx="2" /><path d="M3 8h14M7 2.5v3M13 2.5v3" /></svg>
);
export const GearIcon = (p: P) => (
  <svg {...base} {...p}><circle cx="10" cy="10" r="2.8" /><path d="M10 2.5v2.3M10 15.2v2.3M2.5 10h2.3M15.2 10h2.3M4.7 4.7l1.6 1.6M13.7 13.7l1.6 1.6M15.3 4.7l-1.6 1.6M6.3 13.7l-1.6 1.6" /></svg>
);
export const ShareIcon = (p: P) => (
  <svg {...base} {...p}><circle cx="5" cy="10" r="2" /><circle cx="15" cy="5" r="2" /><circle cx="15" cy="15" r="2" /><path d="M6.8 9l6.4-3M6.8 11l6.4 3" /></svg>
);
export const ChartIcon = (p: P) => (
  <svg {...base} {...p}><path d="M3 17h14M5 14V9M9 14V5M13 14v-3M17 14V7" /></svg>
);
export const ViewIcon = (p: P) => (
  <svg {...base} {...p}><rect x="3" y="3" width="14" height="14" rx="2" /><path d="M3 8h14M8 8v9" /></svg>
);
export const Chevron = (p: P) => (
  <svg {...base} width={11} height={11} {...p}><path d="M5 8l5 5 5-5" /></svg>
);
export const PlayIcon = (p: P) => (
  <svg viewBox="0 0 20 20" width={14} height={14} {...p}><path d="M6 4l10 6-10 6z" fill="currentColor" /></svg>
);
export const PauseIcon = (p: P) => (
  <svg viewBox="0 0 20 20" width={14} height={14} {...p}><path d="M5 4h3.5v12H5zM11.5 4H15v12h-3.5z" fill="currentColor" /></svg>
);
export const StepIcon = (p: P) => (
  <svg viewBox="0 0 20 20" width={14} height={14} {...p}><path d="M4 4l9 6-9 6zM14 4h2.5v12H14z" fill="currentColor" /></svg>
);
export const FullscreenIcon = (p: P) => (
  <svg {...base} {...p}><path d="M3 7V3h4M13 3h4v4M17 13v4h-4M7 17H3v-4" /></svg>
);
export const RainIcon = (p: P) => (
  <svg {...base} {...p}><path d="M5.5 11a3.5 3.5 0 01.4-7 4.5 4.5 0 018.6 1.2A3 3 0 0114.5 11z" /><path d="M7 14l-1 2.5M10.5 14l-1 2.5M14 14l-1 2.5" /></svg>
);
export const GaugeIcon = (p: P) => (
  <svg {...base} {...p}><path d="M3 15a7 7 0 1114 0" /><path d="M10 15l3.5-5" /></svg>
);
export const WaveIcon = (p: P) => (
  <svg {...base} {...p}><path d="M2 8c2-1.6 4-1.6 6 0s4 1.6 6 0 3-1.2 4-.6M2 13c2-1.6 4-1.6 6 0s4 1.6 6 0 3-1.2 4-.6" /></svg>
);
export const DropIcon = (p: P) => (
  <svg {...base} {...p}><path d="M10 2.5c-3 4.4-5 7-5 9.6a5 5 0 0010 0c0-2.6-2-5.2-5-9.6z" /></svg>
);
export const HouseIcon = (p: P) => (
  <svg {...base} {...p}><path d="M3 9.5L10 3.5l7 6M5 8v8.5h10V8" /><path d="M3 13.5h14" strokeDasharray="2 1.6" /></svg>
);
export const ArrowIcon = (p: P) => (
  <svg {...base} {...p}><path d="M3 10h12M11 6l4 4-4 4" /></svg>
);
