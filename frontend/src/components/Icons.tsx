import type { ReactNode } from 'react'

// Paths are the ones drawn in the design files.
function I({ s = 16, w = 1.7, fill, children }: { s?: number; w?: number; fill?: boolean; children: ReactNode }) {
  return (
    <svg aria-hidden="true" width={s} height={s} viewBox="0 0 24 24" fill={fill ? 'currentColor' : 'none'}
      stroke={fill ? 'none' : 'currentColor'} strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" style={{ flex: 'none' }}>
      {children}
    </svg>
  )
}

type P = { s?: number; w?: number }

export const Mail = (p: P) => <I s={15} w={2} {...p}><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" /></I>
export const Grid = (p: P) => <I {...p}><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></I>
export const Inbox = (p: P) => <I {...p}><path d="M22 12h-6l-2 3h-4l-2-3H2" /><path d="M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z" /></I>
export const Terminal = (p: P) => <I {...p}><polyline points="4 17 10 11 4 5" /><line x1="12" y1="19" x2="20" y2="19" /></I>
export const List = (p: P) => <I {...p}><path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01" /></I>
export const Doc = (p: P) => <I {...p}><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6M8 13h8M8 17h6" /></I>
export const User = (p: P) => <I {...p}><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></I>
export const Gear = (p: P) => <I {...p}><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1" /></I>
export const Moon = (p: P) => <I s={15} w={1.8} {...p}><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></I>
export const Dashed = (p: P) => <I s={13} w={2} {...p}><circle cx="12" cy="12" r="9" strokeDasharray="3 3" /></I>
export const Check = (p: P) => <I s={14} w={2.4} {...p}><polyline points="20 6 9 17 4 12" /></I>
export const X = (p: P) => <I s={16} w={2.2} {...p}><path d="M18 6 6 18M6 6l12 12" /></I>
export const Play = (p: P) => <I s={12} fill {...p}><path d="M7 4.5v15l13-7.5z" /></I>
export const Refresh = (p: P) => <I s={13} w={2} {...p}><path d="M21 12a9 9 0 1 1-2.6-6.4" /><polyline points="21 3 21 9 15 9" /></I>
export const Chip = (p: P) => <I s={18} w={1.8} {...p}><rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" /><path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2" /></I>
export const Unlink = (p: P) => <I s={18} w={1.8} {...p}><path d="M9 17H7a5 5 0 0 1 0-10h2M15 7h2a5 5 0 0 1 4 8" /><path d="M8 12h4M3 3l18 18" /></I>
export const Search = (p: P) => <I s={15} w={1.8} {...p}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></I>
export const Plus = (p: P) => <I s={14} w={2.2} {...p}><path d="M12 5v14M5 12h14" /></I>
export const Warn = (p: P) => <I s={13} w={2.2} {...p}><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4M12 17h.01" /></I>
export const Dots = (p: P) => <I s={16} fill {...p}><circle cx="5" cy="12" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="19" cy="12" r="1.6" /></I>
export const Download = (p: P) => <I s={14} w={2} {...p}><path d="M12 4v12M7 11l5 5 5-5M4 20h16" /></I>
export const Calendar = (p: P) => <I s={13} w={1.9} {...p}><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></I>
export const Undo = (p: P) => <I s={13} w={2} {...p}><path d="M9 14 4 9l5-5" /><path d="M4 9h11a5 5 0 0 1 0 10h-3" /></I>
export const Upload = (p: P) => <I s={22} w={1.6} {...p}><path d="M12 16V4M7 9l5-5 5 5" /><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" /></I>
export const FileOk = (p: P) => <I s={16} w={1.8} {...p}><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6" /><polyline points="9 15 11 17 15 13" /></I>
export const SignIn = (p: P) => <I s={16} w={1.8} {...p}><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" /><polyline points="10 17 15 12 10 7" /><line x1="15" y1="12" x2="3" y2="12" /></I>
