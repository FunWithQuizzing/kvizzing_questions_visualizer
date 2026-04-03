import type { Question } from '$lib/types';

/** Build a tag-frequency map and sorted tag list from a set of questions. */
export function tagFrequency(questions: Question[]): { tagFreq: Map<string, number>; allTags: string[] } {
  const tagFreq = new Map<string, number>();
  for (const q of questions) {
    for (const tag of q.question.tags ?? []) {
      tagFreq.set(tag, (tagFreq.get(tag) ?? 0) + 1);
    }
  }
  const allTags = [...tagFreq.entries()].sort((a, b) => b[1] - a[1]).map(([t]) => t);
  return { tagFreq, allTags };
}
