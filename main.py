import discord
from discord.ext import commands
import requests
import os
import asyncio

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

# Function to get game servers with retry logic
async def get_servers(place_id, cursor=None, retries=10):
    url = f"https://games.roblox.com/v1/games/{place_id}/servers/Public?limit=100"
    if cursor:
        url += f"&cursor={cursor}"
    for attempt in range(retries):
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            await asyncio.sleep(2.5)  # Wait before retrying
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
async def search_player(interaction, place_id, username, embed):
    user_id = get_user_id(username)
    if not user_id:
        embed.add_field(name="Error", value="User not found")
        await interaction.edit_original_response(embed=embed)
        return None

    target_thumbnail_url = get_avatar_thumbnail(user_id)
    if not target_thumbnail_url:
        embed.add_field(name="Error", value="Failed to get avatar thumbnail")
        await interaction.edit_original_response(embed=embed)
        return None

    cursor = None
    all_player_tokens = []
    server_data = []
    total_servers = 0
    retries = 10  # Number of retries for fetching servers

    while True:
        embed.set_field_at(0, name="Looping Status", value="Fetching Servers...", inline=False)
        await interaction.edit_original_response(embed=embed)
        
        servers = await get_servers(place_id, cursor, retries)
        if not servers:
            embed.add_field(name="Error", value="Failed to get servers after retries")
            await interaction.edit_original_response(embed=embed)
            return None

        cursor = servers.get("nextPageCursor")
        total_servers += len(servers.get("data", []))

        for server in servers.get("data", []):
            tokens = server.get("playerTokens", [])
            all_player_tokens.extend(tokens)
            server_data.extend([(token, server) for token in tokens])

        if not cursor:
            break

    chunk_size = 100
    total_chunks = (len(all_player_tokens) + chunk_size - 1) // chunk_size
    scanned_chunks = 0

    while all_player_tokens:
        chunk = all_player_tokens[:chunk_size]
        all_player_tokens = all_player_tokens[chunk_size:]
        thumbnails = fetch_thumbnails(chunk)
        if not thumbnails:
            embed.add_field(name="Error", value="Failed to fetch thumbnails")
            await interaction.edit_original_response(embed=embed)
            return None

        for thumb in thumbnails.get("data", []):
            if thumb["imageUrl"] == target_thumbnail_url:
                for token, server in server_data:
                    if token == thumb["requestId"].split(":")[1]:
                        return server.get("id")

        scanned_chunks += 1
        progress = (scanned_chunks / total_chunks) * 100
        embed.set_field_at(0,name="Status", value="Scanning Servers For Player...", inline=False)
        embed.set_field_at(1,name="Scanning Progress", value=f"{progress:.2f}% Scanned", inline=False)
        await interaction.edit_original_response(embed=embed)
        await asyncio.sleep(0.25)  # Optional delay to manage load

    return None

# Cog containing the slash command
class SnipeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="snipe", description="Search for a player in a specific game")
    @discord.app_commands.describe(username="The Roblox username", place_id="The game place ID")
    @commands.has_permissions(administrator=True)  # Restricting command to users with admin permissions
    async def snipe_command(self, interaction: discord.Interaction, username: str, place_id: str):
        await interaction.response.defer()  # Defer the response to avoid timeout

        # Initial embed with progress bar
        embed = discord.Embed(color=0x1E90FF)  # Shiny blue color
        embed.add_field(name="Scanning Progress", value="0% done", inline=False)
        embed.add_field(name="Looping Status", value="Initializing...", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

        job_id = await search_player(interaction, place_id, username, embed)

        if job_id:
            # Player found case
            embed.clear_fields()
            embed.add_field(
                name=f"Player: {username} Found In PlaceID: {place_id}",
                value=f"DeepLink: ||roblox://experiences/start?placeId={place_id}&gameInstanceId={job_id}||",
                inline=False
            )
            embed.add_field(
                name="Instructions:",
                value="Copy DeepLink, Enter https://www.roblox.com/home and Paste It Into URL",
                inline=False
            )
        else:
            # Player not found case
            embed.clear_fields()
            embed.add_field(name=f"Player: {username} was not found in PlaceID: {place_id}", value="N/A", inline=False)

        await interaction.edit_original_response(embed=embed)

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
