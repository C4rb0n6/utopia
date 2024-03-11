import os
import time

import asyncio
import discord

from discord import app_commands
from dotenv import load_dotenv
import google.generativeai as genai

from botinfo import (
    help_instructions,
    messages_dict,
)

from functions import(
    clear_expired_messages,
    eight_ball,
    gemini,
    message_reply,
    search,
    get_word_definition,
    get_weather,
)

load_dotenv()

message_cooldown = 1200  # time to clear all message related dicts(keep_track, newdickt, vision_dict)

TOKEN = os.getenv('TOKEN')
GEMINI_KEY = os.getenv('GEMINI_KEY')
guild_ids_str = os.getenv("GUILD_IDS")
GUILD_IDS = [int(guild_id) for guild_id in guild_ids_str.split(",")]


class MyClient(discord.Client):
    def __init__(self, *, intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.guild_ids = GUILD_IDS

    async def setup_hook(self):
        for guild_id in self.guild_ids:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)


intents = discord.Intents().all()
client = MyClient(intents=intents)
genai.configure(api_key=GEMINI_KEY)


@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')
    asyncio.create_task(clear_expired_messages(message_cooldown))

@client.event
async def on_message(message):
    user_id = message.author.id
    timestamp = time.time()

    if message.content.startswith("?8ball "):
        await eight_ball(message)
        return

    if message.author.bot:
        return

    if message.channel.name != 'chat-gpt':
        return

    if message.content.startswith("!"):
        return

    if message.type == discord.MessageType.pins_add:
        return

    if user_id not in messages_dict:
        #model = genai.GenerativeModel('gemini-pro',
                                      #tools=[search, get_weather, get_word_definition])
        model = genai.GenerativeModel('gemini-pro')
        chat = model.start_chat()
        messages_dict[user_id] = {"chat": chat, "user_id": user_id, "messages": [], "timestamp": timestamp}

    chat = messages_dict[user_id]["chat"]
    async with message.channel.typing():
        response = await gemini(message, chat)
        await message_reply(response, message)
        return


# @client.tree.command(name='gpt')
# @app_commands.describe(persona="Which persona to choose..")
# async def gpt(interaction: discord.Interaction, message: str):
#     """
#     Ask Gemini a question
#
#     Args:
#         message (str): Your question
#     """
#     await interaction.response.defer()
#     message_str = str(message)
#
#     response = await get_gpt_response(message_str, persona)
#
#     try:
#         await interaction.followup.send(
#             content=f'***{interaction.user.mention} - {message_str}***\n\n{response}')
#     except:
#         await interaction.followup.send(
#             content=f'***{interaction.user.mention} - {message_str}***\n\n shit too long idk bro')
#     return


# @client.tree.command(name='model')
# @app_commands.describe(option="Which to choose..")
# @app_commands.choices(option=[
#     app_commands.Choice(name="GPT-4 Turbo", value="1"),
#     app_commands.Choice(name="GPT-4 Vision", value="2"),
#     app_commands.Choice(name="GPT-3.5 Turbo", value="3"),
# ])
# async def model(interaction: discord.Interaction, option: app_commands.Choice[str]):
#     """
#         Choose a model
#
#     """
#     timestamp = time.time()
#     user_id = interaction.user.id
#     selected_model = option.name
#
#     if user_id not in newdickt:
#         newdickt[user_id] = {"chat-model": option.name, "timestamp": timestamp}
#         await interaction.response.send_message(f"Model changed to **{selected_model}**.")
#     else:
#         chat_model = newdickt[user_id]["chat-model"]
#
#         if chat_model == selected_model:
#             await interaction.response.send_message(f"**{selected_model}** is already selected.")
#         else:
#             newdickt[user_id]["chat-model"] = selected_model
#             await interaction.response.send_message(f"Model changed to **{selected_model}**.")


# @client.tree.command(name='personas')
# @app_commands.describe(option="Which to choose..")
# @app_commands.choices(option=[
#     app_commands.Choice(name="Current Persona", value="1"),
#     *[
#         app_commands.Choice(name=persona_info["name"], value=persona_info["value"])
#         for persona_info in persona_dict.values()
#     ]
# ])
# async def personas(interaction: discord.Interaction, option: app_commands.Choice[str]):
#     """
#         Choose a persona
#
#     """
#     timestamp = time.time()
#     await interaction.response.defer()
#
#     current_persona = next((persona_info["name"] for persona_info in persona_dict.values() if option.name in persona_info["name"]), None)
#
#     if current_persona:
#         persona = persona_dict[f"{current_persona}"]["persona"]
#         user_id = interaction.user.id
#         thread = await create_thread()
#         keep_track[user_id] = {"thread": thread.id, "instructions": persona[0]["content"], "persona": current_persona, "timestamp": timestamp}
#         await interaction.followup.send(f"Persona changed to **{current_persona}**.")
#         return
#
#     else:
#         user_id = interaction.user.id
#
#         if user_id not in keep_track:
#             current_per = "Default"
#         else:
#             current_per = keep_track[user_id]["persona"]
#
#         response = f"**Current Persona:** {current_per}"
#         await interaction.followup.send(response)
#         return


@client.tree.command()
async def help(interaction: discord.Interaction):
    """Returns list of commands"""
    await interaction.response.defer()
    chat_gpt_channel = discord.utils.get(interaction.guild.channels, name="chat-gpt")
    if chat_gpt_channel:
        channel_link = f'https://discord.com/channels/{interaction.guild.id}/{chat_gpt_channel.id}'
        instructions = f"""
## **Commands:**
**?8ball**: Classic 8-ball responses. (e.g., `?8ball popeyes?`).
**/ping**: Check bot latency. Type `/ping`.
**/model [model_name]**: Switch chat models (e.g., `/model GPT-4 Turbo`).
**/personas [persona_name]**: Change bot personality (e.g., `/personas DAN`).
**/gpt [message] [--persona_name]**: Simplified chat with optional persona.

- Adding the "!" prefix before messages will instruct the bot to ignore those messages in {channel_link}
"""

        await interaction.followup.send(content=instructions)
    else:
        await interaction.followup.send(content=help_instructions)


@client.tree.command()
async def ping(interaction: discord.Interaction):
    """Returns the bot latency"""
    await interaction.response.defer()
    bot_latency = round(client.latency * 1000)
    await interaction.followup.send(f"Pong! `{bot_latency}ms`")

client.run(TOKEN)
