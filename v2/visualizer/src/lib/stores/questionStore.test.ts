import { describe, it, expect } from 'vitest';
import { QuestionStore } from './questionStore';
import type { Question, Session, Member } from '$lib/types';

// Minimal factories — only populate fields relevant to the tests
function makeQuestion(overrides: Partial<Question> & { id: string }): Question {
  return {
    date: overrides.date ?? '2024-01-15',
    question: {
      timestamp: overrides.question?.timestamp ?? '2024-01-15T12:00:00Z',
      text: 'Q?',
      asker: 'alice',
      type: 'text',
      has_media: false,
      media: null,
      topics: [],
      tags: [],
      ...overrides.question,
    },
    answer: {
      text: 'A',
      solver: 'bob',
      timestamp: '2024-01-15T12:01:00Z',
      confirmed: true,
      confirmation_text: '',
      is_collaborative: false,
      parts: null,
      ...overrides.answer,
    },
    discussion: [],
    stats: {
      wrong_attempts: 0,
      hints_given: 0,
      time_to_answer_seconds: 60,
      unique_participants: 1,
      difficulty: null,
    },
    extraction_confidence: 'high',
    session: overrides.session ?? null,
    scores_after: null,
    reactions: null,
    highlights: null,
    ...overrides,
  };
}

const NO_SESSIONS: Session[] = [];
const NO_MEMBERS: Member[] = [];

describe('QuestionStore — timezone-aware date filtering', () => {
  // This question was asked at 22:30 UTC on Jan 15.
  // In London (UTC+0 in winter) → still Jan 15.
  // In IST (UTC+5:30)           → Jan 16 (04:00 next day).
  const lateNightQ = makeQuestion({
    id: 'q1',
    date: '2024-01-15',               // stored UTC date
    question: { timestamp: '2024-01-15T22:30:00Z' } as any,
  });

  it('includes question when dateFrom/dateTo matches stored UTC date (no tz)', () => {
    const store = new QuestionStore([lateNightQ], NO_SESSIONS, NO_MEMBERS);
    const results = store.getQuestions({ dateFrom: '2024-01-15', dateTo: '2024-01-15' });
    expect(results).toHaveLength(1);
  });

  it('excludes question when stored date is outside range (no tz)', () => {
    const store = new QuestionStore([lateNightQ], NO_SESSIONS, NO_MEMBERS);
    const results = store.getQuestions({ dateFrom: '2024-01-16', dateTo: '2024-01-16' });
    expect(results).toHaveLength(0);
  });

  it('includes question on Jan 16 in IST even though stored date is Jan 15', () => {
    const store = new QuestionStore([lateNightQ], NO_SESSIONS, NO_MEMBERS);
    const results = store.getQuestions({
      dateFrom: '2024-01-16',
      dateTo: '2024-01-16',
      tz: 'Asia/Kolkata',
    });
    expect(results).toHaveLength(1);
  });

  it('excludes question on Jan 15 in IST because it falls on Jan 16 in IST', () => {
    const store = new QuestionStore([lateNightQ], NO_SESSIONS, NO_MEMBERS);
    const results = store.getQuestions({
      dateFrom: '2024-01-15',
      dateTo: '2024-01-15',
      tz: 'Asia/Kolkata',
    });
    expect(results).toHaveLength(0);
  });

  it('includes question on Jan 15 in London (no DST in January)', () => {
    const store = new QuestionStore([lateNightQ], NO_SESSIONS, NO_MEMBERS);
    const results = store.getQuestions({
      dateFrom: '2024-01-15',
      dateTo: '2024-01-15',
      tz: 'Europe/London',
    });
    expect(results).toHaveLength(1);
  });

  it('falls back to q.date when question has no timestamp', () => {
    const noTsQ = makeQuestion({
      id: 'q2',
      date: '2024-01-15',
      question: { timestamp: '' } as any,
    });
    const store = new QuestionStore([noTsQ], NO_SESSIONS, NO_MEMBERS);
    const results = store.getQuestions({
      dateFrom: '2024-01-15',
      dateTo: '2024-01-15',
      tz: 'Asia/Kolkata',
    });
    expect(results).toHaveLength(1);
  });

  it('handles multiple questions across a timezone boundary correctly', () => {
    // q_early: 10:00 UTC Jan 15 → Jan 15 in both London and IST (15:30 IST)
    const qEarly = makeQuestion({
      id: 'q_early',
      date: '2024-01-15',
      question: { timestamp: '2024-01-15T10:00:00Z' } as any,
    });
    // q_late: 22:30 UTC Jan 15 → Jan 15 London, Jan 16 IST
    const qLate = makeQuestion({
      id: 'q_late',
      date: '2024-01-15',
      question: { timestamp: '2024-01-15T22:30:00Z' } as any,
    });

    const store = new QuestionStore([qEarly, qLate], NO_SESSIONS, NO_MEMBERS);

    // In IST: Jan 15 should only include q_early
    const jan15Ist = store.getQuestions({ dateFrom: '2024-01-15', dateTo: '2024-01-15', tz: 'Asia/Kolkata' });
    expect(jan15Ist.map(q => q.id)).toEqual(['q_early']);

    // In IST: Jan 16 should only include q_late
    const jan16Ist = store.getQuestions({ dateFrom: '2024-01-16', dateTo: '2024-01-16', tz: 'Asia/Kolkata' });
    expect(jan16Ist.map(q => q.id)).toEqual(['q_late']);

    // In London: Jan 15 should include both
    const jan15London = store.getQuestions({ dateFrom: '2024-01-15', dateTo: '2024-01-15', tz: 'Europe/London' });
    expect(jan15London).toHaveLength(2);
  });

  it('works for PST (UTC-8): 02:00 UTC Jan 15 → Jan 14 PST', () => {
    const earlyUtcQ = makeQuestion({
      id: 'q_pst',
      date: '2024-01-15',
      question: { timestamp: '2024-01-15T02:00:00Z' } as any,
    });
    const store = new QuestionStore([earlyUtcQ], NO_SESSIONS, NO_MEMBERS);

    // In LA (PST, UTC-8): 02:00 UTC = 18:00 Jan 14 PST
    const jan14 = store.getQuestions({ dateFrom: '2024-01-14', dateTo: '2024-01-14', tz: 'America/Los_Angeles' });
    expect(jan14).toHaveLength(1);

    const jan15 = store.getQuestions({ dateFrom: '2024-01-15', dateTo: '2024-01-15', tz: 'America/Los_Angeles' });
    expect(jan15).toHaveLength(0);
  });

  it('filters low confidence questions regardless of tz', () => {
    const lowQ = makeQuestion({
      id: 'q_low',
      date: '2024-01-15',
      extraction_confidence: 'low',
      question: { timestamp: '2024-01-15T22:30:00Z' } as any,
    });
    const store = new QuestionStore([lowQ], NO_SESSIONS, NO_MEMBERS);
    const results = store.getQuestions({ dateFrom: '2024-01-16', dateTo: '2024-01-16', tz: 'Asia/Kolkata' });
    expect(results).toHaveLength(0);
  });
});
