import datetime
import json
import os
import io
import random
import time

import aiohttp
import asyncio
import discord
import requests
from dotenv import load_dotenv
from openai import AsyncOpenAI

from botinfo import (
    eight_ball_list,
    keep_track,
    newdickt,
    vision_dict,
)

load_dotenv()

MAX_MESSAGE_LENGTH = 2000  # Message length before truncation

GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
GOOGLE_CSE_ID = os.getenv('GOOGLE_CSE_ID')
weather_api_key = os.getenv('WEATHER_API_KEY')
vanc_key = os.getenv('VANC_KEY')

open_ai_client = AsyncOpenAI(api_key=vanc_key)


async def assistant_response(message, instructions, files=None):
    user_id = message.author.id
    assistant = keep_track[user_id]["has_assistant"]
    if files:
        await open_ai_client.beta.threads.messages.create(
            thread_id=keep_track[user_id]['thread'],
            role="user",
            content=message.content,
            file_ids=files
        )
    else:
        await open_ai_client.beta.threads.messages.create(
            thread_id=keep_track[user_id]['thread'],
            role="user",
            content=message.content,
        )

    run = await open_ai_client.beta.threads.runs.create(
        thread_id=keep_track[user_id]['thread'],
        assistant_id=assistant.id,
        instructions=instructions
    )

    print("before loop")
    while run.status != "completed":
        try:
            if run.status == "failed":
                print(run.last_error)
                print("failed")
                await message.reply("shit broke idk, ask a better question loser")
                return

            if run.status == "expired":
                print(run.last_error)
                print("expired")
                await message.reply("shit broke idk, ask a better question loser")
                return

            print(run.status)
            await asyncio.sleep(3)
            print("after sleep")

            start_time = time.time()

            run = await open_ai_client.beta.threads.runs.retrieve(
                thread_id=keep_track[user_id]['thread'],
                run_id=run.id
            )

            end_time = time.time()
            print(f"API call took {end_time - start_time} seconds")

            tool_call_list = []
            if run.status == "requires_action":
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                function_data = None

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

                    if function_data is None:
                        function_data = "No data found."

                    tool_call_list.append({
                        "tool_call_id": tool_call_id,
                        "output": function_data
                    })
                    print(function_data)
                    print(tool_call_list)

                await open_ai_client.beta.threads.runs.submit_tool_outputs(
                    thread_id=keep_track[user_id]['thread'],
                    run_id=run.id,
                    tool_outputs=tool_call_list
                )

        except Exception as e:
            print(f"Error: {e}")
            # Handle the error appropriately

    print(run.status)
    print("after loop")


async def format_response(message):
    file = None
    user_id = message.author.id
    message_list = await open_ai_client.beta.threads.messages.list(thread_id=keep_track[user_id]['thread'])

    for msg in message_list.data:
        print(msg)
        if msg.role == "assistant":
            assistant_message = await open_ai_client.beta.threads.messages.retrieve(
                thread_id=keep_track[user_id]['thread'],
                message_id=msg.id
            )

            try:
                file_id = None
                message_content = assistant_message.content[0].text
                annotations = message_content.annotations
                print(annotations)
            except:
                file_id = assistant_message.content[0].image_file.file_id
                annotations = None
                print("no annotations")

            if annotations:
                for annotation in annotations:
                    file_path = getattr(annotation, 'file_path', None)
                    if file_path:
                        print(file_path)
                        file_name = os.path.basename(annotation.text)
                        file_content = await download_openai_file(file_path.file_id)
                        print(f"{file_content} ANNOTATIONS")
                        if file_content:
                            file = discord.File(io.BytesIO(file_content), filename=file_name)
                            print(file_name)

                    await message.reply(msg.content[0].text.value, file=file)
                    return

            elif file_id:
                file_content = await download_openai_file(file_id)
                print(f"{file_content} NOT ANNOTATIONS")
                if file_content:
                    file_content_io = io.BytesIO(file_content)
                    file = discord.File(file_content_io, filename="model_uploaded_file.png")
                    if msg.content[1].text.value:
                        await message.reply(msg.content[1].text.value, file=file)
                        return
                    else:
                        await message.reply(file=file)
                        return
            else:
                await message_reply(msg.content[0].text.value, message)
                return

conversation = []
async def get_vision(message):
    timestamp = time.time()
    user_id = message.author.id
    # Check if the user already has a conversation, if not, create a new one
    if user_id not in vision_dict:
        instructions = await get_default_persona()
        instructions = [{"role": "system", "content": [{"type": "text", "text": instructions}]}]
        vision_dict[user_id] = {"conversation": instructions, "persona": "default", "timestamp": timestamp}
    vision_dict[user_id]["timestamp"] = timestamp
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
        max_tokens=600,
    )
    conversation.append({
        "role": "assistant",
        "content": [
            {"type": "text", "text": response.choices[0].message.content},
        ],
    })

    await message_reply(response.choices[0].message.content, message)
    return

async def get_default_persona():
    current_date = datetime.datetime.now(datetime.timezone.utc)
    date = f"This is real-time data: '{current_date}', use it to assist users with questions regarding time."
    instructions = ("All your replies will be sent in discord. Messages will be truncated >2K chars. "
                    "Use appropriate formatting. ") + date
    return instructions

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
    url = f'http://api.openweathermap.org/geo/1.0/direct?q={city},{state},{country}&limit=3&appid={weather_api_key}'

    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        print(data)
        if data:
            first_item = data[0]
        else:
            return "No data found"

        lat = first_item["lat"]
        lon = first_item["lon"]
        print(lat, lon)
        print(lat,lon)

        url = f'http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={weather_api_key}&units=imperial'

        real_response = requests.get(url)

        data = real_response.json()

        temperature = data['main']['temp']
        weather_description = data['weather'][0]['description']

        return f"{temperature} F, {weather_description}"
    else:
        return f'Unable to retrieve weather data. Status code: {response.status_code}'


async def eight_ball(message):
    eight_ball_message = random.choice(eight_ball_list)
    question = message.content[7:]
    title = f'{message.author.name}\n:8ball: 8ball'
    description = f'Q. {question}\nA. {eight_ball_message}'
    embed = discord.Embed(title=title, description=description, color=discord.Color.dark_teal())
    embed.set_footer(text=datetime.datetime.now().strftime('%m/%d/%Y %I:%M %p'))
    channel = message.channel
    await channel.send(embed=embed)


async def message_reply(content, message):
    if len(content) <= MAX_MESSAGE_LENGTH:
        await message.reply(content)
    else:
        chunks = [content[i:i + MAX_MESSAGE_LENGTH] for i in range(0, len(content), MAX_MESSAGE_LENGTH)]
        await message.reply(chunks[0])
        for chunk in chunks[1:]:
            await message.channel.send(chunk)
    return


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


async def create_assistant(gpt_version="GPT-3.5 Turbo"):
    tools = None
    chat_model = None
    if gpt_version == "GPT-4 Turbo":
        chat_model = "gpt-4-1106-preview"
        tools = [
            {"type": "code_interpreter"}
        ]
    elif gpt_version == "GPT-3.5 Turbo":
        chat_model = "gpt-3.5-turbo-1106"
        tools = [
            {"type": "code_interpreter"},
            {
                "type": "function",
                "function": {
                    "name": "search_internet",
                    "description": "Search the internet using Google's API. Returns top 3 search results.",
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
        ]

    assistant = await open_ai_client.beta.assistants.create(
        name="Math tutor",
        instructions="You are a personal math tutor. When asked a math question, write and run code to answer the question.",
        tools=tools,
        model=chat_model,
    )
    return assistant


async def create_thread():
    return await open_ai_client.beta.threads.create()

async def download_file_from_url(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                content = io.BytesIO()
                while True:
                    chunk = await resp.content.read(1024)
                    if not chunk:
                        break
                    content.write(chunk)
                content.seek(0)
                return content


async def download_openai_file(file_id):
    file_content = await open_ai_client.files.content(file_id)
    return file_content.content