export interface MediaAttachment {
  type: 'image' | 'video' | 'audio' | 'document';
  url: string | null;
  filename: string | null;
  caption: string | null;
}

export interface DiscussionEntry {
  timestamp: string;
  username: string;
  text: string;
  role: 'attempt' | 'hint' | 'confirmation' | 'answer_reveal' | 'chat' | 'elaboration';
  is_correct: boolean | null;
  has_media: boolean;
  media: MediaAttachment[] | null;
}

export interface QuestionData {
  timestamp: string;
  text: string;
  asker: string;
  type: string;
  has_media: boolean;
  media: MediaAttachment[] | null;
  topics: string[];
  tags: string[];
}

export interface AnswerData {
  text: string;
  solver: string;
  timestamp: string;
  confirmed: boolean;
  confirmation_text: string;
  is_collaborative: boolean;
  parts: { label: string; text: string; solver: string | null }[] | null;
}

export interface QuestionStats {
  wrong_attempts: number;
  hints_given: number;
  time_to_answer_seconds: number;
  unique_participants: number;
  difficulty: 'easy' | 'medium' | 'hard' | null;
}

export interface SessionRef {
  id: string;
  quizmaster: string;
  question_number: number;
  theme: string | null;
  quiz_type?: 'connect' | null;
}

export interface Question {
  id: string;
  date: string;
  question: QuestionData;
  answer: AnswerData;
  discussion: DiscussionEntry[];
  stats: QuestionStats;
  extraction_confidence: 'high' | 'medium' | 'low';
  session: SessionRef | null;
  scores_after: unknown;
  reactions: unknown;
  highlights: unknown;
}

export interface Session {
  id: string;
  quizmaster: string;
  theme: string | null;
  date: string;
  question_count: number;
  avg_time_to_answer_seconds: number | null;
  avg_wrong_attempts: number | null;
  participant_count: number;
  scores: unknown;
  /** If 'connect', the theme is the answer to a connect quiz and should be hidden until revealed. */
  quiz_type?: 'connect' | null;
  /** Quizmaster's introductory message announcing the session */
  announcement?: string | null;
}

export interface Member {
  username: string;
  display_name: string;
  color: string | null;
  avatar_url: string | null;
  questions_asked: number;
  questions_solved: number;
  total_attempts: number;
  sessions_hosted: number;
  avg_solve_time_seconds: number | null;
}

export interface QuestionFilters {
  dateFrom?: string;
  dateTo?: string;
  /** IANA timezone string (e.g. 'Asia/Kolkata'). When provided, date comparisons
   *  use the question's full timestamp converted to this timezone rather than the
   *  stored UTC date string. */
  tz?: string;
  asker?: string;
  solver?: string;
  difficulty?: 'easy' | 'medium' | 'hard' | '';
  topic?: string;
  has_media?: boolean;
  session_id?: string;
  extraction_confidence?: 'high' | 'medium' | 'low' | '';
  search?: string;
}

export type SortOption = 'newest' | 'oldest' | 'most_discussed' | 'quickest';
