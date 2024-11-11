# Utopia

**Utopia is a Discord bot powered by Google Gemini, featuring slash commands, various personas, image understanding, and integration with Google CSE and OpenWeatherMap API.**

### Requirements
* Python 3.9+
* Libraries [google-generativeai, discord, dotenv]
* API Keys [Discord, Google Gemini, OpenWeatherMap, Google CSE]

### Setup

**1. Set Up Environment Variables:**
   - Create a '.env' file in the root directory of the project.
   - Add the following environment variables with your actual keys and tokens:
     ```env
     TOKEN=your-discord-bot-token
     GEMINI_KEY==your-gemini-key
     GUILD_IDS=your-discord-guild-id(number 1),your-discord-guild-id(number 2)  # Separate with a comma
     GOOGLE_API_KEY=your-google-cse-api-key
     GOOGLE_CSE_ID=your-google-cse-id
     WEATHER_API_KEY=your-openweather-api-key
     DEFAULT_CHANNEL=your-lottery-message-channel
     ```
     Replace placeholders (`your-discord-bot-token`, `your-gemini-key`, etc.) with your actual tokens and IDs.

**2. Setup Discord Server:** 
   - Create a channel with ```Gemini``` as the topic. This will serve as the chat channel.