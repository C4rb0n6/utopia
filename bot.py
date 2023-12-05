import datetime
import json
import os
import time

import asyncio
import discord

from discord import app_commands
from dotenv import load_dotenv
from openai import AsyncOpenAI

from botinfo import (
    keep_track,
    persona_dict,
    newdickt,
    help_instructions,
)

from functions import(
    clear_expired_messages,
    eight_ball,
    assistant_response,
    format_response,
    download_file_from_url,
    create_thread,
    create_assistant,
    get_weather,
    get_default_persona,
    get_vision,
    search,
)

load_dotenv()

message_cooldown = 1200  # time to clear all message related dicts(keep_track, newdickt, vision_dict)

TOKEN = os.getenv('TOKEN')
vanc_key = os.getenv('VANC_KEY')
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


@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')
    asyncio.create_task(clear_expired_messages(message_cooldown))

@client.event
async def on_message(message):
    user_files = None
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

    async with message.channel.typing():
        if message.attachments:
            user_files = []
            print(message.attachments)
            for attachment in message.attachments:
                file_content = await download_file_from_url(attachment.url)
                file = await open_ai_client.files.create(file=file_content, purpose='assistants')
                user_files.append(file.id)
            print(user_files)

        if user_id not in newdickt:
            newdickt[user_id] = {"chat-model": "GPT-3.5 Turbo", "timestamp": timestamp}
        else:
            newdickt[user_id]["timestamp"] = timestamp
            chat_model = newdickt[user_id]["chat-model"]
            if chat_model == "GPT-4 Vision":
                print("meow")
                async with message.channel.typing():
                    await get_vision(message)
                    return

        if user_id not in keep_track:
            thread = await create_thread()
            instructions = await get_default_persona()
            print(instructions)
            chat_model = newdickt[user_id]["chat-model"]
            assistant = await create_assistant(chat_model)
            keep_track[user_id] = {"thread": thread.id, "instructions": instructions, "persona": "Default",
                                   "timestamp": timestamp, "has_assistant": assistant}
        else:
            try:
                assistant = keep_track[user_id]["has_assistant"]
            except KeyError:
                keep_track[user_id]["has_assistant"] = await create_assistant()
                assistant = keep_track[user_id]["has_assistant"]
            instructions = keep_track[user_id]["instructions"]
            print(instructions)
            chat_model = newdickt[user_id]["chat-model"]
            keep_track[user_id]["timestamp"] = timestamp

            current_model_mapping = {
                "gpt-3.5-turbo-1106": "GPT-3.5 Turbo",
                "gpt-4-1106-preview": "GPT-4 Turbo",
            }

            current_model = current_model_mapping.get(assistant.model, assistant.model)

            if chat_model != current_model:
                thread = await create_thread()
                assistant = await create_assistant(chat_model)
                keep_track[user_id]["thread"] = thread.id
                keep_track[user_id]["has_assistant"] = assistant

        if user_files:
            await assistant_response(message, instructions, user_files)
        else:
            await assistant_response(message, instructions)

        await format_response(message)
        return


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

    assistant = await create_assistant("GPT-4 Turbo")

    run = await open_ai_client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant.id,
        instructions=instructions
    )

    while run.status != "completed":
        if run.status == "failed":
            print(run.last_error)
            print("failed")
            await interaction.followup.send("shit broke idk, ask a better question loser")
            return
        print(run.status)
        await asyncio.sleep(0.5)

        run = await open_ai_client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id
        )

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

            await open_ai_client.beta.threads.runs.submit_tool_outputs(
                thread_id=thread.id,
                run_id=run.id,
                tool_outputs=tool_call_list
            )

    gpt_messages = await open_ai_client.beta.threads.messages.list(thread_id=thread.id)
    for msg in gpt_messages.data:
        if msg.role == "assistant":
            try:
                await interaction.followup.send(
                    content=f'***{interaction.user.mention} - {message_str}***\n\n{msg.content[0].text.value}')
            except:
                await interaction.followup.send(
                    content=f'***{interaction.user.mention} - {message_str}***\n\n shit too long idk bro')
            return


@client.tree.command(name='model')
@app_commands.describe(option="Which to choose..")
@app_commands.choices(option=[
    app_commands.Choice(name="GPT-4 Turbo", value="1"),
    app_commands.Choice(name="GPT-4 Vision", value="2"),
    app_commands.Choice(name="GPT-3.5 Turbo", value="3"),
])
async def model(interaction: discord.Interaction, option: app_commands.Choice[str]):
    """
        Choose a model

    """
    timestamp = time.time()
    user_id = interaction.user.id
    selected_model = option.name

    if user_id not in newdickt:
        newdickt[user_id] = {"chat-model": option.name, "timestamp": timestamp}
        await interaction.response.send_message(f"Model changed to **{selected_model}**.")
    else:
        chat_model = newdickt[user_id]["chat-model"]

        if chat_model == selected_model:
            await interaction.response.send_message(f"**{selected_model}** is already selected.")
        else:
            newdickt[user_id]["chat-model"] = selected_model
            await interaction.response.send_message(f"Model changed to **{selected_model}**.")


@client.tree.command(name='personas')
@app_commands.describe(option="Which to choose..")
@app_commands.choices(option=[
    app_commands.Choice(name="Current Persona", value="1"),
    app_commands.Choice(name="Republican", value="2"),
    app_commands.Choice(name="Math", value="4"),
    app_commands.Choice(name="Code", value="5"),
    app_commands.Choice(name="Ego", value="9"),
    app_commands.Choice(name="Fitness Trainer", value="12"),
    app_commands.Choice(name="Gordon Ramsay", value="13"),
    app_commands.Choice(name="DAN", value="14"),
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


@client.tree.command()
async def help(interaction: discord.Interaction):
    """Returns list of commands"""
    await interaction.response.defer()
    await interaction.followup.send(f"{help_instructions}")


@client.tree.command()
async def ping(interaction: discord.Interaction):
    """Returns the bot latency"""
    await interaction.response.defer()
    bot_latency = round(client.latency * 1000)
    await interaction.followup.send(f"Pong! `{bot_latency}ms`")

client.run(TOKEN)
