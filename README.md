# Haber Ajansı

Automated News Intelligence Pipeline that monitors YouTube news channels daily and delivers AI-generated reports to Discord.

## What it does
- Checks YouTube news channels for new videos every day
- Fetches transcripts via Apify
- Analyzes transcripts with Google Gemini AI
- Sends structured reports to a Discord channel

## Setup

### Requirements
- Python 3
- YouTube Data API key
- Gemini API key(s)
- Apify API key
- Discord Webhook URL

### GitHub Secrets
Add these to your repository secrets:
- `YOUTUBE_API_KEY`
- `GEMINI_API_KEY_1`, `GEMINI_API_KEY_2`, `GEMINI_API_KEY_3`
- `APIFY_API_KEY`
- `DISCORD_WEBHOOK_URL`

## Deployment
Runs automatically every day via GitHub Actions.
