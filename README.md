# ai-tweets

Production-ready X (Twitter) auto-poster for AI/software engineering content. Generates tweets using OpenAI GPT-4o-mini, posts via Tweepy X API v2. Runs daily via GitHub Actions or cron.

## Features

- AI-generated tweets on rotating topics (AI dev, software engineering, frameworks, etc.)
- X API v2 integration via Tweepy
- GitHub Actions: scheduled daily + manual trigger
- File and console logging

## Prerequisites

- Python 3.9+
- [OpenAI API key](https://platform.openai.com/api-keys)
- [X (Twitter) Developer account](https://developer.twitter.com/) with Read+Write app permissions

## Setup

### Local

1. Clone the repo:
   ```bash
   git clone https://github.com/ishaileshmishra/ai-tweets.git
   cd ai-tweets
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and add your keys:
   ```bash
   cp .env.example .env
   ```

4. Run manually:
   ```bash
   python bot.py
   ```

### GitHub Actions (Recommended)

1. Create repo `ishaileshmishra/ai-tweets` on GitHub, then push:
   ```bash
   git init
   git add .
   git commit -m "Initial commit: AI tweet bot"
   git branch -M main
   git remote add origin https://github.com/ishaileshmishra/ai-tweets.git
   git push -u origin main
   ```
2. Go to **Settings → Secrets and variables → Actions** and add these 6 repository secrets:
   - `OPENAI_API_KEY`
   - `X_BEARER_TOKEN`
   - `X_CONSUMER_KEY`
   - `X_CONSUMER_SECRET`
   - `X_ACCESS_TOKEN`
   - `X_ACCESS_TOKEN_SECRET`
3. Trigger manually: **Actions → Daily AI Tweet → Run workflow**
4. Scheduled run: 9 AM IST daily (or adjust cron in `.github/workflows/post-tweet.yml`)

Push updates anytime; GitHub Actions uses the latest code on each run.

### Cron (Alternative)

For VPS or local scheduling:

```bash
0 9 * * * /usr/bin/python3 /path/to/ai-tweets/bot.py
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `X_BEARER_TOKEN` | X API bearer token |
| `X_CONSUMER_KEY` | X API consumer key |
| `X_CONSUMER_SECRET` | X API consumer secret |
| `X_ACCESS_TOKEN` | X API access token |
| `X_ACCESS_TOKEN_SECRET` | X API access token secret |

## Troubleshooting

- **401 Unauthorized:** Verify X API keys and ensure app has Read+Write permissions
- **Rate limits:** Free tier allows ~500 tweets/month
- **Logs:** Check `twitter_bot.log` for errors

## License

MIT
