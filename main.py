import discord
from discord.ext import commands
import requests
import os

from keep_alive import keep_alive
keep_alive()

# Bot setup with intents
intents = discord.Intents.default()
intents.message_content = True  # Required for reading message content

bot = commands.Bot(command_prefix='!', intents=intents)

# Function to get user ID from username
def get_user_id(username):
    url = f"https://users.roblox.com/v1/usernames/users"
    params = {"usernames": [username]}
    try:
        response = requests.post(url, json=params)
        response.raise_for_status()
        data = response.json()
        if data and 'data' in data and len(data['data']) > 0:
            user_id = data['data'][0]['id']
            return user_id
        return None
    except requests.RequestException as e:
        print(f"Error getting user ID: {e}")
        return None

# Function to get avatar thumbnail URL
def get_avatar_thumbnail(user_id):
    url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&format=Png&size=150x150"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if 'data' in data and len(data['data']) > 0:
            return data['data'][0]['imageUrl']
        return None
    except requests.RequestException as e:
        print(f"Error getting avatar thumbnail: {e}")
        return None

# Function to get game servers
def get_servers(place_id, cursor=None):
    url = f"https://games.roblox.com/v1/games/{place_id}/servers/Public?limit=100"
    if cursor:
        url += f"&cursor={cursor}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error getting servers: {e}")
        return None

# Function to batch fetch thumbnails
def fetch_thumbnails(tokens):
    body = [
        {
            "requestId": f"0:{token}:AvatarHeadshot:150x150:png:regular",
            "type": "AvatarHeadShot",
            "targetId": 0,
            "token": token,
            "format": "png",
            "size": "150x150"
        }
        for token in tokens
    ]
    url = "https://thumbnails.roblox.com/v1/batch"
    try:
        response = requests.post(url, json=body)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching thumbnails: {e}")
        return None

# Function to search for player
def search_player(place_id, username):
    user_id = get_user_id(username)
    if not user_id:
        return "User not found", None

    target_thumbnail_url = get_avatar_thumbnail(user_id)
    if not target_thumbnail_url:
        return "Failed to get avatar thumbnail", None

    cursor = None
    all_player_tokens = []
    server_data = []

    while True:
        servers = get_servers(place_id, cursor)
        if not servers:
            return "Failed to get servers", None

        cursor = servers.get("nextPageCursor")

        for server in servers.get("data", []):
            tokens = server.get("playerTokens", [])
            all_player_tokens.extend(tokens)
            server_data.extend([(token, server) for token in tokens])

        if not cursor:
            break

    chunk_size = 100
    for i in range(0, len(all_player_tokens), chunk_size):
        chunk = all_player_tokens[i:i + chunk_size]
        thumbnails = fetch_thumbnails(chunk)
        if not thumbnails:
            return "Failed to fetch thumbnails", None

        for thumb in thumbnails.get("data", []):
            if thumb["imageUrl"] == target_thumbnail_url:
                for token, server in server_data:
                    if token == thumb["requestId"].split(":")[1]:
                        return "Player found", server.get("id")

    return "Player not found", None

# Cog containing the slash command
class SnipeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="snipe", description="Search for a player in a specific game")
    @discord.app_commands.describe(username="The Roblox username", place_id="The game place ID")
    @commands.has_permissions(administrator=True)  # Restricting command to users with admin permissions
    async def snipe_command(self, interaction: discord.Interaction, username: str, place_id: str):
        status, job_id = search_player(place_id, username)

        embed = discord.Embed(color=0x1E90FF)  # Shiny blue color

        if job_id:
            # Player found case
            embed.add_field(
                name=f"Player {username} found in PlaceID:{place_id}",
                value=f"**Roblox.GameLauncher.joinGameInstance({place_id}, \"{job_id}\")**",
                inline=False
            )
            embed.add_field(
                name="Instructions:",
                value="Copy it > open roblox browser > inspect element > console > write allow pasting then ctrl v enter and it will join game",
                inline=False
            )
        else:
            # Player not found case
            embed.add_field(name=f"Player {username} was not found in PlaceID:{place_id}", value="N/A", inline=False)

        await interaction.response.send_message(embed=embed)

# Register the cog and the command tree
async def setup(bot):
    await bot.add_cog(SnipeCog(bot))
    await bot.tree.sync()

# Bot event handler to run the setup function when the bot is ready
@bot.event
async def on_ready():
    await setup(bot)
    print(f'Logged in as {bot.user}')

# Run the bot using the token stored in environment variables
bot.run(os.environ.get('DISCORD_BOT_TOKENO'))
