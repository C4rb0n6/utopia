import asyncio
import os
import time

import discord
from discord import app_commands, HTTPException
from dotenv import load_dotenv
import google.generativeai as genai

from botinfo import (
    help_instructions,
    messages_dict,
    tools,
    safety_settings,
    persona_dict,
)
from functions import (
    clear_expired_messages,
    delete_messages,
    eight_ball,
    gemini,
    get_vision,
    message_reply,
    newdickt,
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
async def on_message(message: discord.Message) -> None:
    user_id = message.author.id
    timestamp = time.time()

    if message.author.bot:
        return

    if message.content.startswith("?8ball "):
        await eight_ball(message)
        return

    if message.content.lower().startswith("?clear "):
        await delete_messages(int(message.content[7:]), message)
        return

    if message.content.startswith("!"):
        return

    if message.channel.topic is None or message.channel.topic.lower() != 'gemini':
        return

    if user_id not in newdickt:
        newdickt[user_id] = {"chat-model": "Gemini Pro", "timestamp": timestamp}
    else:
        newdickt[user_id]["timestamp"] = timestamp

    if user_id not in messages_dict:
        model = genai.GenerativeModel('gemini-pro', safety_settings=safety_settings)
        chat = model.start_chat()
        messages_dict[user_id] = {"chat": chat, "user_id": user_id, "messages": [], "persona": None,
                                  "timestamp": timestamp}

    newdickt[user_id]["timestamp"] = timestamp
    messages_dict[user_id]["timestamp"] = timestamp
    chat_model = newdickt[user_id]["chat-model"]
    chat = messages_dict[user_id]["chat"]
    async with message.channel.typing():
        if chat_model == "Gemini Pro Function Calling":
            model = genai.GenerativeModel('gemini-pro', safety_settings=safety_settings, tools=tools)
            chat = model.start_chat()
            messages_dict[user_id] = {"chat": chat, "user_id": user_id, "messages": [], "persona": None,
                                      "timestamp": timestamp}
        elif chat_model == "Gemini Pro Vision":
            async with message.channel.typing():
                await get_vision(message)
                return
        response = await gemini(message, chat)
        await message_reply(response, message)


@client.tree.command()
async def clear(interaction: discord.Interaction, messages: int) -> None:
    """Clears a number of messages"""
    await interaction.response.defer()
    await delete_messages(messages, None, interaction)


@client.tree.command()
async def gemini_clear(interaction: discord.Interaction) -> None:
    """Clears your Gemini chat history"""
    await interaction.response.defer()
    user_id = interaction.user.id
    try:
        del newdickt[user_id]
        del messages_dict[user_id]
        await interaction.followup.send(f"Cleared chat history for **" + interaction.user.name + "**")
    except KeyError:
        await interaction.followup.send(f"User ID not found for **" + interaction.user.name + "**")


@client.tree.command(name='gpt')
async def gpt(interaction: discord.Interaction, message: str) -> None:
    """
    Ask Gemini a question

    Args:
        message (str): Your question
    """
    await interaction.response.defer()
    message_str = str(message)

    response = await gemini(message_str)

    try:
        await interaction.followup.send(
            content=f'***{interaction.user.mention} - {message_str}***\n\n{response}')
    except HTTPException as e:
        print(f"GPT Error: {e}")
        await interaction.followup.send(
            content=f'***{interaction.user.mention} - {message_str}***\n\n {e}')


@client.tree.command()
async def help(interaction: discord.Interaction) -> None:
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


@client.tree.command(name='model')
@app_commands.describe(option="Which to choose..")
@app_commands.choices(option=[
    app_commands.Choice(name="Gemini Pro", value="1"),
    app_commands.Choice(name="Gemini Pro Vision", value="2"),
    app_commands.Choice(name="Gemini Pro Function Calling", value="3")
])
async def model(interaction: discord.Interaction, option: app_commands.Choice[str]) -> None:
    """
        Choose a model

    """
    timestamp = time.time()
    user_id = interaction.user.id
    selected_model = option.name

    if user_id not in newdickt:
        if selected_model == "Gemini Pro Vision":
            await interaction.response.send_message(
                f":warning: *(this is not an error)* **{selected_model}** does not support multi-turn conversations. Attach both your image and prompt to one message.")
            newdickt[user_id] = {"chat-model": option.name, "timestamp": timestamp}
            return
        newdickt[user_id] = {"chat-model": option.name, "timestamp": timestamp}
        await interaction.response.send_message(f"Model changed to **{selected_model}**.")
    else:
        chat_model = newdickt[user_id]["chat-model"]

        if chat_model == selected_model:
            await interaction.response.send_message(f"**{selected_model}** is already selected.")
        else:
            if selected_model == "Gemini Pro Vision":
                await interaction.response.send_message(
                    f":warning: *(this is not an error)* **{selected_model}** does not support multi-turn conversations. Attach both your image and prompt to one message.")
                newdickt[user_id]["chat-model"] = selected_model
                return
            newdickt[user_id]["chat-model"] = selected_model
            await interaction.response.send_message(f"Model changed to **{selected_model}**.")


@client.tree.command(name='personas')
@app_commands.describe(option="Which to choose..")
@app_commands.choices(option=[
    app_commands.Choice(name="Current Persona", value="1"),
    *[
        app_commands.Choice(name=persona_info["name"], value=persona_info["value"])
        for persona_info in persona_dict.values()
    ]
])
async def personas(interaction: discord.Interaction, option: app_commands.Choice[str]) -> None:
    """
        Choose a persona

    """
    timestamp = time.time()
    await interaction.response.defer()
    user_id = interaction.user.id

    current_persona = next((persona_info["name"] for persona_info in persona_dict.values() if option.name in persona_info["name"]), None)

    if current_persona:
        persona = persona_dict[f"{current_persona}"]["persona"]
        history = [
            {"parts": [{"text": persona[0]["content"]}],
             "role": "user"},
            {"parts": [{"text": "Adopting " + persona[0]["role"] + " persona..."}], "role": "model"}
        ]
        model = genai.GenerativeModel('gemini-pro', safety_settings=safety_settings)
        chat = model.start_chat(history=history)
        messages_dict[user_id] = {"chat": chat, "user_id": user_id, "messages": [], "persona": current_persona,
                                  "timestamp": timestamp}
        await interaction.followup.send(f"Persona changed to **{current_persona}**.")
        return

    else:
        if user_id not in messages_dict:
            display_persona = "Default"
        else:
            display_persona = messages_dict[user_id]["persona"]

        response = f"**Current Persona:** {display_persona}"
        await interaction.followup.send(response)
        return


@client.tree.command()
async def ping(interaction: discord.Interaction) -> None:
    """Returns the bot latency"""
    await interaction.response.defer()
    bot_latency = round(client.latency * 1000)
    await interaction.followup.send(f"Pong! `{bot_latency}ms`")

client.run(TOKEN)
