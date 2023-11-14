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
from openai import AsyncOpenAI

from botinfo import (
    eight_ball_list,
    keep_track,
    newdickt,
    vision_dict,
    persona_config,
    default_persona
)

load_dotenv()

MAX_MESSAGE_LENGTH = 2000  # 2000 characters
message_cooldown = 900  # time to clear keep_safe dict (15 minutes in seconds)
global_timestamp = ""

TOKEN = os.getenv('TOKEN')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
GOOGLE_CSE_ID = os.getenv('GOOGLE_CSE_ID')
weather_api_key = os.getenv('WEATHER_API_KEY')
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

open_ai_client = AsyncOpenAI(api_key=vanc_key)

persona_dict = {
        persona["role"]: {"name": persona["role"], "persona": [persona], "value": persona["value"]}
        for persona in persona_config
    }


@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')
    asyncio.create_task(clear_expired_messages(message_cooldown))
    asyncio.create_task(timestamp())


async def create_assistant():
    chat_model = "gpt-3.5-turbo-1106"
    assistant = await open_ai_client.beta.assistants.create(
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
                                "city": {
                                    "type": "string",
                                    "description": "City name"
                                },
                                "state": {
                                    "type": "string",
                                    "description": "State code (only for the US, leave blank otherwise)"
                                },
                                "country": {
                                    "type": "string",
                                    "description": "Country code. Please use ISO 3166 country codes"
                                }
                            },
                            "required": ["city", "state", "country"],
                        }
                    }
                }
            ],
            model=chat_model,
        )
    return assistant


async def create_thread():
    return await open_ai_client.beta.threads.create()


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

        for user_id in vision_dict.copy():
            timestamp = vision_dict[user_id]["timestamp"]
            if current_time - timestamp > message_cooldown:
                del vision_dict[user_id]

        await asyncio.sleep(30)


@client.event
async def on_message(message):
    if message.content.startswith("?8ball "):
        await eight_ball(message)
        return

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

    if user_id not in newdickt:
        newdickt[user_id] = {"chat-model": "GPT-4 Turbo", "timestamp": timestamp}
    elif user_id in newdickt:
        chat_model = newdickt[user_id]["chat-model"]
        if chat_model == "GPT-4 Vision":
            print("meow")
            async with message.channel.typing():
                response = await get_vision(message)
                await message_reply(response, message)
                return

    if user_id not in keep_track:
        thread = await create_thread()
        current_date = datetime.datetime.now(datetime.timezone.utc)
        date = f"This is real-time data: {current_date}, use it wisely to find better solutions."
        instructions = "All your messages will be sent in discord. Keep them brief and use appropriate formatting. " + date
        keep_track[user_id] = {"thread": thread.id, "instructions": instructions, "persona": "Default", "timestamp": timestamp}
    else:
        instructions = keep_track[user_id]["instructions"]

    async with message.channel.typing():
        await open_ai_client.beta.threads.messages.create(
            thread_id=keep_track[user_id]['thread'],
            role="user",
            content=message.content
        )

        assistant = await create_assistant()

        run = await open_ai_client.beta.threads.runs.create(
            thread_id=keep_track[user_id]['thread'],
            assistant_id=assistant.id,
            instructions=instructions
        )

        while run.status != "completed":
            await asyncio.sleep(1)
            run = await open_ai_client.beta.threads.runs.retrieve(
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
                        city = tool_arguments_dict["city"]
                        state = tool_arguments_dict["state"]
                        country = tool_arguments_dict["country"]
                        function_data = await get_weather(city, state, country)

                    if tool_name == "search_internet":
                        query = tool_arguments_dict["query"]
                        function_data = await search(query)

                    meow.append({
                        "tool_call_id": tool_call_id,
                        "output": function_data
                    })  # Append the tool output to the list

                # Submit all tool outputs after processing all tool calls
                await open_ai_client.beta.threads.runs.submit_tool_outputs(
                    thread_id=keep_track[user_id]['thread'],
                    run_id=run.id,
                    tool_outputs=meow
                )

        gpt_messages = await open_ai_client.beta.threads.messages.list(thread_id=keep_track[user_id]['thread'])
        print(gpt_messages)
        for msg in gpt_messages.data:
            if msg.role == "assistant":
                await message_reply(msg.content[0].text.value, message)
                return


async def message_reply(content, message):
    if len(content) <= MAX_MESSAGE_LENGTH:
        await message.reply(content)
    else:
        chunks = [content[i:i + MAX_MESSAGE_LENGTH] for i in range(0, len(content), MAX_MESSAGE_LENGTH)]
        await message.reply(chunks[0])  # Reply with the first chunk
        for chunk in chunks[1:]:
            await message.channel.send(chunk)  # Send subsequent chunks as regular messages

    return


async def get_vision(message):
    timestamp = time.time()
    user_id = message.author.id
    # Check if the user already has a conversation, if not, create a new one
    if user_id not in vision_dict:
        current_date = datetime.datetime.now(datetime.timezone.utc)
        date = f"This is real-time data: {current_date}, use it wisely to find better solutions."
        default_persona_copy = [person.copy() for person in default_persona]  # Create "deep copy"
        default_persona_copy[0]["content"] += " " + date
        vision_dict[user_id] = {"conversation": default_persona_copy, "persona": "default", "timestamp": timestamp}
    vision_dict[user_id]["timestamp"] = timestamp
    print(vision_dict[user_id])

    conversation = vision_dict[user_id]["conversation"]

    if message.content and message.attachments:
        image_url = message.attachments[0].url
        conversation.append({
            "role": "user",
            "content": [
                {"type": "text", "text": message.content},
                {
                    "type": "image_url",
                    "image_url": {"url": image_url},
                },
            ],
        })
    elif message.content:
        conversation.append({
            "role": "user",
            "content": [
                {"type": "text", "text": message.content},
            ],
        })

    elif message.attachments:
        image_url = message.attachments[0].url
        conversation.append({
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": image_url},
                },
            ],
        })

    response = await open_ai_client.chat.completions.create(
        model="gpt-4-vision-preview",
        messages=conversation,
        max_tokens=300,
    )
    conversation.append({
        "role": "assistant",
        "content": [
            {"type": "text", "text": response.choices[0].message.content},
        ],
    })
    return response.choices[0].message.content


async def search(query):
    print("Google Query:", query)
    num = 3  # Number of results to return
    url = f"https://www.googleapis.com/customsearch/v1?key={GOOGLE_API_KEY}&cx={GOOGLE_CSE_ID}&q={query}&num={num}"
    data = requests.get(url).json()

    search_items = data.get("items")
    print(search_items)
    results = []
    if search_items is not None:
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
    else:
        return "No search results found"

    output = "\n".join(results)
    print("Google Response:", output)
    return output


async def get_weather(city, state, country):
    print(city, state, country)
    # Create the API URL with latitude and longitude parameters
    url = f'http://api.openweathermap.org/geo/1.0/direct?q={city},{state},{country}&limit=3&appid={weather_api_key}'

    # Send a GET request to the API
    response = requests.get(url)

    # Check if the request was successful (status code 200)
    if response.status_code == 200:
        # Parse the JSON data in the response
        data = response.json()
        print(data)
        if data:
            first_item = data[0]
        else:
            return "No data found"

        # Extract latitude and longitude from the first item
        lat = first_item["lat"]
        lon = first_item["lon"]
        print(lat, lon)
        print(lat,lon)

        url = f'http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={weather_api_key}&units=imperial'

        # Send a GET request to the API
        real_response = requests.get(url)

        data = real_response.json()

        # Extract the relevant information from the JSON response
        temperature = data['main']['temp']
        weather_description = data['weather'][0]['description']

        # Return the weather information as a dictionary
        return f"{temperature} F, {weather_description}"
    else:
        # Return an error message if the request was not successful
        return {'error': f'Unable to retrieve weather data. Status code: {response.status_code}'}


@client.tree.command(name='model')
@app_commands.describe(option="Which to choose..")
@app_commands.choices(option=[
    app_commands.Choice(name="GPT-4 Turbo", value="1"),
    app_commands.Choice(name="GPT-4 Vision", value="2"),
])
async def model(interaction: discord.Interaction, option: app_commands.Choice[str]):
    """
        Choose a model

    """
    user_id = interaction.user.id
    selected_model = option.name

    if user_id not in newdickt:
        newdickt[user_id] = {"chat-model": option.name}
        await interaction.response.send_message(f"Model changed to **{selected_model}**.")
    else:
        chat_model = newdickt[user_id]["chat-model"]

        if chat_model == selected_model:
            await interaction.response.send_message(f"**{selected_model}** is already selected.")
        else:
            newdickt[user_id]["chat-model"] = selected_model
            await interaction.response.send_message(f"Model changed to **{selected_model}**.")

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
    thread = await create_thread()
    instructions = None
    message_str = str(message)

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
        instructions = "All your messages will be sent in discord. Keep them brief and use appropriate formatting. " + date

    await open_ai_client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=message_str
    )

    assistant = await create_assistant()

    run = await open_ai_client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant.id,

        instructions=instructions
    )

    while run.status != "completed":
        await asyncio.sleep(1)
        run = await open_ai_client.beta.threads.runs.retrieve(
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
            await open_ai_client.beta.threads.runs.submit_tool_outputs(
                thread_id=thread.id,
                run_id=run.id,
                tool_outputs=meow
            )

    gpt_messages = await open_ai_client.beta.threads.messages.list(thread_id=thread.id)
    print(gpt_messages)
    # Check all messages returned for the assistant role
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

    if option.value in [persona_info["value"] for persona_info in persona_dict.values()]:
        current_persona = next(
            (persona_info["name"] for persona_info in persona_dict.values() if persona_info["value"] == option.value),
            None)

        if current_persona:
            persona = persona_dict[f"{current_persona}"]["persona"]
            # Update the user's conversation and persona in the keep_track dictionary
            user_id = interaction.user.id
            thread = await create_thread()
            print(persona_dict)
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


async def eight_ball(message):
    eight_ball_message = random.choice(eight_ball_list)
    question = message.content[7:]
    title = f'{message.author.name}\n:8ball: 8ball'
    description = f'Q. {question}\nA. {eight_ball_message}'
    embed = discord.Embed(title=title, description=description, color=discord.Color.dark_teal())
    embed.set_footer(text=global_timestamp)
    channel = message.channel
    await channel.send(embed=embed)

async def timestamp():
    global global_timestamp
    while True:
        global_timestamp = datetime.datetime.now().strftime('%m/%d/%Y %I:%M %p')
        await asyncio.sleep(10)


@client.tree.command()
async def ping(interaction: discord.Interaction):
    """Returns the bot latency"""
    await interaction.response.defer()
    bot_latency = round(client.latency * 1000)
    await interaction.followup.send(f"Pong! `{bot_latency}ms`")

client.run(TOKEN)
