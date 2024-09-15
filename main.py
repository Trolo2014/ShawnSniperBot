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
        print(f"Error getting username: {e}")
        return None

# Function to check T-shirt ownership
def check_ownership(user_id, tshirt_id):
    url = f"https://inventory.roblox.com/v1/users/{user_id}/items/Asset/{tshirt_id}/is-owned"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data.get("isOwned", False)
    except requests.RequestException as e:
        print(f"Error checking T-shirt ownership: {e}")
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

    # Stage 1: Fetching Servers
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
        embed.add_field(name="Fetching Servers", value=f"Total Servers: {total_servers}", inline=False)
        await interaction.edit_original_response(embed=embed)

        for server in servers.get("data", []):
            tokens = server.get("playerTokens", [])
            all_player_tokens.extend(tokens)
            server_data.extend([(token, server) for token in tokens])

        if not cursor:
            break

    # Stage 2: After all servers are loaded
    embed.clear_fields()
    embed.add_field(name="Fetching Servers", value=f"Total Servers: {total_servers}", inline=False)
    embed.add_field(name="Status", value="Scanning Servers For Player...", inline=False)
    embed.add_field(name="Scanning Progress", value="0%", inline=False)
    await interaction.edit_original_response(embed=embed)

    chunk_size = 100
    total_chunks = (len(all_player_tokens) + chunk_size - 1) // chunk_size
    scanned_chunks = 0

    while all_player_tokens:
        chunk = all_player_tokens[:chunk_size]
        all_player_tokens = all_player_tokens[chunk_size:]
        thumbnails = fetch_thumbnails(chunk)
        if not thumbnails:
            embed.add_field(name="Error", value="Failed to fetch thumbnails", inline=False)
            await interaction.edit_original_response(embed=embed)
            return

        for thumb in thumbnails.get("data", []):
            if thumb["imageUrl"] == target_thumbnail_url:
                for token, server in server_data:
                    if token == thumb["requestId"].split(":")[1]:
                        return server.get("id")

        scanned_chunks += 1
        progress = (scanned_chunks / total_chunks) * 100

        # Update the embed with scanning progress
        embed.set_field_at(2, name="Scanning Progress", value=f"{progress:.2f}%", inline=False)
        await interaction.edit_original_response(embed=embed)

    return None

# Cog for checking T-shirt ownership
class CheckTshirtCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="checktshirtpurchase", description="Check if a user owns a specific T-shirt")
    @discord.app_commands.describe(username="The Roblox username", tshirt_id="The T-Shirt Asset ID")
    @commands.has_permissions(administrator=True)  # Restricting command to users with admin permissions
    async def checktshirt(self, interaction: discord.Interaction, username: str, tshirt_id: str):
        await interaction.response.defer()  # Defer the response to avoid timeout

        # Initial embed with progress
        embed = discord.Embed(color=0xFFD700)  # Gold color
        embed.add_field(name="Checking Purchase Of T-Shirt", value="Checking if purchase is made...", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

        user_id = get_user_id(username)
        if not user_id:
            embed.clear_fields()
            embed.add_field(name="Error", value="User not found", inline=False)
            await interaction.edit_original_response(embed=embed)
            return

        end_time = datetime.now() + timedelta(minutes=5)
        while datetime.now() < end_time:
            is_owner = check_ownership(user_id, tshirt_id)
            if is_owner:
                embed.clear_fields()
                embed.add_field(name="Success", value=f"User {username} has purchased the T-shirt!", inline=False)
                await interaction.edit_original_response(embed=embed)
                return

            # Waiting before checking again
            await asyncio.sleep(5)

        embed.clear_fields()
        embed.add_field(name="Timeout", value=f"User {username} has not purchased the T-shirt after 5 minutes.", inline=False)
        await interaction.edit_original_response(embed=embed)

# Add the cog to the bot
bot.add_cog(CheckTshirtCog(bot))

# Run the bot
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
bot.run(DISCORD_BOT_TOKENO)
