import datetime
import json
import os
import random
import time

import asyncio
import discord
import requests
from discord import app_commands
from dotenv import load_dotenv
from openai import OpenAI

from botinfo import (
    eight_ball_list,
    keep_track,
    newdickt,
    persona_dict
)

load_dotenv()

MAX_MESSAGE_LENGTH = 2000  # 2000 characters
message_cooldown = 900  # time to clear keep_safe dict (15 minutes in seconds)

TOKEN = os.getenv('TOKEN')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
GOOGLE_CSE_ID = os.getenv('GOOGLE_CSE_ID')
vanc_key = os.getenv('VANC_KEY')  # gpt4 key
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
    asyncio.create_task(clear_expired_messages(message_cooldown))


def create_assistant(model):
    chat_model = None
    if model == "GPT-4-Turbo":
        chat_model = "gpt-4-1106-preview"
    elif model == "GPT-4-Vision":
        chat_model = "gpt-4-vision-preview"
    assistant = open_ai_client.beta.assistants.create(
            name="Math Tutor",
            instructions="You are a personal math tutor. Write and run code to answer math questions.",
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
                            "required": ["query"],
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
                            "required": ["lat", "lon"],
                        }
                    }
                }
            ],
            model=chat_model
        )
    return assistant

def create_thread():
    return open_ai_client.beta.threads.create()

# Define a coroutine to periodically check and remove expired messages
async def clear_expired_messages(message_cooldown):
    while True:
        current_time = time.time()

        for user_id in keep_track.copy():
            timestamp = keep_track[user_id]["timestamp"]
            if current_time - timestamp > message_cooldown:
                del keep_track[user_id]

        for user_id in newdickt.copy():
            timestamp = newdickt[user_id]["timestamp"]
            if current_time - timestamp > message_cooldown:
                del newdickt[user_id]

        await asyncio.sleep(30)  # Adjust the sleep interval as needed

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
        current_date = datetime.datetime.now(datetime.timezone.utc)
        date = f"This is real-time data: {current_date}, use it wisely to find better solutions."
        instructions = "All your messages will be sent in discord. Use appropriate formatting. " + date
        keep_track[user_id] = {"thread": thread.id, "instructions": instructions, "persona": "Default", "timestamp": timestamp}
    else:
        instructions = keep_track[user_id]["instructions"]

    if user_id not in newdickt:
        newdickt[user_id] = {"chat-model": 'GPT-4-Turbo', "timestamp": timestamp}

    async with message.channel.typing():
        open_ai_client.beta.threads.messages.create(
            thread_id=keep_track[user_id]['thread'],
            role="user",
            content=message.content
        )

        assistant = create_assistant(newdickt[user_id]['chat-model'])

        run = open_ai_client.beta.threads.runs.create(
            thread_id=keep_track[user_id]['thread'],
            assistant_id=assistant.id,

            instructions=instructions
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
    num = 3  # Number of results to return
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


@client.tree.command(name='gpt')
@app_commands.describe(persona="Which persona to choose..")
@app_commands.choices(
    persona=[
        app_commands.Choice(name="Republican", value="2"),
        app_commands.Choice(name="Chef", value="3"),
        app_commands.Choice(name="Math", value="4"),
        app_commands.Choice(name="Code", value="5"),
        app_commands.Choice(name="Ego", value="9"),
        app_commands.Choice(name="Fitness Trainer", value="12"),
        app_commands.Choice(name="Gordon Ramsay", value="13"),
        app_commands.Choice(name="DAN", value="14"),
        app_commands.Choice(name="Default", value="16"),
    ]
)
async def gpt(interaction: discord.Interaction, message: str, persona: app_commands.Choice[str] = None):
    """
    Ask ChatGPT a question

    Args:
        message (str): Your question
        persona (Optional[app_commands.Choice[str]]): Choose a persona
    """
    await interaction.response.defer()
    timestamp = time.time()
    user_id = interaction.user.id
    thread = create_thread()
    instructions = None
    message_str = str(message)

    if user_id not in newdickt:
        newdickt[user_id] = {"chat-model": 'GPT-4-Turbo', "timestamp": timestamp}

    if persona:
        for persona_data in persona_dict.values():
            if persona_data['value'] == persona.value:
                persona = persona_data['name']
                selected_persona = persona_dict[f"{persona}"]["persona"]
                instructions = selected_persona[0]["content"]
                break
    else:
        current_date = datetime.datetime.now(datetime.timezone.utc)
        date = f"This is real-time data: {current_date}, use it wisely to find better solutions."
        instructions = "Always address the user as daddy." + date

    open_ai_client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=message_str
    )

    assistant = create_assistant(newdickt[user_id]['chat-model'])

    run = open_ai_client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant.id,

        instructions=instructions
    )

    while run.status != "completed":
        time.sleep(1)
        run = open_ai_client.beta.threads.runs.retrieve(
            thread_id=thread.id,
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
                thread_id=thread.id,
                run_id=run.id,
                tool_outputs=meow
            )

    gpt_messages = open_ai_client.beta.threads.messages.list(thread_id=thread.id)
    for msg in gpt_messages.data:
        if msg.role == "assistant":
            await interaction.followup.send(
                content=f'***{interaction.user.mention} - {message_str}***\n\n{msg.content[0].text.value}')
            return

@client.tree.command(name='personas')
@app_commands.describe(option="Which to choose..")
@app_commands.choices(option=[
    app_commands.Choice(name="Current Persona", value="1"),
    app_commands.Choice(name="Republican", value="2"),
    app_commands.Choice(name="Chef", value="3"),
    app_commands.Choice(name="Math", value="4"),
    app_commands.Choice(name="Code", value="5"),
    app_commands.Choice(name="Ego", value="9"),
    app_commands.Choice(name="Fitness Trainer", value="12"),
    app_commands.Choice(name="Gordon Ramsay", value="13"),
    app_commands.Choice(name="DAN", value="14"),
    app_commands.Choice(name="Prompt", value="17"),
    app_commands.Choice(name="Default", value="16"),
])
async def personas(interaction: discord.Interaction, option: app_commands.Choice[str]):
    """
        Choose a persona

    """
    timestamp = time.time()
    await interaction.response.defer()
    global current_persona

    for persona in persona_dict.values():

        if persona['value'] == option.value:
            current_persona = persona['name']
            break

    if option.value in [persona_info["value"] for persona_info in persona_dict.values()]:
        current_persona = next(
            (persona_info["name"] for persona_info in persona_dict.values() if persona_info["value"] == option.value),
            None)

        if current_persona:
            persona = persona_dict[f"{current_persona}"]["persona"]
            # Update the user's conversation and persona in the keep_track dictionary
            user_id = interaction.user.id
            thread = create_thread()
            keep_track[user_id] = {"thread": thread.id, "instructions": persona[0]["content"], "persona": current_persona, "timestamp": timestamp}
            await interaction.followup.send(f"Persona changed to **{current_persona}**.")
            return

    if option.value == '1':
        user_id = interaction.user.id

        if user_id not in keep_track:
            current_per = "Default"
        else:
            current_per = keep_track[user_id]["persona"]

        response = f"**Current Persona:** {current_per}"
        await interaction.followup.send(response)
        return


client.run(TOKEN)
