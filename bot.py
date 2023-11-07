import datetime
import json
import os
import random
import time

import discord
import requests
from discord import app_commands
from dotenv import load_dotenv
from openai import OpenAI

from botinfo import (
    eight_ball_list,
    keep_track,
)

load_dotenv()

MAX_MESSAGE_LENGTH = 2000  # 2000 characters

TOKEN = os.getenv('TOKEN')
vanc_key = os.getenv('VANC_KEY')  # gpt4 key
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
GOOGLE_CSE_ID = os.getenv('GOOGLE_CSE_ID')
weather_api_key = os.getenv('WEATHER_API_KEY')
APP_ID = os.getenv('APP_ID')
GUILD1 = os.getenv("GUILD1")
GUILD2 = os.getenv("GUILD2")
GUILD_ID = [GUILD1, GUILD2]


class MyClient(discord.Client):
    def __init__(self, *, intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.guild_ids = GUILD_ID

    async def setup_hook(self):
        for guild_id in self.guild_ids:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)


intents = discord.Intents().all()
client = MyClient(intents=intents)

open_ai_client = OpenAI(api_key=vanc_key)

@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')


assistant = open_ai_client.beta.assistants.create(
    name="Yuji",
    instructions="I'm pretty sure field does nothing. Hi, Dean.",
    tools=[
        {"type": "code_interpreter"},
        {
            "type": "function",
            "function": {
                "name": "search_internet",
                "description": "Search the internet using Google's API. Returns top 7 search results.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather data using OpenWeatherMap's API. Returns Fahrenheit ONLY.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lat": {
                            "type": "number",
                            "description": "Latitude coordinate"
                        },
                        "lon": {
                            "type": "number",
                            "description": "Longitude coordinate"
                        }
                    },
                    "required": ["lat", "lon"]
                }
            }
        }
    ],
    model="gpt-4-1106-preview"
)

def create_thread():
    return open_ai_client.beta.threads.create()

@client.event
async def on_message(message):
    timestamp = time.time()  # Timestamp for keeping track of how long users are kept in keep_track
    user_id = message.author.id

    if message.author.bot:
        return

    if message.channel.name != 'chat-gpt':
        return

    if message.content.startswith("!"):
        return

    if message.type == discord.MessageType.pins_add:
        return

    if user_id not in keep_track:
        thread = create_thread()
        keep_track[user_id] = {"thread": thread.id, "timestamp": timestamp}

    async with message.channel.typing():
        open_ai_client.beta.threads.messages.create(
            thread_id=keep_track[user_id]['thread'],
            role="user",
            content=message.content
        )
        current_date = datetime.datetime.now(datetime.timezone.utc)
        date = f"This is real-time data: {current_date}, use it wisely to find better solutions."

        run = open_ai_client.beta.threads.runs.create(
            thread_id=keep_track[user_id]['thread'],
            assistant_id=assistant.id,
            instructions="Always address the user as daddy." + date
        )

        while run.status != "completed":
            time.sleep(1)
            run = open_ai_client.beta.threads.runs.retrieve(
                thread_id=keep_track[user_id]['thread'],
                run_id=run.id
            )
            meow = []
            # Check if there are tool calls to handle
            if run.status == "requires_action":
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                for tool_call in tool_calls:
                    tool_call_id = tool_call.id
                    tool_name = tool_call.function.name
                    tool_arguments_json = tool_call.function.arguments
                    tool_arguments_dict = json.loads(tool_arguments_json)

                    if tool_name == "get_weather":
                        lat = tool_arguments_dict["lat"]
                        lon = tool_arguments_dict["lon"]
                        function_data = await get_weather(lat, lon)

                    if tool_name == "search_internet":
                        query = tool_arguments_dict["query"]
                        function_data = await search(query)

                    meow.append({
                        "tool_call_id": tool_call_id,
                        "output": function_data
                    })  # Append the tool output to the list

                # Submit all tool outputs after processing all tool calls
                open_ai_client.beta.threads.runs.submit_tool_outputs(
                    thread_id=keep_track[user_id]['thread'],
                    run_id=run.id,
                    tool_outputs=meow
                )

        gpt_messages = open_ai_client.beta.threads.messages.list(thread_id=keep_track[user_id]['thread'])
        for msg in gpt_messages.data:
            if msg.role == "assistant":
                await message_reply(msg.content[0].text.value, message)
                return

async def get_weather(lat, lon):
    api_key = '18d92eb0404edf78cc69383fb89a25af'
    # Create the API URL with latitude and longitude parameters
    url = f'http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=imperial'

    # Send a GET request to the API
    response = requests.get(url)

    # Check if the request was successful (status code 200)
    if response.status_code == 200:
        # Parse the JSON data in the response
        data = response.json()

        # Extract the relevant information from the JSON response
        temperature = data['main']['temp']
        weather_description = data['weather'][0]['description']

        # Return the weather information as a dictionary
        return f"{temperature} F, {weather_description}"
    else:
        # Return an error message if the request was not successful
        return {'error': f'Unable to retrieve weather data. Status code: {response.status_code}'}


async def eight_ball(message):
    eight_ball_message = random.choice(eight_ball_list)
    channel = message.channel
    timestamp_str = datetime.datetime.now().strftime('%m/%d/%Y %I:%M %p')
    title = f'{message.author.name}\n:8ball: 8ball'
    description = f'Q. {(message.content[7:])}\nA. {eight_ball_message}'
    embed = discord.Embed(title=title, description=description, color=discord.Color.dark_teal())
    embed.set_footer(text=f"{timestamp_str}")
    await channel.send(embed=embed)


async def message_reply(content, message):
    if len(content) <= MAX_MESSAGE_LENGTH:
        await message.reply(content)
    else:
        chunks = [content[i:i + MAX_MESSAGE_LENGTH] for i in range(0, len(content), MAX_MESSAGE_LENGTH)]
        await message.reply(chunks[0])  # Reply with the first chunk
        for chunk in chunks[1:]:
            await message.channel.send(chunk)  # Send subsequent chunks as regular messages

    return

async def search(query):
    print("Google Query:", query)
    num = 7  # Number of results to return
    url = f"https://www.googleapis.com/customsearch/v1?key={GOOGLE_API_KEY}&cx={GOOGLE_CSE_ID}&q={query}&num={num}"
    data = requests.get(url).json()

    search_items = data.get("items")
    results = []

    for i, search_item in enumerate(search_items, start=1):
        title = search_item.get("title", "N/A")
        snippet = search_item.get("snippet", "N/A")
        long_description = search_item.get("pagemap", {}).get("metatags", [{}])[0].get("og:description", "N/A")
        link = search_item.get("link", "N/A")

        result_str = f"Result {i}: {title}\n"

        if long_description != "N/A":
            result_str += f"Description {long_description}\n"
        else:
            result_str += f"Snippet {snippet}\n"

        result_str += f"URL {link}\n"

        results.append(result_str)

    output = "\n".join(results)
    print("Google Response:", output)
    return output


async def get_weather(lat, lon):
    # Create the API URL with latitude and longitude parameters
    url = f'http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={weather_api_key}&units=imperial'

    # Send a GET request to the API
    response = requests.get(url)

    # Check if the request was successful (status code 200)
    if response.status_code == 200:
        # Parse the JSON data in the response
        data = response.json()

        # Extract the relevant information from the JSON response
        temperature = data['main']['temp']
        weather_description = data['weather'][0]['description']

        # Return the weather information as a dictionary
        return {
            'temperature': temperature,
            'weather_description': weather_description
        }
    else:
        # Return an error message if the request was not successful
        return {'error': f'Unable to retrieve weather data. Status code: {response.status_code}'}


async def send_embed_message(channel, title, description, thumbnail_url=None, footer=True):
    embed = discord.Embed(title=title, description=description, color=discord.Color.dark_teal())

    if thumbnail_url is not None:
        embed.set_thumbnail(url=thumbnail_url)
    timestamp_str = datetime.datetime.now().strftime('%m/%d/%Y %I:%M %p')
    embed.set_footer(text=f"{timestamp_str}")

    if footer:
        embed.set_footer(text=f"{timestamp_str}")

    message = await channel.send(embed=embed)
    return message


@client.tree.command()
async def ping(interaction: discord.Interaction):
    """Returns the bot latency"""
    await interaction.response.defer()
    bot_latency = round(client.latency * 1000)
    await interaction.followup.send(f"Pong! `{bot_latency}ms`")


client.run(TOKEN)
