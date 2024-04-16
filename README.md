# Utopia Discord Bot

**Utopia is a Discord bot powered by Google Gemini, featuring slash commands, various personas, image understanding with the Vision model, and integration with Google CSE and OpenWeatherMap API.**

## Installation

1. **Clone the Repository:**
   - Clone the repository to your local machine using the following command:
     ```bash
     git clone https://github.com/C4rb0n6/utopia.git
     ```

2. **Set Up Environment Variables:**
   - Create a '.env' file in the root directory of the project.
   - Add the following environment variables with your actual keys and tokens:
     ```env
     TOKEN=your-discord-bot-token
     GEMINI_KEY==your-gemini-key
     GUILD_IDS=your-discord-guild-id(number 1),your-discord-guild-id(number 2)  # Separate with a comma
     GOOGLE_API_KEY=your-google-cse-api-key
     GOOGLE_CSE_ID=your-google-cse-id
     WEATHER_API_KEY=your-openweather-api-key
     ```
     Replace placeholders (`your-discord-bot-token`, `your-gemini-key`, etc.) with your actual tokens and IDs.

3. **Install Dependencies:**
   - Run the following command to install the required Python packages:
     ```bash
     pip install .
     ```

4. **Setup Discord Server:** 
   - Create a channel with ```Gemini``` as the topic.

5. **Run the Bot:**
   - Run [bot.py](/bot.py) to start the bot:
     ```bash
     python bot.py
     ```