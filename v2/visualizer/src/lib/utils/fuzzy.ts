/**
 * Simple fuzzy matching for answer submission.
 * Returns a score 0-1 (1 = exact match, 0 = no match).
 */
function levenshtein(a: string, b: string): number {
  const m = a.length, n = b.length;
  const dp: number[][] = Array.from({ length: m + 1 }, (_, i) =>
    Array.from({ length: n + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0))
  );
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = a[i - 1] === b[j - 1]
        ? dp[i - 1][j - 1]
        : 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
    }
  }
  return dp[m][n];
}

export function matchScore(input: string, answer: string): number {
  const a = input.trim().toLowerCase();
  const b = answer.trim().toLowerCase();
  if (a === b) return 1;
  if (b.includes(a) || a.includes(b)) return 0.9;

  // Check if input closely matches any key word/phrase in the answer
  // (handles "Fyenman" matching "Feynman" in a long title)
  const answerWords = b.split(/[\s,.:;!?'"()]+/).filter(w => w.length >= 3);
  const inputWords = a.split(/[\s,.:;!?'"()]+/).filter(w => w.length >= 3);
  for (const iw of inputWords) {
    for (const aw of answerWords) {
      const wordDist = levenshtein(iw, aw);
      const wordMax = Math.max(iw.length, aw.length);
      const wordScore = 1 - wordDist / wordMax;
      // A close match on a significant word boosts the overall score
      if (wordScore >= 0.7 && aw.length >= 4) {
        const fullScore = 1 - levenshtein(a, b) / Math.max(a.length, b.length);
        return Math.max(fullScore, wordScore * 0.95);
      }
    }
  }

  const dist = levenshtein(a, b);
  const maxLen = Math.max(a.length, b.length);
  if (maxLen === 0) return 1;
  return Math.max(0, 1 - dist / maxLen);
}

export function isCorrect(input: string, answer: string, threshold = 0.7): boolean {
  return matchScore(input, answer) >= threshold;
}

export function isAlmost(input: string, answer: string, threshold = 0.7): boolean {
  const score = matchScore(input, answer);
  return score >= 0.4 && score < threshold;
}
