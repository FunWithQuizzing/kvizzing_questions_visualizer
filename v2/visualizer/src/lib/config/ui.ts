/** Opacity of session background images (0–1).
 *  The wrapper's background colour shows through, so this is the only knob needed. */
export const SESSION_IMAGE_OPACITY = {
  /** Full session page header (bg-gray-900 base) */
  header: 0.6,
  /** Session card on the /sessions list page (default / hover) */
  card: { default: 0.25, hover: 0.45 },
  /** Sidebar session tile (default / hover) */
  sidebar: { default: 0.15, hover: 0.35 },
} as const;

/** Sessions that have a custom background image in /images/sessions/. */
const SESSION_IMAGES = new Set([
  '2025-09-25-akshay', '2025-09-28-aditi', '2025-09-29-abhishek',
  '2025-09-29-aditi', '2025-10-02-kartikey', '2025-10-03-prathamesh',
  '2025-10-05-akshay', '2025-10-10-kartikey', '2025-10-11-pavan',
  '2025-10-12-abhishek', '2025-10-14-akshay', '2025-10-22-akshay',
]);

/** Return the background image URL for a session card. */
export function sessionBgUrl(session: { id: string; quiz_type?: string | null }): string {
  if (session.quiz_type === 'connect') return '/images/connect-quiz-bg.png';
  if (SESSION_IMAGES.has(session.id)) return `/images/sessions/${session.id}.jpg`;
  return '/images/connect-quiz-bg.png';
}

/** Tailwind classes for calendar day pills. */
export const CALENDAR_PILL = {
  /** Question count pill — lighter than the theme color */
  questions: { bg: 'bg-primary-200', text: 'text-primary-700' },
  /** Quiz session pill — darker than the theme color */
  sessions: { bg: 'bg-primary-800', text: 'text-white', hover: 'hover:bg-primary-900' },
} as const;
