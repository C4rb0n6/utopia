import discord
import openai
from discord import app_commands
from botinfo import default_persona, persona_dict, eight_ball_list, function_descriptions, keep_track, newdickt
import asyncio
import time
import wolframalpha
import datetime
import random
import json
import os
from dotenv import load_dotenv
import requests

load_dotenv()

message_cooldown = 900  # time to clear keep_safe dict (15 minutes in seconds)
MAX_MESSAGE_LENGTH = 2000  # 2000 characters
TOKEN = os.getenv('TOKEN')
openai.api_key = os.getenv('OPEN_AI_KEY')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
GOOGLE_CSE_ID = os.getenv('GOOGLE_CSE_ID')
APP_ID = os.getenv('APP_ID')
GUILD1 = os.getenv("GUILD1")
GUILD2 = os.getenv("GUILD2")
GUILD_ID = [GUILD1, GUILD2]


class MyClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
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


@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')
    asyncio.create_task(clear_expired_messages(message_cooldown))


@client.event
async def on_message(message):
    timestamp = time.time()  # Timestamp for keeping track of how long users are kept in keep_track
    user_id = message.author.id

    if message.author.bot:
        return

    if message.content.startswith("?8ball "):
        await eight_ball(message)
        return

    if message.channel.name != 'chat-gpt':
        return

    if message.content.startswith("!"):
        return

    if message.type == discord.MessageType.pins_add:
        return

    # Check if the user already has a conversation, if not, create a new one
    if user_id not in keep_track:
        current_date = datetime.datetime.now(datetime.timezone.utc)
        date = f"This is real-time data: {current_date}, use it wisely to find better solutions."
        default_persona_copy = [person.copy() for person in default_persona]  # Create "deep copy"
        default_persona_copy[0]["content"] += " " + date
        keep_track[user_id] = {"conversation": default_persona_copy, "persona": "default", "timestamp": timestamp}
    keep_track[user_id]["timestamp"] = timestamp
    print(keep_track[user_id])
    if user_id not in newdickt:
        newdickt[user_id] = {"chatmodel": "GPT-3.5", "counter": 0}

    model = newdickt[user_id]["chatmodel"]

    if model == "GPT-3.5":
        gpt4 = False
    else:  # If user not is using GPT-3.5 then keep track of their message count on GPT-4
        gpt4 = True
        newdickt[user_id]['counter'] += 1

        if newdickt[user_id]['counter'] > 5:  # Might add message cap later
            pass

        mention = message.author.display_name
        print(f"{mention} is on {newdickt[user_id]['counter']} GPT-4 Message(s)")

    conversation = keep_track[user_id]["conversation"]
    message_str = message.content

    # If the message is a reply append the parent message to the convo
    if message.reference is not None:
        original_message = await message.channel.fetch_message(message.reference.message_id)
        conversation.append({"role": "assistant", "content": original_message.content})

    async with message.channel.typing():
        # Add the user's message to the conversation history
        conversation.append({"role": "user", "content": message_str})
        if gpt4:
            reply = await get_gpt_response(messages=conversation, model="gpt-4-0613")
        else:
            reply = await get_gpt_response(messages=conversation)
        function_call = response['choices'][0]['message'].get('function_call')

        if not function_call:
            conversation.append({"role": "assistant", "content": reply})
            content = reply
            await message_reply(content, message)
            keep_track[user_id]["conversation"] = conversation
            return
        else:
            # Extract the function name and arguments
            function_name = function_call['name']
            arguments = function_call['arguments']

            # Check if the function name matches search
            if function_name == 'search_internet':
                content = await internet(arguments, gpt4, conversation, user_id)
                await message_reply(content, message)
                return

            # Check if the function name matches wolfram
            if function_name == 'solve_math':
                content = await math(arguments, gpt4, conversation, user_id)
                await message_reply(content, message)
                return


# Define a coroutine to periodically check and remove expired messages
async def clear_expired_messages(message_cooldown):
    while True:
        current_time = time.time()

        for user_id, data in keep_track.copy().items():
            timestamp = data["timestamp"]
            if current_time - timestamp > message_cooldown:
                del keep_track[user_id]

        await asyncio.sleep(30)  # Adjust the sleep interval as needed


async def eight_ball(message):
    eight_ball_message = random.choice(eight_ball_list)
    channel = message.channel
    timestamp_str = datetime.datetime.now().strftime('%m/%d/%Y %I:%M %p')
    title = f'{message.author.name}\n:8ball: 8ball'
    description = f'Q. {(message.content[7:])}\n A. {eight_ball_message}'
    footer_text = f"{timestamp_str}"
    await send_embed_message(channel, title=title, description=description, footer=footer_text is not None)
    return


async def internet(arguments, gpt4, conversation, user_id):
    arguments_dict = json.loads(arguments)
    query = arguments_dict['query']
    search_results = await search(query)

    if gpt4:
        internet_response = await get_gpt_response(
            messages=conversation + [{"role": "function", "name": "search_internet", "content": str(search_results)}],
            function_call="none", model="gpt-4-0613")
    else:
        internet_response = await get_gpt_response(
            messages=conversation + [{"role": "function", "name": "search_internet", "content": str(search_results)}],
            function_call="none")

    conversation.append({"role": "function", "name": "search_internet", "content": str(search_results)})
    conversation.append({"role": "assistant", "content": internet_response})
    keep_track[user_id]["conversation"] = conversation
    return internet_response


async def math(arguments, gpt4, conversation, user_id):
    arguments_dict = json.loads(arguments)
    query = arguments_dict['query']
    wolfram_response = await get_wolfram_response(query)

    if gpt4:
        math_response = await get_gpt_response(
            messages=conversation + [{"role": "function", "name": "solve_math", "content": str(wolfram_response)}],
            function_call="none", temperature=0.2, model="gpt-4-0613")
    else:
        math_response = await get_gpt_response(
            messages=conversation + [{"role": "function", "name": "solve_math", "content": str(wolfram_response)}],
            function_call="none", temperature=0.2)

    conversation.append({"role": "function", "name": "solve_math", "content": str(wolfram_response)})
    conversation.append({"role": "assistant", "content": math_response})
    keep_track[user_id]["conversation"] = conversation
    return math_response


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


async def get_wolfram_response(query):
    print("Wolfram Query:", query)
    app_id = APP_ID
    query_encoded = query.replace(" ", "+")

    url = f"http://api.wolframalpha.com/v1/result?appid={app_id}&i={query_encoded}"

    wolfram_data = requests.get(url)

    if wolfram_data.status_code == 200:
        short_answer = wolfram_data.text.strip()
        print("Wolfram Response:", short_answer)
        return short_answer
    else:
        print("No short answer available, trying backup...")
        long_answer = await backup_wolfram(query)
        return long_answer


async def backup_wolfram(query):
    print("Backup Wolfram Query:", query)
    client = wolframalpha.Client(APP_ID)
    wolfram_data = client.query(query)

    try:
        answer = next(wolfram_data.results).text
    except:
        print("Error: No result found")
        return "Error: No result found"

    print("Wolfram Response:", answer)
    return answer


async def get_gpt_response(messages, model="gpt-3.5-turbo-16k-0613", function_call='auto', temperature=0.5,
                           max_tokens=2500):
    global response
    response = await openai.ChatCompletion.acreate(
        model=model,
        messages=messages,
        functions=function_descriptions,
        function_call=function_call,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response['choices'][0]['message']['content']


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


@client.tree.command(name='model')
@app_commands.describe(option="Which to choose..")
@app_commands.choices(option=[
    app_commands.Choice(name="GPT-3.5", value="1"),
    app_commands.Choice(name="GPT-4", value="2"),
])
async def model(interaction: discord.Interaction, option: app_commands.Choice[str]):
    """
        Choose a model

    """
    user_id = interaction.user.id
    selected_model = None

    if user_id not in newdickt:
        newdickt[user_id] = {"chatmodel": option.name, "counter": 0}
        selected_model = option.name
        chatmodel = option.name
        await interaction.response.send_message(f"Model changed to **{selected_model}**.")
    else:
        chatmodel = newdickt[user_id]["chatmodel"]

        if option.value == '1':
            selected_model = option.name
        elif option.value == '2':
            selected_model = option.name

        if chatmodel == selected_model:
            await interaction.response.send_message(f"**{selected_model}** is already selected.")
        else:
            newdickt[user_id]["chatmodel"] = selected_model
            await interaction.response.send_message(f"Model changed to **{selected_model}**.")

    print(newdickt[user_id]["chatmodel"])


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
            keep_track[user_id] = {"conversation": list(persona), "persona": current_persona, "timestamp": timestamp}
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


@client.tree.command(name='gpt')
@app_commands.describe(persona="Which persona to choose..", model="Which model to choose..")
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
    ],
    model=[
        app_commands.Choice(name="GPT-3.5", value="17"),
        app_commands.Choice(name="GPT-4", value="18"),
    ]
)
async def gpt(interaction: discord.Interaction, message: str, persona: app_commands.Choice[str] = None, model: app_commands.Choice[str] = None):
    """
    Ask ChatGPT a question

    Args:
        message (str): Your question
        persona (Optional[app_commands.Choice[str]]): Choose a persona
        model (Optional[app_commands.Choice[str]]): Choose a model
    """
    await interaction.response.defer()
    message_str = str(message)

    if persona:
        for persona_data in persona_dict.values():

            if persona_data['value'] == persona.value:
                current_persona = persona_data['name']
                selected_persona = persona_dict[f"{current_persona}"]["persona"]
                conversation = list(selected_persona)
                break
    else:
        current_date = datetime.datetime.now(datetime.timezone.utc)
        date = f"This is real-time data: {current_date}, use it wisely to find better solutions."
        default_persona_copy = [person.copy() for person in default_persona]  # Create "deep copy"
        default_persona_copy[0]["content"] += " " + date
        conversation = default_persona_copy

    if model.value == '17':
        selected_model = model.name
    elif model.value == '18':
        selected_model = model.name

    conversation.append({"role": "user", "content": message_str})
    if selected_model == "GPT-4":
        reply = await get_gpt_response(messages=conversation, model="gpt-4-0613")
    else:
        reply = await get_gpt_response(messages=conversation)
    function_call = response['choices'][0]['message'].get('function_call')

    if not function_call:
        await interaction.followup.send(content=f'*{interaction.user.mention} - {message_str}*\n\n**"{reply}"**')
        return
    else:
        # Extract the function name and arguments
        function_name = function_call['name']
        arguments = function_call['arguments']
        # Check if the function name matches your search function

        if function_name == 'search_internet':
            # Extract the necessary arguments from the generated JSON
            arguments_dict = json.loads(arguments)
            query = arguments_dict['query']
            search_results = await search(query)
            # Add search_results to the conversation history
            internet_response = await get_gpt_response(messages=conversation + [
                {"role": "function", "name": "search_internet", "content": str(search_results)}], function_call="none")
            await interaction.followup.send(
                content=f'*{interaction.user.mention} - {message_str}*\n\n**"{internet_response}"**')
            return

        if function_name == 'solve_math':
            # Extract the necessary arguments from the generated JSON
            arguments_dict = json.loads(arguments)
            query = arguments_dict['query']
            wolfram_response = await get_wolfram_response(query)
            # Add wolfram_response to the conversation history and generate a new response
            math_response = await get_gpt_response(
                messages=conversation + [{"role": "function", "name": "solve_math", "content": str(wolfram_response)}],
                function_call="none", temperature=0.2)
            await interaction.followup.send(
                content=f'*{interaction.user.mention} - {message_str}*\n\n**"{math_response}"**')
            return


client.run(TOKEN)
