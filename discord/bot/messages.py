DEVS_MESSAGE = "Created by RaiNz"

BOT_SUMMARY = (
    "I'm Softia, an AI bot to manage the AllSoft server and partners. "
    "I have a multifunctional system with various commands, type -info to see my capabilities"
)

INFO_MESSAGE = """Hello! I'm Softia, here are my commands:
`-devs` - shows the bot creators
`-sum` - presents the bot
`-info` - shows this list
`-musicinfo` - shows music commands
`-mathinfo` - shows math commands
`-searchinfo` - shows search commands
`-chatinfo` - shows chat commands
`-serverinfo` - shows server management commands
`-eventsinfo` - shows random event commands
`-auditinfo` - shows anti-spam audit commands
`-gameinfo` - shows economy and game commands
"""

MUSIC_INFO_MESSAGE = """Music Commands:
`-play <link or name>` - plays YouTube, searches by name or resolves Spotify link
`-loop` - toggles loop for the current song
`-next` - skips to the next song in the queue
`-back` - goes back to the previous song
`-queue` - displays the current queue
"""

MATH_INFO_MESSAGE = """Math Commands:
`-sum <num1> <num2>` - addition
`-sub <num1> <num2>` - subtraction
`-mult <num1> * <num2>` - multiplication
`-div <num1> / <num2>` - division
`-mod <num1> % <num2>` - modulo
`-pow <num1> ^ <num2>` - exponentiation
`-sqrt <num> [grau]` - square root, cube root or root of degree x
`-matrix [[1,2],[3,4]] * [[5,6],[7,8]]` - matrix multiplication
"""

SEARCH_INFO_MESSAGE = """Search Commands:
`-grepg <texto>` - searches on Google and returns the first 5 links
`-grepb <texto>` - searches on Bing and returns the first 5 links
"""

CHAT_INFO_MESSAGE = """Chat Commands:
`-chat <prompt>` - starts channel chat mode with the OpenAI API
After activation, messages from any user in this channel will be treated as prompts.
Softia searches the web before answering and includes useful results as context.
`-abortchat` - terminates chat mode and sends a .txt file with the conversation
"""

SERVER_INFO_MESSAGE = """Server Management Commands:
`-serverinfo` - shows this list
`-clear <amount>` - deletes 1 to 100 messages from the current channel
`-kick @member [reason]` - kicks a member from the server
`-ban @member [reason]` - bans a member from the server
`-eventsinfo` - shows random event commands
`-auditinfo` - shows anti-spam audit commands
"""

EVENTS_INFO_MESSAGE = """Random Event Commands:
`-seteventchannel #channel` - sets the chat where random events are posted
`-eventson` - enables automatic random events
`-eventsoff` - disables automatic random events
`-eventnow` - posts a random event immediately
Events include live polls, private-answer quizzes, click races, mystery doors, team challenges and coin rewards.
"""

AUDIT_INFO_MESSAGE = """Anti-Spam Audit Commands:
`-auditinfo` - shows this list
`-auditon` - enables automatic anti-spam moderation
`-auditoff` - disables automatic anti-spam moderation

Automatic audit deletes spam bursts and repeated-image spam, then attempts to ban the responsible member.
"""

GAME_INFO_MESSAGE = """Game Commands:
`-wallet [@member]` - shows a user's coin wallet
`-daily` - claims daily coins
`-shop` - shows items available to buy
`-buy <item_id> [quantity]` - buys items from the shop
`-inventory [@member]` - shows purchased items
`-leaderboard` - shows the richest users

Available Games:
`-blackjack <bet>` - blackjack with Hit/Stand buttons
`-coinflip <heads/tails> <bet>` - coin flip
`-slots <bet>` - animated slot machine
`-dice <1-6> <bet>` - animated dice guess
"""
