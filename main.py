import discord
from discord.ext import commands
import requests
import os
import asyncio
from datetime import datetime, timedelta

from keep_alive import keep_alive
keep_alive()

# Bot setup with intents
intents = discord.Intents.default()
intents.message_content = True  # Required for reading message content

bot = commands.Bot(command_prefix='!', intents=intents)

# Global variable to track active jobs
active_jobs = {}

# Function to get user ID from username
def get_user_id(username):
    url = "https://users.roblox.com/v1/usernames/users"
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

# Function to get username from user ID
def get_username(user_id):
    url = f"https://users.roblox.com/v1/users/{user_id}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if 'name' in data:
            return data['name']
        return None
    except requests.RequestException as e:
        return None

# Function to check T-shirt ownership
def check_ownership(user_id, tshirt_id):
    url = f"https://inventory.roblox.com/v1/users/{user_id}/items/Asset/{tshirt_id}/is-owned"
    try:
        response = requests.get(url)
        output = response.json()
        return output == True  # Return True if the entire output is True, else False
    except requests.RequestException as e:
        return False

# Function to get avatar thumbnail URL with retry logic and exponential backoff
async def get_avatar_thumbnail(user_id, retries=25, initial_delay=1):
    url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&format=Png&size=150x150"
    delay = initial_delay
    for attempt in range(retries):
        try:
            response = requests.get(url)
            if response.status_code == 429:  # Rate limit error
                print(f"Rate limit hit. Retrying after {delay} seconds...")
                await asyncio.sleep(delay)
                delay *= 2  # Exponential backoff
                continue

            response.raise_for_status()
            data = response.json()
            if 'data' in data and len(data['data']) > 0:
                return data['data'][0]['imageUrl']
            return None
        except requests.RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:  # Don't delay after the last attempt
                await asyncio.sleep(delay)
                delay *= 2  # Exponential backoff
    return None

# Function to get game servers with retry logic and exponential backoff
async def get_servers(place_id, cursor=None, retries=25, initial_delay=1):
    url = f"https://games.roblox.com/v1/games/{place_id}/servers/Public?limit=100"
    if cursor:
        url += f"&cursor={cursor}"
    delay = initial_delay
    for attempt in range(retries):
        try:
            response = requests.get(url)
            if response.status_code == 429:  # Rate limit error
                print(f"Rate limit hit. Retrying after {delay} seconds...")
                await asyncio.sleep(delay)
                delay *= 2  # Exponential backoff
                continue

            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:  # Don't delay after the last attempt
                await asyncio.sleep(delay)
                delay *= 2  # Exponential backoff
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
        embed.add_field(name="Error", value="User not found", inline=False)
        await interaction.edit_original_response(embed=embed)
        return None

    target_thumbnail_url = await get_avatar_thumbnail(user_id)
    if not target_thumbnail_url:
        embed.add_field(name="Error", value="Failed to get avatar thumbnail", inline=False)
        await interaction.edit_original_response(embed=embed)
        return None

    cursor = None
    all_player_tokens = []
    server_data = []
    total_servers = 0
    total_tokens_scanned = 0

    # Stage 1: Fetching Servers and Matching Tokens Concurrently
    while True:
        servers = await get_servers(place_id, cursor)
        if not servers:
            embed.add_field(name="Error", value="Failed to get servers after retries", inline=False)
            await interaction.edit_original_response(embed=embed)
            return None

        cursor = servers.get("nextPageCursor")
        total_servers += len(servers.get("data", []))

        # Update embed with the progressively updated total servers
        embed.clear_fields()
        embed.add_field(name="Fetching Servers", value=f"Total Servers: {total_servers}\nTotal Tokens Scanned: {total_tokens_scanned}", inline=False)
        await interaction.edit_original_response(embed=embed)

        for server in servers.get("data", []):
            tokens = server.get("playerTokens", [])
            all_player_tokens.extend(tokens)
            server_data.extend([(token, server) for token in tokens])

        # Check tokens in parallel
        chunk_size = 100
        for i in range(0, len(all_player_tokens), chunk_size):
            chunk = all_player_tokens[i:i + chunk_size]
            thumbnails = fetch_thumbnails(chunk)
            if not thumbnails:
                embed.add_field(name="Error", value="Failed to fetch thumbnails", inline=False)
                await interaction.edit_original_response(embed=embed)
                return

            for thumb in thumbnails.get("data", []):
                total_tokens_scanned += 1
                if thumb["imageUrl"] == target_thumbnail_url:
                    for token, server in server_data:
                        if token == thumb["requestId"].split(":")[1]:
                            embed.clear_fields()
                            embed.add_field(name=f"Player: {username} Found!", value="", inline=False)
                            embed.add_field(name="DeepLink", value=f"roblox://experiences/start?placeId={place_id}&gameInstanceId={server.get('id')}", inline=False)
                            embed.add_field(name="Instructions:", value="Copy DeepLink, Enter https://www.roblox.com/home and Paste It Into URL", inline=False)
                            await interaction.edit_original_response(embed=embed)
                            return

            # Update embed with scanning progress
            embed.set_field_at(0, name="Fetching Servers", value=f"Total Servers: {total_servers}\nTotal Tokens Scanned: {total_tokens_scanned}", inline=False)
            await interaction.edit_original_response(embed=embed)

        if not cursor:
            break

    # If no player was found
    embed.clear_fields()
    embed.add_field(name=f"Player: {username} was not found in PlaceID: {place_id}", value="", inline=False)
    await interaction.edit_original_response(embed=embed)
    return None

# Cog for checking T-shirt ownership
class CheckTshirtCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="checktshirtpurchase", description="Check if a user owns a specific T-shirt")
    @discord.app_commands.describe(username="The Roblox username", tshirt_id="The ID of the T-shirt")
    async def check_tshirt_purchase(self, interaction: discord.Interaction, username: str, tshirt_id: int):
        user_id = get_user_id(username)
        if not user_id:
            embed = discord.Embed(color=0xFF0000)  # Red color
            embed.add_field(name="Error", value="User not found", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        ownership = check_ownership(user_id, tshirt_id)
        if ownership:
            embed = discord.Embed(color=0x00FF00)  # Green color
            embed.add_field(name="T-Shirt Ownership", value=f"{username} owns the T-shirt with ID {tshirt_id}.", inline=False)
        else:
            embed = discord.Embed(color=0xFF0000)  # Red color
            embed.add_field(name="T-Shirt Ownership", value=f"{username} does not own the T-shirt with ID {tshirt_id}.", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

# Cog for sniping
class SnipeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='snipe')
    async def snipe(self, ctx, place_id: str, username: str):
        embed = discord.Embed(color=0xFFD700)  # Gold color
        embed.add_field(name="Snipe Command", value="Initiating player search...", inline=False)
        message = await ctx.send(embed=embed)
        await search_player(ctx, place_id, username, embed)

    @commands.command(name='snipet')
    async def snipet(self, ctx, place_id: str, username: str):
        embed = discord.Embed(color=0xFFD700)  # Gold color
        embed.add_field(name="Snipet Command", value="Initiating player search...", inline=False)
        message = await ctx.send(embed=embed)
        await search_player(ctx, place_id, username, embed)

# Register the cog and the command tree
async def setup(bot):
    await bot.add_cog(CheckTshirtCog(bot))
    await bot.add_cog(SnipeCog(bot))
    await bot.tree.sync()

# Bot event handler to run the setup function when the bot is ready
@bot.event
async def on_ready():
    await setup(bot)
    print(f'Logged in as {bot.user}')

# Run the bot using the token stored in environment variables
bot.run(os.environ.get('DISCORD_BOT_TOKENO'))
