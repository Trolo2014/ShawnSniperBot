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

# Function to get Roblox username
def get_username(user_id):
    url = f"https://users.roblox.com/v1/users/{user_id}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            return data.get('name', 'Unknown User')
        else:
            return 'Unknown User'
    except requests.RequestException as e:
        print(f"An error occurred: {e}")
        return 'Unknown User'

# Function to check ownership
def check_ownership(user_id, asset_id):
    url = f"https://inventory.roblox.com/v1/users/{user_id}/items/Asset/{asset_id}/is-owned"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()  # Assuming the response is a boolean
        else:
            return False
    except requests.RequestException as e:
        print(f"An error occurred: {e}")
        return False

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

# Function to batch fetch thumbnails with retry logic
async def fetch_thumbnails(tokens, retries=3, delay=2):
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
    for attempt in range(retries):
        try:
            response = requests.post(url, json=body)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            await asyncio.sleep(delay)  # Wait before retrying
    return None

# Function to collect player tokens
async def collect_player_tokens(place_id, cursor=None):
    all_player_tokens = []
    server_data = []
    
    while True:
        servers = await get_servers(place_id, cursor)
        if not servers:
            print("Failed to get servers")
            return None

        cursor = servers.get("nextPageCursor")

        for server in servers.get("data", []):
            tokens = server.get("playerTokens", [])
            all_player_tokens.extend(tokens)
            server_data.extend([(token, server) for token in tokens])

        if not cursor:
            break

    return all_player_tokens, server_data

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

    all_player_tokens, server_data = await collect_player_tokens(place_id)

    if all_player_tokens is None:
        embed.add_field(name="Error", value="Failed to collect player tokens")
        await interaction.edit_original_response(embed=embed)
        return None

    embed.set_field_at(0, name="Status", value=f"Fetching {len(all_player_tokens)} Tokens...", inline=False)
    await interaction.edit_original_response(embed=embed)
    
    chunk_size = 100
    total_chunks = (len(all_player_tokens) + chunk_size - 1) // chunk_size
    scanned_chunks = 0

    while all_player_tokens:
        chunk = all_player_tokens[:chunk_size]
        all_player_tokens = all_player_tokens[chunk_size:]
        thumbnails = await fetch_thumbnails(chunk)
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
        embed.set_field_at(0, name="Status", value="Scanning Servers For Player...", inline=False)
        embed.set_field_at(1, name="Scanning Progress", value=f"{progress:.2f}%", inline=False)
        await interaction.edit_original_response(embed=embed)

    return None

# Cog for searching player in a specific game
class SnipeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="snipe", description="Search for a player in a specific game")
    @discord.app_commands.describe(username="The Roblox username (LETTER CASE MATTER!)", place_id="The game place ID")
    @commands.has_permissions(administrator=True)  # Restricting command to users with admin permissions
    async def snipe_command(self, interaction: discord.Interaction, username: str, place_id: str):
        await interaction.response.defer()  # Defer the response to avoid timeout

        # Initial embed with progress bar
        embed = discord.Embed(color=0xFFD700)  # Gold color
        embed.add_field(name="Status", value="Initializing...", inline=False)
        embed.add_field(name="Scanning Progress", value="0% done", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

        job_id = await search_player(interaction, place_id, username, embed)

        if job_id:
            # Player found case
            embed.clear_fields()
            embed.add_field(
                name=f"Player: {username} Found!",
                value=f"",
                inline=False
            )
            embed.add_field(
                name=f"DeepLink",
                value=f"roblox://experiences/start?placeId={place_id}&gameInstanceId={job_id}",
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
            embed.add_field(name=f"Player: {username} was not found in PlaceID: {place_id}", value="", inline=False)

        await interaction.edit_original_response(embed=embed)

    @discord.app_commands.command(name="snipet", description="Loop Searches In Servers For Player For 5 Minutes")
    @discord.app_commands.describe(username="The Roblox username (LETTER CASE MATTER!)", place_id="The game place ID")
    @commands.has_permissions(administrator=True)  # Restricting command to users with admin permissions
    async def snipet_command(self, interaction: discord.Interaction, username: str, place_id: str):
        await interaction.response.defer()  # Defer the response to avoid timeout

        # Initial embed with progress bar
        embed = discord.Embed(color=0xFFD700)  # Gold color
        embed.add_field(name="Status", value="Starting Searches In Servers For Player For 5 Minutes...", inline=False)
        embed.add_field(name="Scanning Progress", value="0% done", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

        user_id = get_user_id(username)
        if not user_id:
            embed.add_field(name="Error", value="User not found")
            await interaction.edit_original_response(embed=embed)
            return

        target_thumbnail_url = get_avatar_thumbnail(user_id)
        if not target_thumbnail_url:
            embed.add_field(name="Error", value="Failed to get avatar thumbnail")
            await interaction.edit_original_response(embed=embed)
            return

        found = False
        start_time = asyncio.get_event_loop().time()
        duration = 900  # 15 minutes in seconds
        scan_interval = 15  # 15 seconds

        while asyncio.get_event_loop().time() - start_time < duration:
            embed.set_field_at(0, name="Status", value="Scanning Servers For Player...", inline=False)
            await interaction.edit_original_response(embed=embed)

            all_player_tokens, server_data = await collect_player_tokens(place_id)

            if all_player_tokens is None:
                embed.add_field(name="Error", value="Failed to collect player tokens")
                await interaction.edit_original_response(embed=embed)
                return

            embed.set_field_at(0, name=f"Fetching {len(all_player_tokens)} Tokens...", inline=False)

            chunk_size = 100
            total_chunks = (len(all_player_tokens) + chunk_size - 1) // chunk_size
            scanned_chunks = 0

            while all_player_tokens:
                chunk = all_player_tokens[:chunk_size]
                all_player_tokens = all_player_tokens[chunk_size:]
                thumbnails = await fetch_thumbnails(chunk)
                if not thumbnails:
                    embed.add_field(name="Error", value="Failed to fetch thumbnails")
                    await interaction.edit_original_response(embed=embed)
                    return

                for thumb in thumbnails.get("data", []):
                    if thumb["imageUrl"] == target_thumbnail_url:
                        for token, server in server_data:
                            if token == thumb["requestId"].split(":")[1]:
                                found = True
                                job_id = server.get("id")
                                embed.clear_fields()
                                embed.add_field(
                                    name=f"Player: {username} Found!",
                                    value=f"",
                                    inline=False
                                )
                                embed.add_field(
                                    name=f"DeepLink",
                                    value=f"roblox://experiences/start?placeId={place_id}&gameInstanceId={job_id}",
                                    inline=False
                                )
                                embed.add_field(
                                    name="Instructions:",
                                    value="Copy DeepLink, Enter https://www.roblox.com/home and Paste It Into URL",
                                    inline=False
                                )
                                await interaction.edit_original_response(embed=embed)
                                return

                scanned_chunks += 1
                progress = (scanned_chunks / total_chunks) * 100
                embed.set_field_at(0, name="Status", value="Scanning Servers For Player...", inline=False)
                embed.set_field_at(1, name="Scanning Progress", value=f"{progress:.2f}%", inline=False)
                await interaction.edit_original_response(embed=embed)

            embed.set_field_at(0, name="Status", value="(Cooldown)", inline=False)
            await interaction.edit_original_response(embed=embed)
            await asyncio.sleep(scan_interval)

        if not found:
            embed.clear_fields()
            embed.add_field(name=f"Player: {username} was not found in PlaceID: {place_id}", value="", inline=False)
            await interaction.edit_original_response(embed=embed)

# Cog for checking if a user owns a specific T-shirt
class CheckTshirtCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="checktshirtpurchase", description="Check if a user owns a specific T-shirt")
    @discord.app_commands.describe(user_id="The Roblox User ID", tshirt_id="The T-Shirt Asset ID")
    @commands.has_permissions(administrator=True)  # Restricting command to users with admin permissions
    async def checktshirt(self, interaction: discord.Interaction, user_id: str, tshirt_id: str):
        # Fetch the username
        username = get_username(user_id)
        ownership_status = check_ownership(user_id, tshirt_id)

        if ownership_status:
            await interaction.response.send_message(f"{username} bought the T-shirt ID {tshirt_id}!")
        else:
            await interaction.response.send_message(f"{username} hasn't bought T-shirt {tshirt_id}")

# Register the cogs and the command tree
async def setup(bot):
    await bot.add_cog(SnipeCog(bot))
    await bot.add_cog(CheckTshirtCog(bot))
    await bot.tree.sync()

# Bot event handler to run the setup function when the bot is ready
@bot.event
async def on_ready():
    await setup(bot)
    print(f'Logged in as {bot.user}')

# Run the bot using the token stored in environment variables
bot.run(os.environ.get('DISCORD_BOT_TOKEN'))
