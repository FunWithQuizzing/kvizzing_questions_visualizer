/**
 * Filter hint texts to remove noise: short rejections ("Nope"), vague reactions
 * ("Getting there"), and contextual follow-ups that make no sense without the
 * preceding message ("And y?", "It behaves like it is").
 *
 * TODO: This heuristic is fragile — it will miss edge cases in both directions
 * (filtering useful hints, keeping useless ones). The right fix is to re-run
 * extraction with a better prompt that distinguishes genuine hints from
 * rejection messages, or to run a dedicated LLM pass over all discussion
 * entries tagged role='hint' and re-classify them as hint vs. rejection vs.
 * context-dependent before import.
 */

// Patterns that indicate a reaction to a wrong guess rather than a real hint.
const REJECTION_RE = /^(nope|not quite|close[,.\s]|but close|getting there|very close|you'?re almost|it behaves|it'?s a very topical|too much overthink|in the right neighborhood|and y[?]|and so the|annie besant and|yes,? was looking|while captaining)/i;

export function isUsefulHint(text: string): boolean {
  const t = text.trim();
  // Always keep explicitly labelled hints
  if (/^hint[:\s]/i.test(t)) return true;
  // Drop anything too short to carry standalone meaning
  if (t.length < 15) return false;
  // Drop known reaction/rejection patterns
  if (REJECTION_RE.test(t)) return false;
  return true;
}

export function filterHints(texts: string[]): string[] {
  return texts.filter(isUsefulHint);
}
