import discord
import openai
from discord import app_commands
from botinfo import banned_users, default_persona, persona_dict, eight_ball_list, ban_reason, function_descriptions, keep_track
import wolframalpha
import datetime
import random
import json
import os
from dotenv import load_dotenv
import requests

load_dotenv()

TOKEN = os.getenv('TOKEN')
openai.api_key = os.getenv('OPEN_AI_KEY')
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
EVENT_CHANNEL_ID = int(os.getenv('EVENT_CHANNEL_ID'))
GUILD_ID = int(os.getenv('GUILD_ID'))
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
GOOGLE_CSE_ID = os.getenv('GOOGLE_CSE_ID')
APP_ID = os.getenv('APP_ID')

class MyClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

intents = discord.Intents().all()
intents.members = True
intents.guilds = True
intents.presences = True
client = MyClient(intents=intents)

@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')

@client.event
async def on_message(message):
    user_id = message.author.id
    if message.author.bot:
        return
    if message.content.startswith("?8ball "):
        response1 = random.choice(eight_ball_list)
        channel = message.channel
        timestamp_str = datetime.datetime.now().strftime('%m/%d/%Y %I:%M %p')
        title = f'{message.author.name}\n🎱 8ball'
        description = f'Q. {(message.content[7:])}\n A. {response1}'
        footer_text = f"{timestamp_str}"
        await send_embed_message(channel, title=title, description=description, footer=footer_text is not None)
        return
    if message.channel.name != 'chat-gpt':
        return
    if message.content.startswith("!"):
        return
    if message.type == discord.MessageType.pins_add:
        return
    
    # Check if the user already has a conversation, if not, create a new one
    if user_id not in keep_track:
        keep_track[user_id] = {"conversation": list(default_persona), "persona": "default"}

    conversation = keep_track[user_id]["conversation"]

    message_str = message.content

    if message.reference is not None:
        original_message = await message.channel.fetch_message(message.reference.message_id)
        conversation.append({"role": "assistant", "content": original_message.content})

    async with message.channel.typing():
        # Add the user's message to the conversation history
        conversation.append({"role": "user", "content": message_str})
        if current_persona == "Code":
            reply = await get_gpt_response(messages=conversation, function_call='none', temperature=0.2)
        else:
            reply = await get_gpt_response(messages=conversation)

        function_call = response['choices'][0]['message'].get('function_call')

        if not function_call:
            # If no function call, it's a regular assistant response
            conversation.append({"role": "assistant", "content": reply})
            await message.reply(reply)
            # Update the conversation history in the keep_track dictionary
            keep_track[user_id]["conversation"] = conversation
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

                # Add the search_results / function call to the conversation history and generate a new response
                internet_response = await get_gpt_response(messages=conversation + [{"role": "function", "name": "search_internet", "content": str(search_results)}], function_call="none")
                conversation.append({"role": "function", "name": "search_internet", "content": str(search_results)})
                conversation.append({"role": "assistant", "content": internet_response})
                await message.reply(internet_response)
                # Update the conversation history in the keep_track dictionary
                keep_track[user_id]["conversation"] = conversation
                return
            
            if function_name == 'solve_math':
                arguments_dict = json.loads(arguments)
                query = arguments_dict['query']
                wolfram_response = await get_wolfram_response(query)
                
                # Add wolfram_response / function call to the conversation history and generate a new response
                math_response = await get_gpt_response(messages=conversation + [{"role": "function", "name": "solve_math", "content": str(wolfram_response)}], function_call="none", temperature=0.2)
                conversation.append({"role": "function", "name": "solve_math", "content": str(wolfram_response)})
                conversation.append({"role": "assistant", "content": math_response})
                await message.reply(math_response)
                keep_track[user_id]["conversation"] = conversation
                return
            
async def search(query):
    print("Google Query:", query)
    page = 1
    start = (page - 1) * 10 + 1
    url = f"https://www.googleapis.com/customsearch/v1?key={GOOGLE_API_KEY}&cx={GOOGLE_CSE_ID}&q={query}&start={start}"
    data = requests.get(url).json()
    
    search_items = data.get("items")
    results = []

    for i, search_item in enumerate(search_items, start=1):
        title = search_item.get("title", "N/A")
        snippet = search_item.get("snippet", "N/A")
        long_description = search_item.get("pagemap", {}).get("metatags", [{}])[0].get("og:description", "N/A")
        link = search_item.get("link", "N/A")
        
        result_str = f"Result {i+start-1}: {title}\n"
        
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

    response = requests.get(url)
    if response.status_code == 200:
        output = response.text.strip()
        print("Wolfram Response:", output)
        return output
    else:
        print("No short answer available, trying backup...")
        output = await backup_wolfram(query)
        return output
        
async def backup_wolfram(query):
    print("Backup Wolfram Query:", query)
    client = wolframalpha.Client(APP_ID)
    res = client.query(query)
    try:
        answer = next(res.results).text
    except:
        print("Error: No result found")
        return "Error: No result found"
    print("Wolfram Response:", answer)
    return answer
    
async def get_gpt_response(messages, function_call='auto', temperature=0.5, max_tokens=850):
    global response
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo-16k-0613",
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

async def handle_member_event(event_type, member):
    guild = client.get_guild(GUILD_ID)
    message_text = None
    channel = client.get_channel(EVENT_CHANNEL_ID)
    timestamp_str = datetime.datetime.now().strftime('%m/%d/%Y %I:%M %p')
    log_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_mention = member.name + '#' + member.discriminator
    pfp = member.display_avatar.url

    banned_users.clear() # Clear the list to ensure updated information
    bans = guild.bans()  # Get the list of banned users in the guild
    async for ban_entry in bans:
        banned_users.append(ban_entry.user)

    if event_type == "join":
        title = "Member Joined"
        description = f"{member.mention} has joined the server!"
        color = discord.Color.green()
        footer_text = f"{timestamp_str} | {channel.guild.name} | {len(channel.guild.members)} members"
        message_text = "Welcome to the server!" if member.joined_at is None else "Welcome back to the server!"
    elif event_type == "ban":
        title = "Member Banned"
        ban_entry = None
        description = ''
        for user in banned_users:
            if user.id == member.id:
                ban_entry = user
                break
        global ban_reason
        if ban_reason != None:
            description = f"{member.mention} has been banned for playing {ban_reason}."
            ban_reason = None
        else:
            description = f"{member.mention} has been banned."
        color = discord.Color.red()
        footer_text = f"{timestamp_str} | {channel.guild.name} | {len(channel.guild.members)} members"
    elif event_type == "leave":
        title = "Member Left"
        description = f"{member.mention} has left the server."
        color = discord.Color.red()
        footer_text = f"{timestamp_str} | {channel.guild.name} | {len(channel.guild.members)} members"
        if member.bot:
            return
        if member.id in [user.id for user in banned_users]:
            return
    elif event_type == "unban":
        title = "Member Unbanned"
        description = f"{member.mention} has been unbanned from the server."
        color = discord.Color.green()
        footer_text = f"{timestamp_str} | {channel.guild.name} | {len(channel.guild.members)} members"
    
    if message_text != None:
        try:
            await member.send(message_text)
        except discord.Forbidden:
            print(f'Could not send message to {log_mention}')

    embed = discord.Embed(title=title, description=description, color=color)
    if pfp:
        embed.set_thumbnail(url=pfp)

    await send_embed_message(channel, title=title, description=description, thumbnail_url=pfp, footer=footer_text is not None)
    print(f'\x1b[38;2;153;157;165m\x1b[1m{log_time}\x1b[0m \x1b[38;2;255;25;25m\x1b[1m{event_type.upper()}\x1b[0m         \x1b[1m{log_mention}\x1b[0m')

@client.event
async def on_member_join(member):
    await handle_member_event("join", member)

@client.event
async def on_member_ban(member):
    await handle_member_event("ban", member)

@client.event
async def on_member_remove(member):
    await handle_member_event("leave", member)

@client.event
async def on_member_unban(member):
    await handle_member_event("unban", member)

@client.tree.command()
async def ping(interaction: discord.Interaction):
   """Shows the bot's latency"""
   bot_latency = round(client.latency * 1000)
   await interaction.response.send_message(f"Pong! `{bot_latency}ms`")

@client.tree.command(name='personas')
@app_commands.describe(option="Which to choose..")
@app_commands.choices(option=[
        app_commands.Choice(name="Current Persona", value="1"),
        app_commands.Choice(name="Republican", value="2"),
        app_commands.Choice(name="Chef", value="3"),
        app_commands.Choice(name="Math", value="4"),
        app_commands.Choice(name="Code", value="5"),
        app_commands.Choice(name="Default", value="6"),
    ])
async def personas(interaction: discord.Interaction, option: app_commands.Choice[str]):
    """
        Choose a persona

    """
    global current_persona
    for persona in persona_dict.values():
        if persona['value'] == option.value:
            current_persona = persona['name']
            break

    if option.value in [persona_info["value"] for persona_info in persona_dict.values()]:
        current_persona = next((persona_info["name"] for persona_info in persona_dict.values() if persona_info["value"] == option.value), None)
        if current_persona:
            persona = persona_dict[f"{current_persona}"]["persona"]
            # Update the user's conversation and persona in the keep_track dictionary
            user_id = interaction.user.id
            keep_track[user_id] = {"conversation": list(persona), "persona": current_persona}
            await interaction.response.send_message(f"Persona changed to **{current_persona}**.")
            return

    if option.value == '1':
        user_id = interaction.user.id
        if user_id not in keep_track:
            current_per = "Default"
        else:
            current_per = keep_track[user_id]["persona"]
        response = f"**Current Persona:** {current_per}"
        await interaction.response.send_message(response)
        return
    
@client.tree.command(name='gpt')
@app_commands.describe(persona="Which persona to choose..")
@app_commands.choices(persona=[
        app_commands.Choice(name="Republican", value="2"),
        app_commands.Choice(name="Chef", value="3"),
        app_commands.Choice(name="Math", value="4"),
    ])
async def gpt(interaction: discord.Interaction, message: str, persona: app_commands.Choice[str] = None):
    """
    Ask ChatGPT a question

    Args:
        message (str): Your question
        persona (Optional[app_commands.Choice[str]]): Choose a persona
    """
    await interaction.response.send_message("<a:typing:1136369547973234708>")
    message_str = str(message)
    if persona:
        for persona_data in persona_dict.values():
            if persona_data['value'] == persona.value:
                current_persona = persona_data['name']
                selected_persona = persona_dict[f"{current_persona}"]["persona"]
                conversation = list(selected_persona)
                break
    else:
        conversation = list(default_persona)
    conversation.append({"role": "user", "content": message_str})
    reply = await get_gpt_response(messages=conversation)
    function_call = response['choices'][0]['message'].get('function_call')
    if not function_call:
            await interaction.edit_original_response(content=f'*{interaction.user.mention} - {message_str}*\n\n**"{reply}"**')
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
                internet_response = await get_gpt_response(messages=conversation + [{"role": "function", "name": "search_internet", "content": str(search_results)}], function_call="none")
                await interaction.edit_original_response(content=f'*{interaction.user.mention} - {message_str}*\n\n**"{internet_response}"**')
                return
            if function_name == 'solve_math':
                # Extract the necessary arguments from the generated JSON
                arguments_dict = json.loads(arguments)
                query = arguments_dict['query']
                wolfram_response = await get_wolfram_response(query)
                
                # Add wolfram_response to the conversation history and generate a new response
                math_response = await get_gpt_response(messages=conversation + [{"role": "function", "name": "solve_math", "content": str(wolfram_response)}], function_call="none", temperature=0.2)
                await interaction.edit_original_response(content=f'*{interaction.user.mention} - {message_str}*\n\n**"{math_response}"**')
                return

client.run(TOKEN)