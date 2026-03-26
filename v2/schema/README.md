# KVizzing Question Schema

## Design Decisions

- **`id`**: `YYYY-MM-DD-NNN` format (human-readable, chronologically sortable)
- **`answer.parts`**: Handles multi-part questions (e.g. "Id X, Y, Z") where different people may solve each part
- **`answer.is_collaborative`**: True when multiple people contribute to the full answer
- **`session`**: Null for ad-hoc questions; populated when a quizmaster runs a structured quiz (detected by "###Quiz Start", score tracking, etc.)
- **`extraction_confidence`**: `high` = asker explicitly confirmed; `medium` = inferred from context; `low` = no confirmation found
- **`topic`** and **`difficulty`**: Optional fields, best assigned by LLM post-processing. Difficulty can be derived from `stats.wrong_attempts` heuristically.
- **`discussion`**: Full ordered message thread for website replay and context display
- **`reactions`** / **`highlights`**: Optional enrichment from WhatsApp SQLite DB (iOS: `ChatStorage.sqlite`; Android: `msgstore.db`). Null when unavailable.

---

## JSON Schema

> **Auto-generated** — do not edit by hand. Run `python3 schema.py` to regenerate from the Pydantic models in `schema.py`, which is the single source of truth.

<!-- BEGIN:schema.json -->
```json
{
  "$defs": {
    "Answer": {
      "properties": {
        "text": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "The correct answer text. Null if answer was never confirmed or revealed.",
          "title": "Text"
        },
        "solver": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Username of the first person to give the correct answer. Null if asker revealed without anyone getting it.",
          "title": "Solver"
        },
        "timestamp": {
          "anyOf": [
            {
              "format": "date-time",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Timestamp of the winning answer message. For collaborative/answer_reveal cases this is the confirmation message timestamp. Null if unanswered.",
          "title": "Timestamp"
        },
        "confirmed": {
          "description": "Whether the asker explicitly confirmed the answer",
          "title": "Confirmed",
          "type": "boolean"
        },
        "confirmation_text": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "The exact message the asker used to confirm (e.g. 'correct', 'Bingo', 'Yes!')",
          "title": "Confirmation Text"
        },
        "is_collaborative": {
          "description": "True when multiple participants together produced the full answer",
          "title": "Is Collaborative",
          "type": "boolean"
        },
        "parts": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/AnswerPart"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "For multi-part questions (X/Y/Z style). Null for single-answer questions.",
          "title": "Parts"
        }
      },
      "required": [
        "confirmed",
        "is_collaborative"
      ],
      "title": "Answer",
      "type": "object"
    },
    "AnswerPart": {
      "properties": {
        "label": {
          "description": "Part identifier (e.g. 'X', 'Y', 'Z', or '1', '2', '3')",
          "title": "Label",
          "type": "string"
        },
        "text": {
          "description": "The answer for this part",
          "title": "Text",
          "type": "string"
        },
        "solver": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Who solved this specific part",
          "title": "Solver"
        }
      },
      "required": [
        "label",
        "text"
      ],
      "title": "AnswerPart",
      "type": "object"
    },
    "Difficulty": {
      "enum": [
        "easy",
        "medium",
        "hard"
      ],
      "title": "Difficulty",
      "type": "string"
    },
    "DiscussionEntry": {
      "properties": {
        "timestamp": {
          "format": "date-time",
          "title": "Timestamp",
          "type": "string"
        },
        "username": {
          "title": "Username",
          "type": "string"
        },
        "text": {
          "title": "Text",
          "type": "string"
        },
        "role": {
          "$ref": "#/$defs/DiscussionRole"
        },
        "is_correct": {
          "anyOf": [
            {
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "True if this attempt was the winning answer. Null for non-attempt roles.",
          "title": "Is Correct"
        },
        "media": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/MediaAttachment"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Media attachments on this discussion message (e.g. an image posted as a hint). Null when unavailable or not applicable.",
          "title": "Media"
        }
      },
      "required": [
        "timestamp",
        "username",
        "text",
        "role"
      ],
      "title": "DiscussionEntry",
      "type": "object"
    },
    "DiscussionRole": {
      "enum": [
        "attempt",
        "hint",
        "confirmation",
        "chat",
        "answer_reveal"
      ],
      "title": "DiscussionRole",
      "type": "string"
    },
    "ExtractionConfidence": {
      "enum": [
        "high",
        "medium",
        "low"
      ],
      "title": "ExtractionConfidence",
      "type": "string"
    },
    "Highlights": {
      "properties": {
        "reaction_counts": {
          "additionalProperties": {
            "type": "integer"
          },
          "description": "Total count per emoji across all thread messages. Keys are emoji characters, values are counts. Open-ended map.",
          "title": "Reaction Counts",
          "type": "object"
        },
        "total_reactions": {
          "description": "Sum of all reaction_counts values. Useful for sorting by engagement.",
          "minimum": 0,
          "title": "Total Reactions",
          "type": "integer"
        },
        "categories": {
          "description": "Derived category labels from a configurable emoji→category mapping (e.g. '😂'→'funny', '❤️'→'crowd_favourite'). New categories are added by updating the pipeline config, not this schema.",
          "items": {
            "type": "string"
          },
          "title": "Categories",
          "type": "array"
        }
      },
      "required": [
        "reaction_counts",
        "total_reactions",
        "categories"
      ],
      "title": "Highlights",
      "type": "object"
    },
    "MediaAttachment": {
      "properties": {
        "type": {
          "$ref": "#/$defs/MediaType",
          "description": "Media type — image, video, audio, or document"
        },
        "url": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "URL of the hosted media file (e.g. CDN path, GitHub LFS URL). Null until the file is extracted from a WhatsApp backup and hosted.",
          "title": "Url"
        },
        "filename": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Original filename from the WhatsApp backup (e.g. 'IMG-20260316-WA0007.jpg'). Null if unavailable.",
          "title": "Filename"
        },
        "caption": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Caption text attached to the media message, if any.",
          "title": "Caption"
        }
      },
      "required": [
        "type"
      ],
      "title": "MediaAttachment",
      "type": "object"
    },
    "MediaType": {
      "enum": [
        "image",
        "video",
        "audio",
        "document"
      ],
      "title": "MediaType",
      "type": "string"
    },
    "Question": {
      "properties": {
        "timestamp": {
          "description": "ISO 8601 timestamp of the question message",
          "format": "date-time",
          "title": "Timestamp",
          "type": "string"
        },
        "text": {
          "description": "Full question text, cleaned of WhatsApp artifacts",
          "title": "Text",
          "type": "string"
        },
        "asker": {
          "description": "Username of the question poser (normalised, without leading ~)",
          "title": "Asker",
          "type": "string"
        },
        "type": {
          "$ref": "#/$defs/QuestionType",
          "description": "Question format type — describes the thinking required, independent of medium. Use has_media=True for image/video questions; they can be any type."
        },
        "has_media": {
          "description": "True if the question message included an image/video/audio (detected via 'image omitted' / 'video omitted' in the chat export). Remains True even when media[] is null — it means the file exists in the original chat but has not yet been extracted.",
          "title": "Has Media",
          "type": "boolean"
        },
        "media": {
          "anyOf": [
            {
              "items": {
                "$ref": "#/$defs/MediaAttachment"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Actual media attachments, populated when files are extracted from a WhatsApp backup. Null when unavailable (e.g. plain .txt export). has_media=True with media=null means: file exists but not yet extracted.",
          "title": "Media"
        },
        "topic": {
          "anyOf": [
            {
              "$ref": "#/$defs/TopicCategory"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Topic category. Null if not yet classified. Best assigned via LLM."
        },
        "tags": {
          "description": "Free-form tags for fine-grained categorisation (e.g. ['India', 'architecture', 'colonial'])",
          "items": {
            "type": "string"
          },
          "title": "Tags",
          "type": "array"
        }
      },
      "required": [
        "timestamp",
        "text",
        "asker",
        "type",
        "has_media"
      ],
      "title": "Question",
      "type": "object"
    },
    "QuestionType": {
      "enum": [
        "factual",
        "connect",
        "identify",
        "fill_in_blank",
        "multi_part",
        "unknown"
      ],
      "title": "QuestionType",
      "type": "string"
    },
    "Reaction": {
      "properties": {
        "message_timestamp": {
          "description": "Timestamp of the reacted-to message. FK into question.timestamp (question itself) or discussion[].timestamp.",
          "format": "date-time",
          "title": "Message Timestamp",
          "type": "string"
        },
        "username": {
          "description": "Who reacted",
          "title": "Username",
          "type": "string"
        },
        "emoji": {
          "description": "The reaction emoji (e.g. '✅', '👍', '❤️', '😂')",
          "title": "Emoji",
          "type": "string"
        },
        "reaction_timestamp": {
          "description": "When the reaction was placed",
          "format": "date-time",
          "title": "Reaction Timestamp",
          "type": "string"
        }
      },
      "required": [
        "message_timestamp",
        "username",
        "emoji",
        "reaction_timestamp"
      ],
      "title": "Reaction",
      "type": "object"
    },
    "Score": {
      "properties": {
        "username": {
          "description": "Username of the participant",
          "title": "Username",
          "type": "string"
        },
        "score": {
          "description": "Score at this point in the session",
          "title": "Score",
          "type": "integer"
        }
      },
      "required": [
        "username",
        "score"
      ],
      "title": "Score",
      "type": "object"
    },
    "Session": {
      "properties": {
        "id": {
          "description": "Session identifier (e.g. date + quizmaster slug: '2026-03-16-pratik')",
          "title": "Id",
          "type": "string"
        },
        "quizmaster": {
          "description": "Username of the session host",
          "title": "Quizmaster",
          "type": "string"
        },
        "question_number": {
          "description": "Position of this question within the session (1-based)",
          "minimum": 1,
          "title": "Question Number",
          "type": "integer"
        },
        "theme": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Session theme if announced (e.g. 'Hollywood Movies', 'Bollywood')",
          "title": "Theme"
        }
      },
      "required": [
        "id",
        "quizmaster",
        "question_number"
      ],
      "title": "Session",
      "type": "object"
    },
    "Source": {
      "properties": {
        "file": {
          "description": "Source daily chat file (e.g. 'chat_2025-09-23.txt')",
          "title": "File",
          "type": "string"
        },
        "pair_index": {
          "description": "Pair number within the source file (1-based)",
          "minimum": 1,
          "title": "Pair Index",
          "type": "integer"
        }
      },
      "required": [
        "file",
        "pair_index"
      ],
      "title": "Source",
      "type": "object"
    },
    "Stats": {
      "properties": {
        "wrong_attempts": {
          "description": "Number of incorrect attempts before the correct answer",
          "minimum": 0,
          "title": "Wrong Attempts",
          "type": "integer"
        },
        "hints_given": {
          "description": "Number of hints/nudges the asker gave",
          "minimum": 0,
          "title": "Hints Given",
          "type": "integer"
        },
        "time_to_answer_seconds": {
          "anyOf": [
            {
              "minimum": 0,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Seconds from question timestamp to first correct answer. Null if unanswered.",
          "title": "Time To Answer Seconds"
        },
        "unique_participants": {
          "anyOf": [
            {
              "minimum": 1,
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Number of distinct users who attempted an answer",
          "title": "Unique Participants"
        },
        "difficulty": {
          "anyOf": [
            {
              "$ref": "#/$defs/Difficulty"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Heuristic: easy=0 wrong attempts; medium=1–3; hard=4+. Or LLM-assigned."
        }
      },
      "required": [
        "wrong_attempts",
        "hints_given"
      ],
      "title": "Stats",
      "type": "object"
    },
    "TopicCategory": {
      "enum": [
        "history",
        "science",
        "literature",
        "technology",
        "sports",
        "geography",
        "entertainment",
        "food_drink",
        "art_culture",
        "business",
        "general"
      ],
      "title": "TopicCategory",
      "type": "string"
    }
  },
  "description": "A single extracted Q&A pair from the KVizzing WhatsApp group.",
  "properties": {
    "id": {
      "description": "Unique identifier. Format: YYYY-MM-DD-NNN (e.g. '2025-09-23-001')",
      "examples": [
        "2025-09-23-001"
      ],
      "pattern": "^\d{4}-\d{2}-\d{2}-\d+$",
      "title": "Id",
      "type": "string"
    },
    "date": {
      "description": "Date the question was posted (YYYY-MM-DD)",
      "format": "date",
      "title": "Date",
      "type": "string"
    },
    "question": {
      "$ref": "#/$defs/Question"
    },
    "answer": {
      "$ref": "#/$defs/Answer"
    },
    "discussion": {
      "description": "Ordered list of all relevant messages in the Q&A thread",
      "items": {
        "$ref": "#/$defs/DiscussionEntry"
      },
      "title": "Discussion",
      "type": "array"
    },
    "stats": {
      "$ref": "#/$defs/Stats"
    },
    "extraction_confidence": {
      "$ref": "#/$defs/ExtractionConfidence",
      "description": "Confidence that this is a genuine Q&A pair with a known answer"
    },
    "source": {
      "$ref": "#/$defs/Source"
    },
    "session": {
      "anyOf": [
        {
          "$ref": "#/$defs/Session"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Null for ad-hoc questions; populated for QM-hosted quiz sessions"
    },
    "scores_after": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/$defs/Score"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Scores announced by the quizmaster immediately after this question, if present. Null if no score announcement followed this question. Only populated for session questions — never for ad-hoc questions.",
      "title": "Scores After"
    },
    "reactions": {
      "anyOf": [
        {
          "items": {
            "$ref": "#/$defs/Reaction"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Optional enrichment from WhatsApp SQLite DB (iOS: ChatStorage.sqlite; Android: msgstore.db). Null when unavailable.",
      "title": "Reactions"
    },
    "highlights": {
      "anyOf": [
        {
          "$ref": "#/$defs/Highlights"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Optional enrichment derived from reactions[]. Null when reactions unavailable."
    }
  },
  "required": [
    "id",
    "date",
    "question",
    "answer",
    "discussion",
    "stats",
    "extraction_confidence",
    "source"
  ],
  "title": "KVizzingQuestion",
  "type": "object"
}
```
<!-- END:schema.json -->

---

## Sample Instances

<!-- BEGIN:examples.json -->
### 1. Factual question (single solver, confirmed)

```json
{
  "id": "2025-09-23-003",
  "date": "2025-09-23",
  "question": {
    "timestamp": "2025-09-23T14:49:49",
    "text": "Although there is a patent issued in 1938 to John Jordent for an improved version of this invention, no one knows who the very first inventor is, since the original patent was lost in a fire in the US Patent Office in 1936. We will never know the inventor of which life saving invention?",
    "asker": "Aditi Bapat",
    "type": "factual",
    "has_media": false,
    "topic": "history",
    "tags": [
      "patents",
      "USA",
      "inventions"
    ]
  },
  "answer": {
    "text": "Fire Hydrant",
    "solver": "Lzafeer Ahmad B F",
    "timestamp": "2025-09-23T14:51:49",
    "confirmed": true,
    "confirmation_text": "Bingo",
    "is_collaborative": false,
    "parts": null
  },
  "discussion": [
    {
      "timestamp": "2025-09-23T14:50:20",
      "username": "Shubham",
      "text": "CPR?",
      "role": "attempt",
      "is_correct": false
    },
    {
      "timestamp": "2025-09-23T14:50:43",
      "username": "Aditi Bapat",
      "text": "Not quite. Some hints in the question. 🙊",
      "role": "hint",
      "is_correct": null
    },
    {
      "timestamp": "2025-09-23T14:51:03",
      "username": "Akshay",
      "text": "Extinguisher 🧯",
      "role": "attempt",
      "is_correct": false
    },
    {
      "timestamp": "2025-09-23T14:51:13",
      "username": "Aditi Bapat",
      "text": "Very close",
      "role": "hint",
      "is_correct": null
    },
    {
      "timestamp": "2025-09-23T14:51:49",
      "username": "Lzafeer Ahmad B F",
      "text": "Fire Hydrant",
      "role": "attempt",
      "is_correct": true
    },
    {
      "timestamp": "2025-09-23T14:52:01",
      "username": "Aditi Bapat",
      "text": "Bingo",
      "role": "confirmation",
      "is_correct": null
    }
  ],
  "stats": {
    "wrong_attempts": 2,
    "hints_given": 2,
    "time_to_answer_seconds": 120,
    "unique_participants": 3,
    "difficulty": "medium"
  },
  "session": null,
  "extraction_confidence": "high",
  "reactions": [
    {
      "message_timestamp": "2025-09-23T14:49:49",
      "username": "Akshay",
      "emoji": "❤️",
      "reaction_timestamp": "2025-09-23T14:52:10"
    },
    {
      "message_timestamp": "2025-09-23T14:49:49",
      "username": "Pavan Pamidimarri",
      "emoji": "😂",
      "reaction_timestamp": "2025-09-23T14:52:30"
    },
    {
      "message_timestamp": "2025-09-23T14:49:49",
      "username": "Khandoba",
      "emoji": "😂",
      "reaction_timestamp": "2025-09-23T14:52:45"
    },
    {
      "message_timestamp": "2025-09-23T14:51:49",
      "username": "Aditi Bapat",
      "emoji": "✅",
      "reaction_timestamp": "2025-09-23T14:52:05"
    }
  ],
  "highlights": {
    "reaction_counts": {
      "❤️": 1,
      "😂": 2,
      "✅": 1
    },
    "total_reactions": 4,
    "categories": [
      "funny",
      "crowd_favourite"
    ]
  },
  "source": {
    "file": "chat_2025-09-23.txt",
    "pair_index": 3
  }
}
```

### 2. Multi-part identify question (collaborative)

```json
{
  "id": "2026-03-16-001",
  "date": "2026-03-16",
  "question": {
    "timestamp": "2026-03-16T03:49:23",
    "text": "Q. X was born in Taiwan and immigrated to the United States... Id X, company Y, and Z.",
    "asker": "Kartikey Pradhan",
    "type": "multi_part",
    "has_media": false,
    "topic": "technology",
    "tags": [
      "CEO",
      "semiconductors",
      "AI",
      "AMD",
      "Nvidia"
    ]
  },
  "answer": {
    "text": "X = Lisa Su, Y = AMD, Z = Jensen Huang",
    "solver": "Saumay",
    "timestamp": "2026-03-16T03:55:33",
    "confirmed": true,
    "confirmation_text": "Lisa Su is X, AMD is Y, and Jensen Huang, her mamaji, is Z",
    "is_collaborative": false,
    "parts": [
      {
        "label": "X",
        "text": "Lisa Su",
        "solver": "Saumay"
      },
      {
        "label": "Y",
        "text": "AMD",
        "solver": "Saumay"
      },
      {
        "label": "Z",
        "text": "Jensen Huang",
        "solver": "Saumay"
      }
    ]
  },
  "discussion": [
    {
      "timestamp": "2026-03-16T03:54:04",
      "username": "Saumay",
      "text": "Jensen..",
      "role": "attempt",
      "is_correct": false
    },
    {
      "timestamp": "2026-03-16T03:54:06",
      "username": "Saumay",
      "text": "Nvidia",
      "role": "attempt",
      "is_correct": false
    },
    {
      "timestamp": "2026-03-16T03:54:22",
      "username": "Saumay",
      "text": "AMD?",
      "role": "attempt",
      "is_correct": false
    },
    {
      "timestamp": "2026-03-16T03:54:42",
      "username": "Kartikey Pradhan",
      "text": "which letter?",
      "role": "hint",
      "is_correct": null
    },
    {
      "timestamp": "2026-03-16T03:55:03",
      "username": "Saumay",
      "text": "Z",
      "role": "attempt",
      "is_correct": false
    },
    {
      "timestamp": "2026-03-16T03:55:19",
      "username": "Kartikey Pradhan",
      "text": "good, that's what I wanted 😀",
      "role": "hint",
      "is_correct": null
    },
    {
      "timestamp": "2026-03-16T03:55:33",
      "username": "Saumay",
      "text": "Lisa is X",
      "role": "attempt",
      "is_correct": true
    },
    {
      "timestamp": "2026-03-16T03:56:02",
      "username": "Kartikey Pradhan",
      "text": "Lisa Su is X, AMD is Y, and Jensen Huang, her mamaji, is Z",
      "role": "confirmation",
      "is_correct": null
    }
  ],
  "stats": {
    "wrong_attempts": 4,
    "hints_given": 2,
    "time_to_answer_seconds": 370,
    "unique_participants": 1,
    "difficulty": "hard"
  },
  "session": null,
  "extraction_confidence": "high",
  "reactions": null,
  "highlights": null,
  "source": {
    "file": "chat_2026-03-16.txt",
    "pair_index": 1
  }
}
```

### 3. Visual question (structured quiz session)

```json
{
  "id": "2026-03-16-007",
  "date": "2026-03-16",
  "question": {
    "timestamp": "2026-03-16T07:18:47",
    "text": "[image: movie poster visual quiz]",
    "asker": "pratik.s.chandarana",
    "type": "factual",
    "has_media": true,
    "topic": "entertainment",
    "tags": [
      "movies",
      "Hollywood",
      "poster quiz"
    ]
  },
  "answer": {
    "text": "Rush Hour 2",
    "solver": "Chinmay Mehta",
    "timestamp": "2026-03-16T07:19:07",
    "confirmed": true,
    "confirmation_text": "Rush Hour 2 is correct; Chinmay with the correct answer",
    "is_collaborative": false,
    "parts": null
  },
  "discussion": [
    {
      "timestamp": "2026-03-16T07:18:57",
      "username": "Lzafeer Ahmad B F",
      "text": "Oceans 11",
      "role": "attempt",
      "is_correct": false
    },
    {
      "timestamp": "2026-03-16T07:18:57",
      "username": "Radhika",
      "text": "Hangover?",
      "role": "attempt",
      "is_correct": false
    },
    {
      "timestamp": "2026-03-16T07:18:58",
      "username": "Gautam Aswani",
      "text": "21",
      "role": "attempt",
      "is_correct": false
    },
    {
      "timestamp": "2026-03-16T07:19:07",
      "username": "Chinmay Mehta",
      "text": "Rush hour?",
      "role": "attempt",
      "is_correct": true
    },
    {
      "timestamp": "2026-03-16T07:19:35",
      "username": "Nikunj",
      "text": "Rounders?",
      "role": "attempt",
      "is_correct": false
    },
    {
      "timestamp": "2026-03-16T07:19:59",
      "username": "pratik.s.chandarana",
      "text": "Rush Hour 2 is correct; Chinmay with the correct answer",
      "role": "confirmation",
      "is_correct": null
    }
  ],
  "stats": {
    "wrong_attempts": 3,
    "hints_given": 0,
    "time_to_answer_seconds": 20,
    "unique_participants": 5,
    "difficulty": "medium"
  },
  "session": {
    "id": "2026-03-16-pratik",
    "quizmaster": "pratik.s.chandarana",
    "question_number": 7,
    "theme": "Hollywood Movies"
  },
  "extraction_confidence": "high",
  "reactions": [
    {
      "message_timestamp": "2026-03-16T07:19:07",
      "username": "Nikunj",
      "emoji": "✅",
      "reaction_timestamp": "2026-03-16T07:20:05"
    },
    {
      "message_timestamp": "2026-03-16T07:19:07",
      "username": "Radhika",
      "emoji": "✅",
      "reaction_timestamp": "2026-03-16T07:20:08"
    },
    {
      "message_timestamp": "2026-03-16T07:19:35",
      "username": "Nikunj",
      "emoji": "😂",
      "reaction_timestamp": "2026-03-16T07:20:10"
    }
  ],
  "highlights": {
    "reaction_counts": {
      "✅": 2,
      "😂": 1
    },
    "total_reactions": 3,
    "categories": [
      "confirmed_correct",
      "funny"
    ]
  },
  "source": {
    "file": "chat_2026-03-16.txt",
    "pair_index": 7
  }
}
```

### 4. Connect question (collaborative solve)

```json
{
  "id": "2026-03-16-003",
  "date": "2026-03-16",
  "question": {
    "timestamp": "2026-03-16T06:14:40",
    "text": "Flash Q.
Connect:
Carolyn Keene
Franklin Dixon
Roy Rockwood
Victor Appleton
Margaret Penrose",
    "asker": "Sidhesh K K",
    "type": "connect",
    "has_media": false,
    "topic": "literature",
    "tags": [
      "pseudonyms",
      "publishing",
      "Hardy Boys",
      "Nancy Drew"
    ]
  },
  "answer": {
    "text": "Pseudonyms / house names owned by the Stratemeyer Syndicate — multiple ghostwriters published under each name",
    "solver": null,
    "timestamp": "2026-03-16T06:18:00",
    "confirmed": true,
    "confirmation_text": "Together you folks have cracked the funda... these are pennames of authors given by the same syndicate",
    "is_collaborative": true,
    "parts": null
  },
  "discussion": [
    {
      "timestamp": "2026-03-16T06:15:46",
      "username": "Chaitanya Malhotra",
      "text": "Pseudonym authors?",
      "role": "attempt",
      "is_correct": false
    },
    {
      "timestamp": "2026-03-16T06:15:47",
      "username": "Nikunj",
      "text": "Franklin Dixon is Hardy boys right?",
      "role": "attempt",
      "is_correct": false
    },
    {
      "timestamp": "2026-03-16T06:16:15",
      "username": "Sidhesh K K",
      "text": "Yes... but there's a deeper funda for these names",
      "role": "hint",
      "is_correct": null
    },
    {
      "timestamp": "2026-03-16T06:16:42",
      "username": "Lzafeer Ahmad B F",
      "text": "Wasn't pen name picked by publisher so that whoever wrote was published under that author name",
      "role": "attempt",
      "is_correct": false
    },
    {
      "timestamp": "2026-03-16T06:16:55",
      "username": "Sidhesh K K",
      "text": "Correct",
      "role": "hint",
      "is_correct": null
    },
    {
      "timestamp": "2026-03-16T06:18:00",
      "username": "Sidhesh K K",
      "text": "Together you folks have cracked the funda... these are pennames of authors given by the same syndicate",
      "role": "confirmation",
      "is_correct": null
    }
  ],
  "stats": {
    "wrong_attempts": 3,
    "hints_given": 2,
    "time_to_answer_seconds": 200,
    "unique_participants": 3,
    "difficulty": "medium"
  },
  "session": null,
  "extraction_confidence": "high",
  "reactions": [
    {
      "message_timestamp": "2026-03-16T06:14:40",
      "username": "Chaitanya Malhotra",
      "emoji": "❤️",
      "reaction_timestamp": "2026-03-16T06:18:20"
    },
    {
      "message_timestamp": "2026-03-16T06:14:40",
      "username": "Nikunj",
      "emoji": "❤️",
      "reaction_timestamp": "2026-03-16T06:18:25"
    },
    {
      "message_timestamp": "2026-03-16T06:14:40",
      "username": "Lzafeer Ahmad B F",
      "emoji": "🔥",
      "reaction_timestamp": "2026-03-16T06:18:30"
    },
    {
      "message_timestamp": "2026-03-16T06:18:00",
      "username": "Chaitanya Malhotra",
      "emoji": "😂",
      "reaction_timestamp": "2026-03-16T06:18:40"
    }
  ],
  "highlights": {
    "reaction_counts": {
      "❤️": 2,
      "🔥": 1,
      "😂": 1
    },
    "total_reactions": 4,
    "categories": [
      "crowd_favourite",
      "spicy",
      "funny"
    ]
  },
  "source": {
    "file": "chat_2026-03-16.txt",
    "pair_index": 3
  }
}
```
<!-- END:examples.json -->

---

## Output File Format

Questions should be stored as:
- **`data/questions.json`** — array of all question objects (primary source of truth)
- **`data/questions_by_date/YYYY-MM-DD.json`** — per-day arrays (for efficient date-range queries)

The `questions.json` array is sorted by `question.timestamp` ascending.
