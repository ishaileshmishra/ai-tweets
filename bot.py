"""
Production-ready X (Twitter) auto-poster for AI/software engineering content.
Generates tweets using OpenAI GPT, posts via Tweepy X API v2.
Run daily via cron or GitHub Actions. Requires .env with keys.
"""

import os
import logging
from datetime import datetime

from openai import OpenAI
from dotenv import load_dotenv
import tweepy

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('twitter_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TwitterBot:
    def __init__(self):
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set in .env")
        self.openai_client = OpenAI(api_key=self.openai_api_key)

        self.x_bearer_token = os.getenv('X_BEARER_TOKEN')
        self.x_consumer_key = os.getenv('X_CONSUMER_KEY')
        self.x_consumer_secret = os.getenv('X_CONSUMER_SECRET')
        self.x_access_token = os.getenv('X_ACCESS_TOKEN')
        self.x_access_token_secret = os.getenv('X_ACCESS_TOKEN_SECRET')

        missing_keys = [k for k in [
            'X_BEARER_TOKEN', 'X_CONSUMER_KEY', 'X_CONSUMER_SECRET',
            'X_ACCESS_TOKEN', 'X_ACCESS_TOKEN_SECRET'
        ] if not os.getenv(k)]
        if missing_keys:
            raise ValueError(f"Missing X API keys in .env: {missing_keys}")

        self.client = tweepy.Client(
            bearer_token=self.x_bearer_token,
            consumer_key=self.x_consumer_key,
            consumer_secret=self.x_consumer_secret,
            access_token=self.x_access_token,
            access_token_secret=self.x_access_token_secret,
            wait_on_rate_limit=True
        )

    def generate_tweet(self) -> str:
        """Generate a tweet on AI dev/software engineering using GPT-4o-mini."""
        topics = [
            "latest AI implementation trends in software engineering",
            "tips for AI development best practices",
            "software engineering challenges with AI tools",
            "news on AI frameworks like LangChain or TensorFlow",
            "prompt engineering and LLM best practices",
            "AI-powered developer tools and productivity",
            "ethical AI and responsible software development",
        ]
        topic = topics[datetime.now().weekday() % len(topics)]  # Rotate daily topics

        prompt = f"""
        Generate one engaging X/Twitter post (max 280 chars) about: {topic}.
        Make it informative, add a practical tip or insight, use 1-2 hashtags like #AI #SoftwareEngineering.
        Conversational tone, end with a question to engage.
        Do not exceed 280 characters.
        """

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.7
            )
            tweet = response.choices[0].message.content.strip()
            if len(tweet) > 280:
                tweet = tweet[:277] + "..."
            logger.info(f"Generated tweet: {tweet}")
            return tweet
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            raise

    def post_tweet(self, text: str) -> dict:
        """Post tweet and return response."""
        try:
            response = self.client.create_tweet(text=text)
            logger.info(f"Tweet posted! ID: {response.data['id']}")
            return response.data
        except tweepy.TweepyException as e:
            logger.error(f"Tweepy error: {e}")
            if "401" in str(e):  # Unauthorized, check keys/permissions
                raise ValueError("X API auth failed. Verify keys and app permissions (Read+Write).")
            raise


def main():
    try:
        bot = TwitterBot()
        tweet_text = bot.generate_tweet()
        bot.post_tweet(tweet_text)
        logger.info("Daily post completed successfully.")
    except Exception as e:
        logger.error(f"Bot run failed: {e}")
        raise

# main function to run the bot
if __name__ == "__main__":
    main()
