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
            if attempt < retries - 1:
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
    total_players_collected = 0
    matched_players = 0
    total_server_batches = 0

    # Stage 1: Fetching Servers
    while True:
        servers = await get_servers(place_id, cursor)
        if not servers:
            embed.add_field(name="Error", value="Failed to get servers after retries", inline=False)
            await interaction.edit_original_response(embed=embed)
            return None

        cursor = servers.get("nextPageCursor")
        total_servers += len(servers.get("data", []))
        total_players_collected += sum(len(server.get("playerTokens", [])) for server in servers.get("data", []))

        # Update embed with progressively updated total servers and players
        embed.clear_fields()
        embed.add_field(name="Fetching Servers!", value=f"Total Servers collected: {total_servers}", inline=False)
        embed.add_field(name="Matching Players ID With Target ID Per 100 Servers:", value=f"{total_players_collected}", inline=False)
        await interaction.edit_original_response(embed=embed)

        for server in servers.get("data", []):
            tokens = server.get("playerTokens", [])
            all_player_tokens.extend(tokens)
            server_data.extend([(token, server) for token in tokens])

        if not cursor:
            break

    # Stage 2: Matching Players in Background
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
                        embed.clear_fields()
                        embed.add_field(name=f"Player: {username} Found!", value="", inline=False)
                        embed.add_field(name="DeepLink", value=f"roblox://experiences/start?placeId={place_id}&gameInstanceId={server.get('id')}", inline=False)
                        embed.add_field(name="Instructions:", value="Copy DeepLink, Enter https://www.roblox.com/home and Paste It Into URL", inline=False)
                        await interaction.edit_original_response(embed=embed)
                        return server.get("id")

        scanned_chunks += 1
        matched_players += 1
        progress = (scanned_chunks / total_chunks) * 100

        # Update the embed with matching progress
        embed.set_field_at(2, name="Matching Players ID With Target ID Per 100 Servers", value=f"{matched_players} per {scanned_chunks * 100} servers", inline=False)
        await interaction.edit_original_response(embed=embed)

    return None


# Cog for searching player in a specific game
class SnipeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="snipe", description="Search for a player in a specific game")
    @discord.app_commands.describe(username="The Roblox username (LETTER CASE MATTER!)", place_id="The game place ID")
    @commands.has_permissions(administrator=True)
    async def snipe_command(self, interaction: discord.Interaction, username: str, place_id: str):
        if any(active_jobs.values()):
            for user_id, _ in active_jobs.items():
                if user_id != interaction.user.id:
                    user = self.bot.get_user(user_id)
                    if user:
                        embed = discord.Embed(color=0xFFD700)
                        embed.add_field(name="Sniper", value=f"{user.name} is currently running a search. Please wait.", inline=False)
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return

        active_jobs[interaction.user.id] = True
        await interaction.response.defer()

        embed = discord.Embed(color=0xFFD700)
        embed.add_field(name="Fetching Servers!", value="Total Servers collected: 0", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

        await search_player(interaction, place_id, username, embed)

        active_jobs[interaction.user.id] = False
