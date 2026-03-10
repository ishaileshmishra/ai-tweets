"""
Production-ready X (Twitter) auto-poster for AI/software engineering content.
Generates tweets using OpenAI GPT, posts via Tweepy X API v2.
Run daily via cron or GitHub Actions. Requires .env with keys.
"""

import os
import random
import time
import logging
from datetime import datetime

from openai import OpenAI, RateLimitError, APIStatusError
from dotenv import load_dotenv
import tweepy

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

TOPICS = [
    "latest AI implementation trends in software engineering",
    "tips for AI development best practices",
    "software engineering challenges with AI tools",
    "news on AI frameworks like LangChain or TensorFlow",
    "prompt engineering and LLM best practices",
    "AI-powered developer tools and productivity",
    "ethical AI and responsible software development",
]

FALLBACK_TWEETS = [
    "AI isn't replacing developers — it's amplifying them. The best engineers learn to collaborate with AI, not compete. What AI tool has boosted your productivity the most? #AI #SoftwareEngineering",
    "Prompt engineering tip: be specific about format, length, and tone. Vague prompts = vague results. What's your go-to prompting strategy? #LLM #AI",
    "The best AI code suggestions still need a human to review them. Trust but verify — that's the new developer mantra. How do you review AI-generated code? #AI #DevLife",
    "LangChain, LlamaIndex, CrewAI — the AI framework ecosystem is evolving fast. Staying curious is the only way to keep up. Which framework are you exploring? #AI #SoftwareEngineering",
    "Responsible AI starts with responsible data. Bias in, bias out. Are you auditing your training data? #EthicalAI #SoftwareEngineering",
    "Hot take: writing good tests is more important than ever in the age of AI-generated code. Do you trust AI to write your tests? #AI #Testing",
    "The secret to productive AI pair-programming: treat the AI like a junior dev — guide it, review its work, iterate. What's your AI pairing workflow? #AI #DevProductivity",
]

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2


class TwitterBot:
    def __init__(self):
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set in .env")
        self.openai_client = OpenAI(api_key=self.openai_api_key)

        missing_keys = [k for k in [
            'X_BEARER_TOKEN', 'X_CONSUMER_KEY', 'X_CONSUMER_SECRET',
            'X_ACCESS_TOKEN', 'X_ACCESS_TOKEN_SECRET'
        ] if not os.getenv(k)]
        if missing_keys:
            raise ValueError(f"Missing X API keys in .env: {missing_keys}")

        self.client = tweepy.Client(
            bearer_token=os.getenv('X_BEARER_TOKEN'),
            consumer_key=os.getenv('X_CONSUMER_KEY'),
            consumer_secret=os.getenv('X_CONSUMER_SECRET'),
            access_token=os.getenv('X_ACCESS_TOKEN'),
            access_token_secret=os.getenv('X_ACCESS_TOKEN_SECRET'),
            wait_on_rate_limit=True
        )

    def _is_quota_exhausted(self, error: RateLimitError) -> bool:
        body = getattr(error, 'body', None)
        if isinstance(body, dict):
            code = body.get('error', {}).get('code', '')
            return code == 'insufficient_quota'
        return 'insufficient_quota' in str(error)

    def generate_tweet(self) -> str:
        topic = TOPICS[datetime.now().weekday() % len(TOPICS)]

        prompt = (
            f"Generate one engaging X/Twitter post (max 280 chars) about: {topic}. "
            "Make it informative, add a practical tip or insight, use 1-2 hashtags like #AI #SoftwareEngineering. "
            "Conversational tone, end with a question to engage. "
            "Do not exceed 280 characters."
        )

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info("Generating tweet (attempt %d/%d) for topic: %s", attempt, MAX_RETRIES, topic)
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=100,
                    temperature=0.7
                )
                tweet = response.choices[0].message.content.strip()
                if len(tweet) > 280:
                    tweet = tweet[:277] + "..."
                logger.info("Tweet generated: %s", tweet)
                return tweet

            except RateLimitError as e:
                if self._is_quota_exhausted(e):
                    logger.warning("OpenAI quota exhausted — falling back to pre-written tweet")
                    return self._fallback_tweet()
                if attempt == MAX_RETRIES:
                    logger.warning("Transient rate-limit persisted after %d retries — using fallback", MAX_RETRIES)
                    return self._fallback_tweet()
                delay = RETRY_BASE_DELAY ** attempt
                logger.warning("Rate-limited by OpenAI, retrying in %ds...", delay)
                time.sleep(delay)

            except APIStatusError as e:
                logger.error("OpenAI API error (status %s): %s", e.status_code, e.message)
                if e.status_code in (401, 403):
                    raise ValueError(
                        "OpenAI authentication failed. Verify your OPENAI_API_KEY is valid."
                    ) from e
                if attempt == MAX_RETRIES:
                    logger.warning("OpenAI API unavailable after %d retries — using fallback", MAX_RETRIES)
                    return self._fallback_tweet()
                delay = RETRY_BASE_DELAY ** attempt
                logger.warning("Retrying in %ds...", delay)
                time.sleep(delay)

        return self._fallback_tweet()

    @staticmethod
    def _fallback_tweet() -> str:
        tweet = random.choice(FALLBACK_TWEETS)
        logger.info("Using fallback tweet: %s", tweet)
        return tweet

    def post_tweet(self, text: str) -> dict:
        try:
            logger.info("Posting tweet: %s", text)
            response = self.client.create_tweet(text=text)
            tweet_id = response.data['id']
            logger.info("Tweet posted! ID: %s", tweet_id)
            return response.data
        except tweepy.TweepyException as e:
            if "401" in str(e):
                raise ValueError(
                    "X API auth failed. Verify keys and app permissions (Read+Write)."
                ) from e
            logger.error("Tweepy error: %s", e, exc_info=True)
            raise


def main():
    try:
        logger.info("Starting Twitter bot...")
        bot = TwitterBot()

        tweet_text = bot.generate_tweet()
        bot.post_tweet(tweet_text)

    except ValueError as e:
        logger.error("Configuration error: %s", e)
        exit(1)
    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=True)
        exit(1)


if __name__ == "__main__":
    main()