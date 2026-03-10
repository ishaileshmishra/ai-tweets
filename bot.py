"""
Production-ready X (Twitter) auto-poster for System Design education.

- Generates tweets using OpenAI gpt-4o-mini.
- Posts via Tweepy X API v2 using OAuth 1.0a User Context (required for write).
- Rotates a curated System Design curriculum by day-of-year so consecutive
  posts never repeat the same topic.
- Run daily via GitHub Actions or cron. All secrets read from env.
"""

from __future__ import annotations

import logging
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import tweepy
from dotenv import load_dotenv
from openai import OpenAI, APIError, APIConnectionError, RateLimitError

# --------------------------------------------------------------------------- #
# Setup
# --------------------------------------------------------------------------- #
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ai-tweets")

OPENAI_MODEL = "gpt-4o-mini"
MAX_TWEET_LEN = 280
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds, exponential

REQUIRED_X_KEYS = (
    "X_CONSUMER_KEY",
    "X_CONSUMER_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET",
)


# --------------------------------------------------------------------------- #
# System Design curriculum
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Lesson:
    category: str
    topic: str
    angle: str  # one-sentence teaching angle the LLM should expand on


CURRICULUM: tuple[Lesson, ...] = (
    # ---------- Fundamentals ----------
    Lesson("Fundamentals", "CAP theorem",
           "Under network partition you choose Consistency OR Availability — never both. Most 'AP' systems still favor convergence."),
    Lesson("Fundamentals", "Strong vs eventual consistency",
           "Strong = read sees latest write. Eventual = read may lag. Pick based on user expectation, not engineering taste."),
    Lesson("Fundamentals", "Sharding strategies",
           "Range, hash, and directory-based sharding. Hot keys kill range shards; consistent hashing tames rebalancing."),
    Lesson("Fundamentals", "Replication: leader vs leaderless",
           "Leader-based gives ordering; leaderless (Dynamo-style) gives availability. Quorums (R+W>N) trade latency for safety."),
    Lesson("Fundamentals", "Quorum reads/writes",
           "R + W > N guarantees read sees latest write. Tune R and W for read-heavy vs write-heavy workloads."),
    Lesson("Fundamentals", "Idempotency",
           "Retries are inevitable. Design every write with an idempotency key so duplicates never corrupt state."),
    Lesson("Fundamentals", "Backpressure",
           "If the producer outruns the consumer, you need backpressure — not bigger queues. Bounded queues fail loudly, unbounded queues fail silently."),
    Lesson("Fundamentals", "Latency vs throughput",
           "Throughput is jobs/sec; latency is time per job. Optimizing one usually hurts the other. Know which one your user feels."),

    # ---------- Components ----------
    Lesson("Components", "Load balancer L4 vs L7",
           "L4 routes by IP/port (fast, dumb). L7 routes by path/header (smart, expensive). Use L7 when you need routing logic."),
    Lesson("Components", "API gateway",
           "Gateways centralize auth, rate limiting, and routing — so services stay focused. The trap: gateway becomes a distributed monolith."),
    Lesson("Components", "Message queues vs streams",
           "Queues (SQS, RabbitMQ) drop messages after consume. Streams (Kafka) retain them. Replayability is the differentiator."),
    Lesson("Components", "Cache invalidation",
           "Two hard problems: naming things, cache invalidation. Use TTL + write-through OR cache-aside with explicit busts. Never both."),
    Lesson("Components", "CDN edge caching",
           "Push static assets to the edge. Cache-Control + ETag are not optional — they are the contract between your origin and the world."),
    Lesson("Components", "Reverse proxy",
           "Nginx/Envoy buffer slow clients, terminate TLS, and shield your app from the open internet. One config away from a 10x ops upgrade."),
    Lesson("Components", "Database connection pooling",
           "Postgres dies at ~500 connections. PgBouncer lets 10,000 clients share 100 connections. Pooling is non-negotiable at scale."),
    Lesson("Components", "Search index (Elastic / OpenSearch)",
           "Don't query your OLTP DB with LIKE '%foo%'. Index searchable fields into a real inverted index. Updates are eventually consistent."),

    # ---------- Patterns ----------
    Lesson("Patterns", "CQRS",
           "Split writes (commands) from reads (queries). Different schemas, different scale models. Adds complexity — earn it before adopting."),
    Lesson("Patterns", "Event Sourcing",
           "Store events, derive state. Audit log is free; rebuilds are cheap; debugging is pleasant. Migrations are nightmares."),
    Lesson("Patterns", "Saga pattern",
           "Distributed transactions die in 2026. Sagas chain local txns + compensating actions. Choreography for simple flows, orchestration when steps grow."),
    Lesson("Patterns", "Circuit breaker",
           "When a downstream is failing, stop hammering it. Open the circuit, fail fast, recover gracefully. Cascading failures start where breakers don't."),
    Lesson("Patterns", "Bulkhead",
           "Isolate resource pools so one bad neighbor can't drown the ship. Separate thread pools per dependency = predictable degradation."),
    Lesson("Patterns", "Retry with exponential backoff + jitter",
           "Naïve retries cause thundering herds. Backoff smooths load; jitter desynchronizes clients. Always use both."),
    Lesson("Patterns", "Outbox pattern",
           "Need 'write to DB AND publish event' atomically? Write the event into an outbox table in the same txn, then ship it asynchronously."),
    Lesson("Patterns", "Idempotent consumer",
           "At-least-once delivery is the default in distributed systems. Make consumers idempotent — track processed message IDs."),

    # ---------- Real-world architectures ----------
    Lesson("Real-world", "URL shortener",
           "Generate short keys via base62(counter) or hash. Store in KV. Cache hot keys. The hard part isn't shortening — it's analytics at scale."),
    Lesson("Real-world", "Twitter feed (fan-out on write vs read)",
           "Write fan-out = fast reads, expensive for celebrities. Read fan-out = slow reads, cheap writes. Real systems use a hybrid."),
    Lesson("Real-world", "Ride-sharing dispatch",
           "Geohash drivers into cells. On request, query nearby cells. The matching engine is single-region; everything else can be global."),
    Lesson("Real-world", "Payment system",
           "Idempotency keys on every API call. Double-entry ledger as source of truth. Async settlement, sync authorization. Never trust the network."),
    Lesson("Real-world", "Chat system",
           "WebSockets for online users, push-to-mobile for offline. Messages = events in a partitioned log. Read receipts = eventually consistent."),
    Lesson("Real-world", "Video streaming (HLS/DASH)",
           "Chunk video into 6-10s segments, transcode at multiple bitrates, serve via CDN. Adaptive bitrate happens client-side."),
    Lesson("Real-world", "Rate limiter",
           "Token bucket beats fixed window. Sliding log is precise but expensive. Distributed limiters need a Redis with INCR + EXPIRE."),
    Lesson("Real-world", "Notification system",
           "Producers emit events; a fan-out service routes to email/push/SMS workers. Dedup by event ID. Always make notifications idempotent."),

    # ---------- Trade-offs ----------
    Lesson("Trade-offs", "SQL vs NoSQL",
           "SQL when relations matter and access patterns evolve. NoSQL when access patterns are fixed and scale is the goal. Most teams pick wrong."),
    Lesson("Trade-offs", "Monolith vs microservices",
           "Microservices solve org problems, not tech ones. If your team is <20 engineers, monolith + modules wins on velocity every time."),
    Lesson("Trade-offs", "Push vs pull",
           "Push = low latency, server keeps state. Pull = simple, scales by client count. Long-polling and WebSockets are the practical middle ground."),
    Lesson("Trade-offs", "Sync vs async APIs",
           "Sync is easy to reason about, fragile under load. Async (queue + worker) absorbs spikes but adds complexity. Use async for slow work."),
    Lesson("Trade-offs", "Vertical vs horizontal scaling",
           "Vertical is the cheap, boring win until ~$10k/month. Horizontal needs distributed-systems thinking from day one. Don't horizontal-scale prematurely."),
    Lesson("Trade-offs", "Strong typing vs schema evolution",
           "Strict schemas (protobuf) prevent bad data at ingest. Loose schemas (JSON) let you ship faster. Compatibility rules matter more than the format."),
    Lesson("Trade-offs", "Cache-aside vs write-through",
           "Cache-aside: app manages cache (simple, stale risk). Write-through: cache writes to DB (consistent, slower). Choose based on read/write ratio."),
    Lesson("Trade-offs", "Pessimistic vs optimistic locking",
           "Pessimistic: lock first, work later (safe, contended). Optimistic: work, then version-check (fast, retry on conflict). Use optimistic for read-heavy."),
)


# --------------------------------------------------------------------------- #
# Fallbacks (if LLM is fully unavailable)
# --------------------------------------------------------------------------- #
FALLBACK_TWEETS = (
    "🧵 System Design: idempotency keys are the cheapest insurance you'll ever buy. Every write API should accept one — retries are inevitable. "
    "#SystemDesign #SoftwareEngineering #DevEducation",
    "🧵 System Design: caches don't fail loudly. They fail slowly — wrong data, slowly served. TTL + invalidation is a contract, not a config. "
    "#SystemDesign #SoftwareEngineering #DevEducation",
    "🧵 System Design: most 'we need microservices' decisions are really 'we need module boundaries'. Fix the codebase before you fix the network. "
    "#SystemDesign #SoftwareEngineering #DevEducation",
)


# --------------------------------------------------------------------------- #
# Bot
# --------------------------------------------------------------------------- #
class TwitterBot:
    def __init__(self) -> None:
        # OpenAI
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            raise ValueError("OPENAI_API_KEY is not set")
        self.openai = OpenAI(api_key=openai_key)

        # X / Twitter — OAuth 1.0a User Context is REQUIRED to POST tweets
        # via API v2. tweepy.Client handles v2; pass the 4 OAuth1 credentials.
        missing = [k for k in REQUIRED_X_KEYS if not os.getenv(k)]
        if missing:
            raise ValueError(f"Missing required X API secrets: {missing}")

        self.client = tweepy.Client(
            consumer_key=os.getenv("X_CONSUMER_KEY"),
            consumer_secret=os.getenv("X_CONSUMER_SECRET"),
            access_token=os.getenv("X_ACCESS_TOKEN"),
            access_token_secret=os.getenv("X_ACCESS_TOKEN_SECRET"),
            wait_on_rate_limit=False,  # we handle 429 explicitly below
        )

    # --------------------------------------------------------------------- #
    # Topic selection — deterministic by day-of-year, never consecutive
    # --------------------------------------------------------------------- #
    @staticmethod
    def pick_lesson(now: Optional[datetime] = None) -> Lesson:
        now = now or datetime.now(timezone.utc)
        idx = now.timetuple().tm_yday % len(CURRICULUM)
        return CURRICULUM[idx]

    # --------------------------------------------------------------------- #
    # Generation
    # --------------------------------------------------------------------- #
    def generate_tweet(self) -> str:
        lesson = self.pick_lesson()
        logger.info("Today's lesson: [%s] %s", lesson.category, lesson.topic)

        system_prompt = (
            "You are a senior systems engineer writing daily System Design micro-lessons for X/Twitter. "
            "Voice: clear, opinionated, concise — like a teacher who has shipped at scale. No fluff, no hedging. "
            "RULES (hard):\n"
            "1) Output MUST be <= 280 characters total, INCLUDING hashtags and emojis.\n"
            "2) Start with the hook '🧵 System Design: <topic>' on the first line.\n"
            "3) Teach exactly ONE concept. Give the trade-off or the rule of thumb.\n"
            "4) End with 2–3 of these hashtags: #SystemDesign #SoftwareEngineering #DevEducation\n"
            "5) Return ONLY the tweet text. No quotes, no preface, no markdown."
        )
        user_prompt = (
            f"Topic: {lesson.topic}\n"
            f"Category: {lesson.category}\n"
            f"Teaching angle: {lesson.angle}\n"
            f"Write the tweet now."
        )

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.openai.chat.completions.create(
                    model=OPENAI_MODEL,
                    temperature=0.7,
                    max_tokens=200,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                text = (resp.choices[0].message.content or "").strip().strip('"')
                text = self._enforce_length(text)
                logger.info("Generated (%d chars): %s", len(text), text)
                return text

            except RateLimitError as e:
                delay = RETRY_BASE_DELAY ** attempt
                logger.warning("OpenAI rate limit (attempt %d/%d): %s — sleeping %ds",
                               attempt, MAX_RETRIES, e, delay)
                time.sleep(delay)

            except (APIConnectionError, APIError) as e:
                delay = RETRY_BASE_DELAY ** attempt
                logger.warning("OpenAI API error (attempt %d/%d): %s — sleeping %ds",
                               attempt, MAX_RETRIES, e, delay)
                time.sleep(delay)

        logger.error("OpenAI unavailable after %d attempts — using fallback", MAX_RETRIES)
        return random.choice(FALLBACK_TWEETS)

    @staticmethod
    def _enforce_length(text: str) -> str:
        # Strip stray quotes and collapse internal whitespace runs.
        text = " ".join(text.split())
        if len(text) <= MAX_TWEET_LEN:
            return text
        # Truncate at the last word boundary that fits, keep an ellipsis.
        cut = text[: MAX_TWEET_LEN - 1].rsplit(" ", 1)[0]
        return cut + "…"

    # --------------------------------------------------------------------- #
    # Posting
    # --------------------------------------------------------------------- #
    def post_tweet(self, text: str) -> dict:
        if len(text) > MAX_TWEET_LEN:
            text = self._enforce_length(text)

        try:
            logger.info("Posting tweet (%d chars)…", len(text))
            resp = self.client.create_tweet(text=text)
            tweet_id = resp.data.get("id")
            logger.info("Posted! tweet_id=%s", tweet_id)
            return resp.data

        except tweepy.Forbidden as e:
            # 403 — most commonly: duplicate content, suspended, or app perms missing
            msg = str(e)
            if "duplicate" in msg.lower():
                logger.warning("Duplicate tweet rejected by X (403). Treating as no-op success.")
                return {"id": None, "duplicate": True}
            logger.error("X 403 Forbidden: %s", msg)
            raise

        except tweepy.Unauthorized as e:
            raise RuntimeError(
                "X API 401 Unauthorized — verify OAuth 1.0a creds AND that the app has "
                "Read+Write permissions enabled in the X developer portal."
            ) from e

        except tweepy.TooManyRequests as e:
            logger.error("X 429 rate-limited: %s", e)
            raise

        except tweepy.TweepyException as e:
            logger.error("Tweepy error: %s", e, exc_info=True)
            raise


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main() -> int:
    try:
        logger.info("ai-tweets bot starting at %s", datetime.now(timezone.utc).isoformat())
        bot = TwitterBot()
        text = bot.generate_tweet()
        bot.post_tweet(text)
        logger.info("Done.")
        return 0

    except ValueError as e:
        logger.error("Config error: %s", e)
        return 2
    except RuntimeError as e:
        logger.error("Runtime error: %s", e)
        return 3
    except Exception as e:  # noqa: BLE001
        logger.error("Unhandled error: %s", e, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
