import asyncio
import datetime
import io
import json
import os
import random
import time

import aiohttp
import discord
import requests
import PIL.Image
from dotenv import load_dotenv
import google.ai.generativelanguage as glm
import google.generativeai as genai

from botinfo import (
    eight_ball_list,
    newdickt,
    messages_dict,
    safety_settings,
    persona_dict,
)

load_dotenv()
MAX_MESSAGE_LENGTH = 2000  # Message length before truncation
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
GOOGLE_CSE_ID = os.getenv('GOOGLE_CSE_ID')
weather_api_key = os.getenv('WEATHER_API_KEY')
DICT_KEY = os.getenv('DICT_KEY')
GEMINI_KEY = os.getenv('GEMINI_KEY')
genai.configure(api_key=GEMINI_KEY)


async def clear_expired_messages(message_cooldown):
    while True:
        current_time = time.time()

        for user_id in newdickt.copy():
            timestamp = newdickt[user_id]["timestamp"]
            if current_time - timestamp > message_cooldown:
                del newdickt[user_id]

        for user_id in messages_dict.copy():
            timestamp = messages_dict[user_id]["timestamp"]
            if current_time - timestamp > message_cooldown:
                del messages_dict[user_id]

        await asyncio.sleep(30)


async def delete_messages(num: int, user_message: discord.Message = None, interaction: discord.Interaction = None) -> None:
    member = user_message.author if user_message else interaction.user
    channel = user_message.channel if user_message else interaction.channel

    perms = channel.permissions_for(member)
    perms = perms.manage_messages

    if interaction is not None:
        if num > 50:
            await interaction.followup.send("Sorry, you can't delete more than 50 messages at a time")
            return

        if not perms:
            reply = await interaction.followup.send(f"You don't have permission to use this command")
            await reply.delete(delay=3)
            return
        async for message in channel.history(limit=1):
            first_message = message
        deleted = await channel.purge(limit=num + 1, bulk=True, check=lambda message: message != first_message)
        await interaction.followup.send(f'Deleted {len(deleted)} message(s)')
        reply = await interaction.original_response()
        await reply.delete(delay=3)
        return
    if user_message is not None:
        if num > 50:
            await channel.send("Sorry, you can't delete more than 50 messages at a time")
            return
        if not perms:
            reply = await channel.send(f"You don't have permission to use this command")
            await asyncio.sleep(3)
            await reply.delete()
            return
        deleted = await channel.purge(limit=num + 1, bulk=True)
        reply = await channel.send(f'Deleted {len(deleted) - 1} message(s)')
        await asyncio.sleep(3)
        await reply.delete()
        return


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


async def eight_ball(message):
    eight_ball_message = random.choice(eight_ball_list)
    question = message.content[7:]
    title = f'{message.author.name}\n:8ball: 8ball'
    description = f'Q. {question}\nA. {eight_ball_message}'
    embed = discord.Embed(title=title, description=description, color=discord.Color.dark_teal())
    embed.set_footer(text=datetime.datetime.now().strftime('%m/%d/%Y %I:%M %p'))
    channel = message.channel
    await channel.send(embed=embed)


async def gemini(user_message, chat=None):
    if chat is None:
        persona = persona_dict["DAN"]["persona"]
        history = [
            {"parts": [{"text": persona[0]["content"]}],
             "role": "user"},
            {"parts": [{"text": "Adopting " + persona[0]["role"] + " persona..."}], "role": "model"}
        ]
        model = genai.GenerativeModel('gemini-pro', safety_settings=safety_settings)
        chat = model.start_chat(history=history)
        message = user_message
    else:
        message = user_message.content

    response = chat.send_message(message, safety_settings=safety_settings)

    if response.candidates and response.candidates[0].content.parts[0].function_call:
        try:
            fc = response.candidates[0].content.parts[0].function_call
            function_name = fc.name
            function_data = None

            if function_name == "get_weather":
                city = fc.args["city"]
                state = fc.args["state"]
                country = fc.args["country"]
                function_data = await get_weather(city, state, country)

            elif function_name == "search_internet":
                query = fc.args["query"]
                function_data = await search_internet(query)

            response = chat.send_message(
                glm.Content(
                    parts=[glm.Part(text=function_data)]
                ), safety_settings=safety_settings
            )
            return response.text
        except Exception as e:
            return f"Error executing function: {e}"

    else:
        return response.text


async def get_definition(word: str):
    """Merriam-Webster API. Returns word definition."""
    print(word)
    url = f'https://www.dictionaryapi.com/api/v3/references/collegiate/json/{word}?key={DICT_KEY}'

    response = requests.get(url)
    print(response.status_code)

    if response.status_code == 200:
        try:
            definitions = response.json()
            print("API response:", definitions)

            if not definitions or 'shortdef' not in definitions[0]:
                return "Nothing found"

            first_definition = definitions[0]
            short_defs = first_definition['shortdef']
            try:
                print(", ".join(str(short_def) for short_def in short_defs))
                return ", ".join(str(short_def) for short_def in short_defs)
            except:
                return "No definition found."
        except json.JSONDecodeError as e:
            return f"Error decoding JSON: {e}"
    else:
        return f"Error {response.status_code}: {response.text}"


async def get_vision(message):
    model = genai.GenerativeModel('gemini-pro-vision', safety_settings=safety_settings)
    chat = model.start_chat()

    if message.content and message.attachments:
        image_url = message.attachments[0].url
        img = await download_file_from_url(image_url)
        img = PIL.Image.open(img)
        response = chat.send_message([message.content, img], safety_settings=safety_settings)
    elif message.attachments:
        image_url = message.attachments[0].url
        img = await download_file_from_url(image_url)
        img = PIL.Image.open(img)
        response = chat.send_message(img, safety_settings=safety_settings)
    else:
        await message.reply("Please provide an image with your prompt.")
        return
    await message_reply(response.text, message)
    return


async def get_weather(city: str, state_code: str, country_code: str):
    """Get current weather data using OpenWeatherMap's API. Returns Fahrenheit ONLY."""
    print("get_weather Called: ", city, state_code, country_code)
    url = f'https://api.openweathermap.org/data/2.5/weather?q={city},{country_code}&appid={weather_api_key}&units=imperial'

    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()

        temperature = data['main']['temp']
        weather_description = data['weather'][0]['description']

        return f"{temperature} F, {weather_description}"
    else:
        return f'Unable to retrieve weather data. Status code: {response.status_code}'


async def message_reply(content, message):
    if len(content) <= MAX_MESSAGE_LENGTH:
        await message.reply(content)
    else:
        chunks = [content[i:i + MAX_MESSAGE_LENGTH] for i in range(0, len(content), MAX_MESSAGE_LENGTH)]
        await message.reply(chunks[0])
        for chunk in chunks[1:]:
            await message.channel.send(chunk)
    return


async def search_internet(query: str):
    """Search the internet using Google's API. Query returns top 3 search results."""
    print("search Called: ", query)
    num = 3  # Number of results to return
    url = f"https://www.googleapis.com/customsearch/v1?key={GOOGLE_API_KEY}&cx={GOOGLE_CSE_ID}&q={query}&num={num}"
    data = requests.get(url).json()

    search_items = data.get("items")
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
    print("search Results: ", output)
    return output

