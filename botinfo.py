import google.ai.generativelanguage as glm

eight_ball_list = [
    "It is certain",
    "Without a doubt",
    "You may rely on it",
    "Yes definitely",
    "It is decidedly so",
    "As I see it, yes",
    "Most likely",
    "Yes",
    "Outlook good",
    "Signs point to yes",
    "Reply hazy try again",
    "Better not tell you now",
    "Ask again later",
    "Cannot predict now",
    "Concentrate and ask again",
    "Don’t count on it",
    "Outlook not so good",
    "My sources say no",
    "Very doubtful",
    "My reply is no",
]

messages_dict = {}

keep_track = {}

newdickt = {}

vision_dict = {}

default_persona = [
  {"role": "system", "content": "Your messages will be sent in discord. Use proper formatting."}
]

persona_config = [
    {"value": "4", "role": "Math", "content": "Analyze the user's question and identify any mathematical equations, problems, or calculations it may require to solve. Keep your answers short and concise."},
    {"value": "5", "role": "Code", "content": "You are a helpful coding assistant, provide step by step solutions to the users questions. Write efficient, clean, easily understandable code."},
    {"value": "16", "role": "Default", "content": ("All your messages will be sent in discord. Messages will be truncated >2K chars. Use appropriate formatting.")}
]

persona_dict = {
        persona["role"]: {"name": persona["role"], "persona": [persona], "value": persona["value"]}
        for persona in persona_config
    }

history = [
        {"parts": [{"text": "Your messages will be sent in discord. Use proper formatting."}],
         "role": "user"},
        {"parts": [{"text": "Will do."}], "role": "model"}
    ]


# Define your tools
search_internet_declaration = glm.FunctionDeclaration(
    name='search_internet',
    description="Returns short descriptions of top 3 results",
    parameters=glm.Schema(
        type=glm.Type.OBJECT,
        properties={
            'query': glm.Schema(type=glm.Type.STRING, description="The search query")
        },
        required=['query']
    )
)

get_weather_declaration = glm.FunctionDeclaration(
    name='get_weather',
    description="Returns Fahrenheit ONLY weather data.",
    parameters=glm.Schema(
        type=glm.Type.OBJECT,
        properties={
            'city': glm.Schema(type=glm.Type.STRING, description="City name"),
            'state': glm.Schema(type=glm.Type.STRING, description="State code (only for the US, leave blank otherwise)"),
            'country': glm.Schema(type=glm.Type.STRING, description="Country code. Please use ISO 3166 country codes")
        },
        required=['city', 'state', 'country']
    )
)

# Create a list of function declarations
function_declarations = [
    search_internet_declaration,
    get_weather_declaration
]

tools = glm.Tool(function_declarations=function_declarations)


safety_settings = {
        'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'block_none',
        'HARM_CATEGORY_HATE_SPEECH': 'block_none',
        'HARM_CATEGORY_HARASSMENT': 'block_none',
        'HARM_CATEGORY_DANGEROUS_CONTENT': 'block_none'
}

# tools = [
#             {
#                 "type": "function",
#                 "function": {
#                     "name": "search_internet",
#                     "description": "Search the internet using Google's API. Returns top 3 search results.",
#                     "parameters": {
#                         "type": "object",
#                         "properties": {
#                             "query": {
#                                 "type": "string",
#                                 "description": "The search query"
#                             }
#                         },
#                         "required": ["query"],
#                     }
#                 }
#             },
#             {
#                 "type": "function",
#                 "function": {
#                     "name": "get_definition",
#                     "description": "Merriam-Webster API. Returns definition.",
#                     "parameters": {
#                         "type": "object",
#                         "properties": {
#                             "word": {
#                                 "type": "string",
#                                 "description": "The word to define"
#                             }
#                         },
#                         "required": ["word"],
#                     }
#                 }
#             },
#             {
#                 "type": "function",
#                 "function": {
#                     "name": "get_weather",
#                     "description": "Get current weather data using OpenWeatherMap's API. Returns Fahrenheit ONLY.",
#                     "parameters": {
#                         "type": "object",
#                         "properties": {
#                             "city": {
#                                 "type": "string",
#                                 "description": "City name"
#                             },
#                             "state": {
#                                 "type": "string",
#                                 "description": "State code (only for the US, leave blank otherwise)"
#                             },
#                             "country": {
#                                 "type": "string",
#                                 "description": "Country code. Please use ISO 3166 country codes"
#                             }
#                         },
#                         "required": ["city", "state", "country"],
#                     }
#                 }
#             }
#         ]

help_instructions = f"""
# Using the "!" Prefix:
- Adding the "!" prefix before messages will instruct the bot to ignore those messages in the #chat-gpt channel.

## Commands:
- **?8ball**
  - The bot replies with one of the classic 8-ball messages.
  - Simply type ?8ball in the chat and send a message.

- **/ping**
  - Returns the latency of the bot.
  - Type /ping in the chat.

- **/model**
  - Allows you to switch between different chat models.
  - /model [model_name] (e.g. /model GPT-4 Turbo)

- **/personas**
  - Allows you to change the personality of the bot.
  - /personas [persona_name] (e.g. /personas DAN)

- **/gpt**
  - Simplified version of the standard implementation in the #chat-gpt channel.
  - /gpt [message]
  - Optionally you can add a persona parameter to the gpt command to specify the bot's personality. For example: /gpt [message] --[persona_name]
"""
