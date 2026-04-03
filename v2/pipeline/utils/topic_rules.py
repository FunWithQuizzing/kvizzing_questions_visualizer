"""
Rule-based topic assignment for KVizzingQuestion objects.

Used by:
  - pipeline.py assign-topics  (retroactive batch fix)
  - stage4_enrich (future: as LLM fallback)
"""

from __future__ import annotations

from collections import Counter

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "schema"))
from schema import KVizzingQuestion, TopicCategory


# ── Tag → topic mapping ───────────────────────────────────────────────────────

TAG_TOPIC: dict[str, str] = {
    # Geography
    "flags": "geography", "airports": "geography", "iata": "geography",
    "cities": "geography", "islands": "geography", "locations": "geography",
    "canada": "geography", "usa": "geography", "japan": "geography",
    "pakistan": "geography", "india": "geography", "bombay": "geography",
    "madras": "geography", "sikkim": "geography", "balochistan": "geography",
    "travancore": "geography", "punjab": "geography", "rivers": "geography",
    "mountains": "geography", "capitals": "geography", "continents": "geography",
    "oceans": "geography", "countries": "geography", "states": "geography",
    "aviation": "geography",
    # History
    "battle": "history", "ww2": "history", "world leaders": "history",
    "british": "history", "british india": "history",
    "east india company": "history", "mughal": "history",
    "maratha": "history", "ahom": "history", "rig veda": "history",
    "vijayanagar": "history", "ancient": "history",
    "lords": "history", "dalit": "history", "constitution": "history",
    "politics": "politics", "empire": "history", "colonialism": "history",
    "revolution": "history", "war": "history", "independence": "history",
    "medieval": "history", "dynasty": "history", "kings": "history",
    "queens": "history", "treaties": "history", "coins": "history",
    "cooch behar": "history",
    # Science
    "astronomy": "science", "women in science": "science",
    "mathematics": "science", "physics": "science", "nasa": "science",
    "space": "science", "science": "science", "medicine": "science",
    "ivf": "science", "eclipse": "science", "astronauts": "science",
    "time dilation": "science", "weather": "science", "biology": "science",
    "chemistry": "science", "genetics": "science", "elements": "science",
    "periodic table": "science", "nobel": "science", "climate": "science",
    "semiconductor": "science", "quantum": "science", "computer science": "science",
    "fields medal": "science",
    # Technology
    "cars": "technology", "porsche": "technology", "tesla": "technology",
    "lotus": "technology", "brands": "technology", "logo": "technology",
    "ai": "technology", "technology": "technology", "software": "technology",
    "internet": "technology", "computers": "technology", "robots": "technology",
    "electric vehicles": "technology", "satellites": "technology",
    "bell labs": "technology", "programming": "technology",
    # Entertainment
    "bollywood": "entertainment", "films": "entertainment", "actors": "entertainment",
    "hollywood": "entertainment", "disney": "entertainment",
    "marvel": "entertainment", "comics": "entertainment", "tv": "entertainment",
    "music": "entertainment", "lyrics": "entertainment", "rock": "entertainment",
    "nirvana": "entertainment", "pop": "entertainment", "albums": "entertainment",
    "directors": "entertainment", "oscars": "entertainment",
    "grammy": "entertainment", "pulitzer": "entertainment",
    "streaming": "entertainment", "badly explained": "entertainment",
    # Sports
    "cricket": "sports", "ipl": "sports", "records": "sports",
    "football": "sports", "tennis": "sports", "olympics": "sports",
    "athletes": "sports", "chess": "sports", "formula 1": "sports",
    "f1": "sports", "baseball": "sports", "basketball": "sports",
    "nfl": "sports",
    # Literature
    "books": "literature", "novels": "literature", "authors": "literature",
    "poetry": "literature", "shakespeare": "literature",
    "booker": "literature", "fiction": "literature",
    # Etymology
    "etymology": "etymology", "language": "etymology", "puns": "etymology",
    "hindi": "etymology", "tamil": "etymology", "words": "etymology",
    "latin": "etymology", "slang": "etymology", "wordplay": "etymology",
    "foreign language": "etymology", "sanskrit": "etymology",
    "arabic": "etymology",
    # Art & Culture
    "painting": "art_culture", "art": "art_culture",
    "sculpture": "art_culture", "architecture": "art_culture",
    "culture": "art_culture", "dance": "art_culture", "theatre": "art_culture",
    # Food & Drink
    "food": "food_drink", "cuisine": "food_drink", "drinks": "food_drink",
    "cocktails": "food_drink", "restaurants": "food_drink",
    "chefs": "food_drink", "coffee": "food_drink",
    # Business
    "business": "business", "economics": "business",
    "stock market": "business", "startups": "business",
    "ceo": "business", "companies": "business", "trade": "business",
    # Mythology
    "mythology": "mythology", "greek mythology": "mythology",
    "hindu mythology": "mythology", "roman mythology": "mythology",
    "gods": "mythology", "legends": "mythology", "folklore": "mythology",
    "epics": "mythology", "ramayana": "mythology", "mahabharata": "mythology",
    # Geology
    "geology": "geology", "minerals": "geology", "rocks": "geology",
    "volcanoes": "geology", "earthquakes": "geology", "craters": "geology",
    "fossils": "geology", "tectonic": "geology",
    # Meme
    "meme": "meme", "memes": "meme", "pun": "meme", "puns": "meme",
    "joke": "meme", "jokes": "meme", "humor": "meme",
    # Politics
    "election": "politics", "elections": "politics", "parliament": "politics",
    "democracy": "politics", "government": "politics", "legislation": "politics",
    "prime minister": "politics", "president": "politics",
    "geopolitics": "politics", "diplomacy": "politics", "sanctions": "politics",
    "united nations": "politics", "nato": "politics", "world leaders": "politics",
}


# ── Keyword → topic: scan question + answer text ──────────────────────────────

KEYWORD_TOPIC: list[tuple[list[str], str]] = [
    (["world war", "ww2", "ww1", "cold war", "revolution", "treaty",
      "empire", "dynasty", "colonial", "british raj", "mughal", "maratha",
      "east india company", "independence", "partition", "cooch behar",
      "princely state"], "history"),
    (["planet", "galaxy", "black hole", "nasa", "astronaut", "orbit",
      "telescope", "eclipse", "comet", "quantum", "wave function",
      "taylor series", "primality", "fields medal", "semiconductor",
      "bell labs", "periodic table", "potassium", "sodium", "chemistry",
      "physicist", "chemist", "biologist", "nobel prize in",
      "indian chemist", "bengali chemist", "mahalanobis", "royal society",
      "frequency-hopping", "frequency hopping", "lok sabha elections",
      "mit professor", "princeton", "computer scientist", "algorithm"], "science"),
    (["flag of", "capital of", "country ", "continent", "ocean", "river ",
      "mountain", "airport", "iata", "timezone", "map of",
      "sommaroy", "norwegian island", "drives on the right",
      "region of india", "drives on the left"], "geography"),
    (["bollywood", "film ", "movie ", "actor ", "actress", "director ",
      "oscar", "grammy", "pulitzer", "song ", "album ", "singer ",
      "hindi movie", "guinness world record", "id the movie",
      "id this movie", "id the song", "padman", "delhi belly",
      "munnabhai", "thappad", "dum laga"], "entertainment"),
    (["cricket", "ipl", "football", "tennis", "olympics", "formula 1",
      "nfl player", "world cup", "championship", "tournament",
      "athlete", "sports"], "sports"),
    (["novel ", "book ", "author ", "poet ", "poem ",
      "ralph waldo emerson", "literature", "booker prize"], "literature"),
    (["brand ", "company ", "startup", "ceo ", "stock ", "economy",
      "trade ", "gdp", "economist ", "chaguan"], "business"),
    (["arabic root", "latin word", "etymology", "language ",
      "foreign language", "portuguese", "polish", "korean", "thai",
      "sanskrit", "kshudhavardhak", "derived from",
      "word originally", "ety question", "pun "], "etymology"),
    (["painting ", "sculpture", "architecture", "museum",
      "gallery", "artwork", "dance ", "theatre"], "art_culture"),
    (["recipe", "cuisine", "food ", "drink ", "wine ", "beer ",
      "coffee per capita", "cocktail", "chef ", "restaurant"], "food_drink"),
    (["car ", "automobile", "electric vehicle", "software", "internet",
      "ai ", "artificial intelligence", "robot", "computer",
      "smartphone", "tech company"], "technology"),
    (["myth", "mythology", "ramayana", "mahabharata", "greek god",
      "roman god", "hindu god", "legend ", "folklore", "fable",
      "nastika", "indian philosophy", "golden pylon", "palm tree",
      "tortoise and hare", "hare and tortoise"], "mythology"),
    (["crater", "volcano", "earthquake", "mineral", "fossil",
      "tectonic", "geological", "geology", "rock formation",
      "hildebrand", "chicxulub"], "geology"),
    (["prime minister", "president ", "election", "parliament",
      "political party", "senator", "congressman", "legislation",
      "democracy", "dictator", "regime", "cabinet minister",
      "lok sabha", "rajya sabha", "congress party", "bjp",
      "geopolitic", "sanctions", "diplomacy", "diplomat",
      "united nations", "nato", "g7", "g20", "summit",
      "foreign policy", "ambassador", "treaty", "bilateral",
      "trade war", "netanyahu", "bibisitters"], "politics"),
    (["complete the joke", "caption this", "complete the pun",
      "math pj", "math joke", "puntastic", "nerdy joke",
      "complete the venn diagram", "halloween theme",
      "therapy session", "guess who?", "name the cousin",
      "for the nerds", "headache with pictures"], "meme"),
]


# ── Per-question text overrides ───────────────────────────────────────────────

TEXT_OVERRIDES: list[tuple[str, str, str | None]] = [
    ("symmetric and antisymmetric wave functions", "science", None),
    ("taylor series approximation for the inverse tangent", "science", "etymology"),
    ("bengali chemist", "science", "history"),
    ("father of indian chemistry", "science", "history"),
    ("semiconductor junctions to detect radio waves", "science", "technology"),
    ("indian american computer scientist", "technology", "science"),
    ("former president of bell labs", "technology", "science"),
    ("aks primality test", "science", "technology"),
    ("contested for lok sabha elections in 1951", "science", "history"),
    ("cambridge-educated indian scientist", "science", "history"),
    ("prasanta chandra mahalanobis", "science", "history"),
    ("fellow of the royal society", "science", None),
    ("fields medal", "science", None),
    ("hildebrand spent years", "geology", "science"),
    ("frequency-hopping system during w", "science", "history"),
    ("assistant math professor at mit", "science", "sports"),
    ("nastika traditions of indian philosophy", "history", "mythology"),
    ("arabic root word meaning", "etymology", None),
    ("golden pylon resembling a palm tree", "mythology", "history"),
    ("chemical element sounds like a latin word", "science", "etymology"),
    ("first artist from his genre to win the pulitzer", "entertainment", None),
    ("scientist and household name", "science", None),
    ("2003 hindi movie", "entertainment", None),
    ("id the movie", "entertainment", None),
    ("id the song/movie", "entertainment", None),
    ("id this movie", "entertainment", None),
    ("cooch behar flag", "history", "geography"),
    ("this historical word used to refer to a region", "geography", "etymology"),
    ("majority of the world drives on the right", "geography", None),
    ("norwegian island of sommaroy", "geography", None),
    ("children's toy", "general", None),
    ("board originally placed in front of carriages", "general", "etymology"),
    ("taking a leaf out of akshay's book", "geography", None),
    ("competitive sports were a total non-starter", "sports", None),
    ("blanked out educational institute", "entertainment", None),
    ("what do the numbers represent in this chart", "geography", None),
    ("foreign languages", "etymology", None),
    ("foreign language", "etymology", None),
    ("onde está minha mente", "etymology", None),
    ("오징어 게임", "entertainment", "etymology"),
    ("whats this map representing", "geography", None),
    ("what's this map", "geography", None),
    ("what metal were these coins made of", "history", None),
    ("kshudhavardhak", "etymology", None),
    ("ety question", "etymology", None),
    ("ralph waldo emerson", "literature", None),
    ("economist has a weekly column", "business", None),
    ("chaguan", "business", "geography"),
    ("coffee per capita", "food_drink", "geography"),
    ("tortoise", "mythology", None),
    ("ambled along while its opponent", "mythology", None),
    ("two belligerent factions", "history", None),
    ("inaugural quiz time", "general", None),
    ("what's the theme", "general", None),
    ("farzi time", "etymology", None),
    ("20 rupee coin", "history", None),
    ("urban legend", "general", None),
    # ── Meme / joke questions ──
    ("complete the joke", "meme", None),
    ("complete the venn diagram", "meme", None),
    ("complete this math pj", "meme", "science"),
    ("caption this", "meme", None),
    ("pun on the animal", "meme", None),
    ("puntastic", "meme", None),
    ("math pj", "meme", "science"),
    ("last pj promise", "meme", "science"),
    ("math joke", "meme", "science"),
    ("nerdy joke", "meme", None),
    ("for the \"nerds\"", "meme", "science"),
    ("for the nerds", "meme", "science"),
    ("lighten it up", "meme", None),
    ("diarrhoea medication", "meme", "sports"),
    ("idaho montoya", "meme", "entertainment"),
    ("id the spider", "meme", None),
    ("guess who?", "meme", None),
    ("halloween theme", "meme", None),
    ("therapy session", "meme", None),
    ("polka-geist", "meme", None),
    ("sticking to the halloween", "meme", None),
    ("whose therapy session", "meme", None),
    ("blas-femurs", "meme", None),
    ("social medea", "meme", "mythology"),
    ("good day biscuits", "meme", "food_drink"),
    ("legalize", "meme", "food_drink"),
    ("brush with death", "meme", None),
    ("goth ness", "meme", None),
    ("dmitri finds out", "meme", None),
    ("blanked out phrase in this meme", "meme", None),
    ("toy yoda", "meme", "entertainment"),
    ("1/cos(c)", "meme", "science"),
    ("derivative of kinetic energy", "meme", "science"),
    ("integral of (1/cabin)", "meme", "science"),
    ("a penny for your thought", "meme", None),
    ("name the cousin", "meme", None),
    ("colander", "meme", None),
    ("headache with pictures", "meme", None),
    ("don't kia telluride", "meme", None),
    # ── Geography re-assignments ──
    ("what's this map", "geography", None),
    ("whats this map", "geography", None),
    ("number of time zones per country", "geography", None),
    ("birthright citizenship", "geography", "history"),
    ("map showing countries", "geography", None),
    ("world map showing", "geography", None),
    ("anagram city names", "geography", None),
    ("airport code", "geography", None),
    ("iata code", "geography", None),
    ("which airport", "geography", None),
    ("gaya gay thing", "geography", None),
    ("sioux gateway", "geography", None),
    # ── Etymology re-assignments ──
    ("acronym expansion", "etymology", "technology"),
    ("anglicized version", "etymology", None),
    ("john doe", "etymology", None),
    ("jane doe", "etymology", None),
    ("farzi time", "etymology", "sports"),
    # ── Entertainment re-assignments ──
    ("best-selling singer", "entertainment", None),
    ("id the film", "entertainment", None),
    ("id the movie", "entertainment", None),
    ("ask the sexpert", "entertainment", None),
    ("the weeknd and wednesday", "entertainment", None),
    # ── History re-assignments ──
    ("tiananmen square", "history", None),
    ("tank man", "history", None),
    ("mary roy", "history", None),
    ("aggrieved by being denied a right", "history", None),
    ("prime minister benjamin netanyahu", "politics", None),
    ("bibisitters", "politics", None),
    ("20 rupee coin", "history", None),
    # ── Business re-assignments ──
    ("flying spaghetti monster", "business", None),  # parody religion / social commentary
    ("pastafarian", "business", None),
    ("administratium", "meme", "science"),
    ("bureaucratium", "meme", "science"),
    ("ceo of starbucks", "business", None),
    ("lakshman narasimhan", "business", None),
    ("project nobel", "business", None),
    ("ashoka university", "business", None),
    # ── Science re-assignments ──
    ("ig nobel", "science", None),
    ("pi they have recited", "science", None),
    ("digits of pi", "science", None),
    # ── Sports re-assignments ──
    ("2026 fifa world cup", "sports", None),
    ("trionda", "sports", None),
    ("marble races", "sports", "entertainment"),
    # ── Literature re-assignments ──
    ("chris mccandless", "literature", "geography"),
    ("into the wild", "literature", "geography"),
    # ── Art & Culture re-assignments ──
    ("connect.*watches", "art_culture", "business"),
    ("famous watches", "art_culture", "business"),
    ("pasha de cartier", "art_culture", "business"),
    ("audemars piguet", "art_culture", "business"),
    # ── Misc ──
    ("play-doh", "general", "history"),
    ("binary string represents", "meme", "technology"),
    ("acharya balkrishna", "business", None),
    ("patanjali", "business", None),
    ("ajmal", "entertainment", None),
    ("quote from an interview", "entertainment", None),
    ("id the connection", "general", None),
]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _find_override(text: str) -> tuple[str, str | None] | None:
    tl = text.lower()
    for substring, primary, secondary in TEXT_OVERRIDES:
        if substring in tl:
            return primary, secondary
    return None


def _candidate_topics_from_tags(tags: list[str], exclude: str) -> Counter:
    counts: Counter = Counter()
    for tag in tags:
        mapped = TAG_TOPIC.get(tag.lower())
        if mapped and mapped != exclude:
            counts[mapped] += 2
    return counts


def _candidate_topics_from_text(text: str, exclude: str) -> Counter:
    counts: Counter = Counter()
    tl = text.lower()
    for keywords, topic in KEYWORD_TOPIC:
        if topic == exclude:
            continue
        if any(kw in tl for kw in keywords):
            counts[topic] += 1
    return counts


def _best_secondary(tags: list[str], text: str, exclude: str) -> str | None:
    combined: Counter = Counter()
    combined.update(_candidate_topics_from_tags(tags, exclude))
    combined.update(_candidate_topics_from_text(text, exclude))
    if not combined:
        return None
    best, score = combined.most_common(1)[0]
    return best if score >= 2 else None


def _infer_primary(tags: list[str], text: str) -> str | None:
    for keywords, topic in KEYWORD_TOPIC:
        if any(kw in text.lower() for kw in keywords):
            return topic
    tag_counts: Counter = Counter()
    for tag in tags:
        mapped = TAG_TOPIC.get(tag.lower())
        if mapped:
            tag_counts[mapped] += 1
    return tag_counts.most_common(1)[0][0] if tag_counts else None


# ── Public API ────────────────────────────────────────────────────────────────

def assign_topics(q: KVizzingQuestion) -> KVizzingQuestion:
    """
    Assign primary (and optionally secondary) topic to a question using
    rule-based tag + keyword matching. No LLM required.
    Text overrides take precedence; questions already with 2+ topics are skipped.
    """
    tags = q.question.tags or []
    text = (q.question.text or "") + " " + ((q.answer.text or "") if q.answer else "")

    override = _find_override(q.question.text or "")
    if override is not None:
        primary_str, secondary_str = override
        try:
            primary = TopicCategory(primary_str)
        except ValueError:
            primary = TopicCategory.general
        new_topics: list[TopicCategory] = [primary]
        if secondary_str:
            try:
                sec = TopicCategory(secondary_str)
                if sec != primary:
                    new_topics.append(sec)
            except ValueError:
                pass
        return q.model_copy(update={"question": q.question.model_copy(update={"topics": new_topics})})

    if len(q.question.topics) >= 3:
        return q

    if q.question.topics:
        primary = q.question.topics[0]
    else:
        inferred = _infer_primary(tags, text)
        try:
            primary = TopicCategory(inferred) if inferred else TopicCategory.general
        except ValueError:
            primary = TopicCategory.general

    secondary_str = _best_secondary(tags, text, primary.value)
    if secondary_str:
        try:
            secondary = TopicCategory(secondary_str)
            return q.model_copy(update={"question": q.question.model_copy(
                update={"topics": [primary, secondary]}
            )})
        except ValueError:
            pass

    if not q.question.topics or q.question.topics[0] != primary:
        return q.model_copy(update={"question": q.question.model_copy(update={"topics": [primary]})})

    return q
