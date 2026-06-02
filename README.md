# cv-marketing-campaign-visual-audit-bot
The MCVA Bot is designed to automate the critique of marketing materials (posters, banners, social media ads).

## Hermes AI Setup
To enable Member 4 Hermes AI report generation, create a `.env` file in the project root with this content:

```env
OPENROUTER_API_KEY=your_openrouter_api_key_here
```

Then install dependencies and run the bot again. If the API key is missing, the bot will fall back to the local report generator.
