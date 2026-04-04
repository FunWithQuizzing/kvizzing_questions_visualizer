import type { Question, Session, Member, QuestionFilters, SortOption } from '$lib/types';
import { dateInTz } from '$lib/utils/time';

export type TagEntry = { tag: string; count: number; question_ids: string[] };
export type Stats = {
  total_questions: number;
  total_sessions: number;
  topic_distribution: Record<string, number>;
  difficulty_distribution: Record<string, number>;
  session_activity: Record<string, number>;
};

export class QuestionStore {
  private questions: Question[];
  private sessions: Session[];
  private members: Member[];
  private tags: TagEntry[];
  private stats: Stats | null;

  constructor(
    questions: Question[],
    sessions: Session[],
    members: Member[],
    tags: TagEntry[] = [],
    stats: Stats | null = null,
  ) {
    this.questions = questions;
    this.sessions = sessions;
    this.members = members;
    this.tags = tags;
    this.stats = stats;
  }

  getQuestions(filters?: QuestionFilters, sort: SortOption = 'newest'): Question[] {
    let results = this.questions.filter(q => q.extraction_confidence !== 'low');

    if (filters) {
      if (filters.dateFrom || filters.dateTo) {
        results = results.filter(q => {
          // If a timezone is provided, compare against the question's timestamp
          // converted to that timezone; otherwise fall back to the stored UTC date.
          const d = filters.tz && q.question?.timestamp
            ? dateInTz(q.question.timestamp, filters.tz)
            : q.date;
          if (filters.dateFrom && d < filters.dateFrom) return false;
          if (filters.dateTo && d > filters.dateTo) return false;
          return true;
        });
      }
      if (filters.asker) {
        results = results.filter(q =>
          q.question.asker.toLowerCase().includes(filters.asker!.toLowerCase())
        );
      }
      if (filters.solver) {
        results = results.filter(q =>
          q.answer?.solver?.toLowerCase().includes(filters.solver!.toLowerCase())
        );
      }
      if (filters.difficulty) {
        results = results.filter(q => q.stats?.difficulty === filters.difficulty);
      }
      if (filters.topic) {
        results = results.filter(q => q.question.topics?.includes(filters.topic!));
      }
      if (filters.has_media !== undefined) {
        results = results.filter(q => q.question.has_media === filters.has_media);
      }
      if (filters.session_id) {
        results = results.filter(q => q.session?.id === filters.session_id);
      }
      if (filters.extraction_confidence) {
        results = results.filter(q => q.extraction_confidence === filters.extraction_confidence);
      }
    }

    return this.sortQuestions(results, sort);
  }

  private sortQuestions(questions: Question[], sort: SortOption): Question[] {
    const q = [...questions];
    switch (sort) {
      case 'newest':
        return q.sort((a, b) => (b.question?.timestamp ?? b.date).localeCompare(a.question?.timestamp ?? a.date));
      case 'oldest':
        return q.sort((a, b) => (a.question?.timestamp ?? a.date).localeCompare(b.question?.timestamp ?? b.date));
      case 'most_discussed':
        return q.sort((a, b) => (b.discussion?.length ?? 0) - (a.discussion?.length ?? 0));
      case 'quickest':
        return q.sort((a, b) => {
          const ta = a.stats?.time_to_answer_seconds ?? Infinity;
          const tb = b.stats?.time_to_answer_seconds ?? Infinity;
          return ta - tb;
        });
      default:
        return q;
    }
  }

  getById(id: string): Question | undefined {
    return this.questions.find(q => q.id === id);
  }

  getSessions(): Session[] {
    return [...this.sessions].sort((a, b) => b.date.localeCompare(a.date));
  }

  getSessionById(id: string): Session | undefined {
    return this.sessions.find(s => s.id === id);
  }

  getSessionQuestions(session_id: string, sort: SortOption = 'oldest'): Question[] {
    const sessionQs = this.questions.filter(q => q.session?.id === session_id);
    return this.sortQuestions(sessionQs, sort);
  }

  random(filters?: QuestionFilters): Question | undefined {
    const pool = this.getQuestions(filters);
    if (pool.length === 0) return undefined;
    return pool[Math.floor(Math.random() * pool.length)];
  }

  getMembers(): Member[] {
    return this.members;
  }

  getMember(username: string): Member | undefined {
    return this.members.find(m => m.username === username);
  }

  getTags(): TagEntry[] {
    return this.tags;
  }

  getTagFreq(): { tagFreq: Map<string, number>; allTags: string[] } {
    const tagFreq = new Map<string, number>();
    for (const t of this.tags) {
      tagFreq.set(t.tag, t.count);
    }
    const allTags = this.tags.map(t => t.tag);
    return { tagFreq, allTags };
  }

  getStats(): Stats | null {
    return this.stats;
  }

  getAskers(): string[] {
    const askers = new Set(this.questions.map(q => q.question.asker));
    return [...askers].sort();
  }

  getSolvers(): string[] {
    const solvers = new Set(
      this.questions.filter(q => q.answer?.solver).map(q => q.answer.solver)
    );
    return [...solvers].sort();
  }

  getTopics(): string[] {
    const topics = new Set(
      this.questions.flatMap(q => q.question.topics ?? [])
    );
    return [...topics].sort();
  }

  /** Returns a map of session ID → earliest question ISO timestamp in that session. */
  getSessionEarliestTimestamps(): Map<string, string> {
    const map = new Map<string, string>();
    for (const q of this.questions) {
      if (q.session?.id && q.question?.timestamp) {
        const existing = map.get(q.session.id);
        if (!existing || q.question.timestamp < existing) {
          map.set(q.session.id, q.question.timestamp);
        }
      }
    }
    return map;
  }

  getTotalStats() {
    const questions = this.questions.filter(q => q.extraction_confidence !== 'low');
    const earliest = questions.reduce<Question | null>(
      (min, q) => {
        const ts = q.question?.timestamp ?? q.date;
        const minTs = min?.question?.timestamp ?? min?.date ?? '';
        return !min || ts < minTs ? q : min;
      }, null
    );
    return {
      total: questions.length,
      sessions: this.sessions.length,
      earliestDate: earliest?.date ?? '',
      earliestTimestamp: earliest?.question?.timestamp ?? earliest?.date ?? '',
    };
  }

  getAdjacentQuestions(id: string, filters?: QuestionFilters): { prev: Question | null; next: Question | null } {
    const list = this.getQuestions(filters);
    const idx = list.findIndex(q => q.id === id);
    return {
      prev: idx > 0 ? list[idx - 1] : null,
      next: idx < list.length - 1 ? list[idx + 1] : null,
    };
  }

  getAdjacentSessions(id: string): { prev: Session | null; next: Session | null } {
    const list = this.getSessions(); // newest first
    const idx = list.findIndex(s => s.id === id);
    return {
      prev: idx > 0 ? list[idx - 1] : null,
      next: idx < list.length - 1 ? list[idx + 1] : null,
    };
  }
}
