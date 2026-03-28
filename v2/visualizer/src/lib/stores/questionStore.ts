import type { Question, Session, Member, QuestionFilters, SortOption } from '$lib/types';

export class QuestionStore {
  private questions: Question[];
  private sessions: Session[];
  private members: Member[];

  constructor(questions: Question[], sessions: Session[], members: Member[]) {
    this.questions = questions;
    this.sessions = sessions;
    this.members = members;
  }

  getQuestions(filters?: QuestionFilters, sort: SortOption = 'newest'): Question[] {
    let results = this.questions.filter(q => q.extraction_confidence !== 'low');

    if (filters) {
      if (filters.dateFrom) {
        results = results.filter(q => q.date >= filters.dateFrom!);
      }
      if (filters.dateTo) {
        results = results.filter(q => q.date <= filters.dateTo!);
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
        results = results.filter(q => q.question.topic === filters.topic);
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
        return q.sort((a, b) => b.date.localeCompare(a.date));
      case 'oldest':
        return q.sort((a, b) => a.date.localeCompare(b.date));
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
      this.questions.filter(q => q.question.topic).map(q => q.question.topic!)
    );
    return [...topics].sort();
  }

  getTotalStats() {
    const questions = this.questions.filter(q => q.extraction_confidence !== 'low');
    return {
      total: questions.length,
      sessions: this.sessions.length,
      earliestDate: questions.reduce((min, q) => q.date < min ? q.date : min, questions[0]?.date ?? ''),
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
