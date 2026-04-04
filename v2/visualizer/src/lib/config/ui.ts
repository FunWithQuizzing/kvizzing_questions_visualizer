/** Opacity of session background images (0–1).
 *  The wrapper's background colour shows through, so this is the only knob needed. */
export const SESSION_IMAGE_OPACITY = {
  /** Full session page header (bg-gray-900 base) */
  header: 0.6,
  /** Session card on the /sessions list page (default / hover) */
  card: { default: 0.4, hover: 0.6 },
  /** Sidebar session tile (default / hover) */
  sidebar: { default: 0.15, hover: 0.35 },
} as const;

/** Sessions that have a custom background image in /images/sessions/. */
/** Return the background image URL for a session card.
 *  Always tries the session-specific image first; falls back to connect-quiz-bg. */
export function sessionBgUrl(session: { id: string; quiz_type?: string | null }): string {
  if (session.quiz_type === 'connect') return '/images/connect-quiz-bg.png';
  return `/images/sessions/${session.id}.jpg`;
}

/** Tailwind classes for calendar day pills. */
export const CALENDAR_PILL = {
  /** Question count pill — lighter than the theme color */
  questions: { bg: 'bg-primary-200', text: 'text-primary-700' },
  /** Quiz session pill — darker than the theme color */
  sessions: { bg: 'bg-primary-800', text: 'text-white', hover: 'hover:bg-primary-900' },
} as const;
