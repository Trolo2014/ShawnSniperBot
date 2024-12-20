import discord
from discord.ext import commands
import requests
import os
import asyncio
import random
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

# Function to get avatar thumbnail URL with retry logic
async def get_avatar_thumbnail(user_id, retries=480, initial_delay=0.25): 
    url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&format=Png&size=150x150"
    delay = initial_delay
    original_retries = retries  # Store the original retry count
    while retries > 0:  # Use a while loop to control retries
        try:
            response = requests.get(url)
            if response.status_code == 429:  # Rate limit error
                print(f"Rate limit hit. Retrying after {delay} seconds...")
                await asyncio.sleep(delay)
                retries -= 1  # Decrement retry count
                continue

            response.raise_for_status()
            data = response.json()
            if 'data' in data and len(data['data']) > 0:
                return data['data'][0]['imageUrl']
            return None

        except requests.RequestException as e:
            print(f"Failed: {e}")
            retries -= 1  # Decrement retry count

    # Reset retries to original count after success
    retries = original_retries
    return None



# Updated list of proxies that support HTTPS
proxies_list = [
    "http://213.136.79.127:8888",
    "http://47.251.43.115:33333",
    "http://103.255.222.1:80",
    "http://103.160.69.85:3128",
    "168.119.214.223:60775",
    "NoProxy",  # Option for no proxy
]

# Function to get game servers with proxy rotation
async def get_servers(place_id, cursor=None, retries=480, initial_delay=0.25):
    url = f"https://games.roblox.com/v1/games/{place_id}/servers/Public?limit=100"
    if cursor:
        url += f"&cursor={cursor}"

    delay = initial_delay

    while retries > 0:
        # Select a random proxy for each request
        proxy = random.choice(proxies_list)

        if proxy == "NoProxy":
            print("Using no proxy for this request.")
            proxy = None  # Set proxy to None to make a request without proxy
        else:
            print(f"Using proxy: {proxy}")

        try:
            # Make the request with or without a proxy based on the selection
            response = requests.get(url, proxies={"http": proxy, "https": proxy}, timeout=2.5) if proxy else requests.get(url, timeout=2.5)

            if response.status_code == 429:  # Rate limit error
                print(f"Rate limit hit with {proxy if proxy else 'NoProxy'}. Switching to another proxy...")
                await asyncio.sleep(delay)  # Wait before trying the next proxy
                continue  # Go back to the start of the while loop to try another proxy

            response.raise_for_status()  # Raise an error for bad responses
            return response.json()  # Return JSON response if successful

        except requests.RequestException as e:
            print(f"Failed with proxy {proxy if proxy else 'NoProxy'}: {e}")
            retries -= 1  # Decrement retry count if there's an error

    return None  # Return None if all retries fail



# Function to batch fetch thumbnails with retry logic
async def fetch_thumbnails(tokens, retries=480, initial_delay=0.25): 
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
    delay = initial_delay
    original_retries = retries  # Store the original retry count

    while retries > 0:  # Use a while loop to control retries
        try:
            response = requests.post(url, json=body)

            # Handle rate limit
            if response.status_code == 429:
                print(f"Rate limit Fetching Thumbnails hit. Retrying after {delay} seconds...")
                await asyncio.sleep(delay)
                retries -= 1  # Decrement retry count
                continue  # Retry

            response.raise_for_status()  # Raise error for other non-200 status codes
            return response.json()

        except requests.RequestException as e:
            print(f"Failed: {e}")
            retries -= 1  # Decrement retry count

    # Reset retries to original count after success
    retries = original_retries
    return None


# Function to search for player
async def search_player(interaction, place_id, username, embed):
    user_id = get_user_id(username)
    if not user_id:
        embed.clear_fields()
        embed.add_field(name="Error", value="User Does Not Exist", inline=False)
        await interaction.edit_original_response(embed=embed)
        return None

    target_thumbnail_url = await get_avatar_thumbnail(user_id)
    if not target_thumbnail_url:
        embed.clear_fields()
        embed.add_field(name="Error", value="Server Issues Run Command again", inline=False)
        await interaction.edit_original_response(embed=embed)
        return None

    cursor = None
    all_player_tokens = []
    server_data = []
    total_servers = 0
    total_players_not_matched = 0

    while True:
        fetch_count = 0

        # Fetch servers up to 3 times before processing player tokens
        while fetch_count < 3:
            servers = await get_servers(place_id, cursor)
            if not servers:
                embed.add_field(name="Error", value="Failed to get servers after retries", inline=False)
                await interaction.edit_original_response(embed=embed)
                return None

            cursor = servers.get("nextPageCursor")
            total_servers += len(servers.get("data", []))

            for server in servers.get("data", []):
                tokens = server.get("playerTokens", [])
                all_player_tokens.extend(tokens)
                total_players_not_matched += len(tokens)
                server_data.extend([(token, server) for token in tokens])

            # Update the embed with progress
            embed.clear_fields()
            embed.add_field(name="Fetching Servers", value=f"Total Servers Collected: {total_servers}", inline=False)
            embed.add_field(name="Collecting Players Token", value=f"{total_players_not_matched}", inline=False)
            await interaction.edit_original_response(embed=embed)

            # Increment fetch count
            fetch_count += 1

        # Process chunks of player tokens
        chunk_size = 100
        while all_player_tokens:
            chunk = all_player_tokens[:chunk_size]
            all_player_tokens = all_player_tokens[chunk_size:]
            thumbnails = await fetch_thumbnails(chunk)
            if not thumbnails:
                embed.add_field(name="Error", value="Thumbnail Rate Limit is A Bitch", inline=False)
                await interaction.edit_original_response(embed=embed)
                return

            for thumb in thumbnails.get("data", []):
                if thumb["imageUrl"] == target_thumbnail_url:
                    for token, server in server_data:
                        if token == thumb["requestId"].split(":")[1]:
                            return server.get("id")

            # Update the total players not matched field
            total_players_not_matched -= len(chunk)
            embed.set_field_at(1, name="Matching Players Token With Target Token", value=f"{total_players_not_matched}", inline=False)
            await interaction.edit_original_response(embed=embed)

        # If cursor is None, we have exhausted the servers and should exit
        if cursor is None:
            break

    return None


async def load_all_servers_and_search_player(interaction, place_id, username, embed):
    user_id = get_user_id(username)
    if not user_id:
        embed.clear_fields()
        embed.add_field(name="Error", value="User Does Not Exist", inline=False)
        await interaction.edit_original_response(embed=embed)
        return None

    target_thumbnail_url = await get_avatar_thumbnail(user_id)
    if not target_thumbnail_url:
        embed.clear_fields()
        embed.add_field(name="Error", value="Server Issues Run Command again", inline=False)
        await interaction.edit_original_response(embed=embed)
        return None

    cursor = None
    all_player_tokens = []
    server_data = []
    total_servers = 0
    total_players_not_matched = 0

    # Load all servers before searching players
    while True:
        servers = await get_servers(place_id, cursor)
        if not servers:
            embed.add_field(name="Error", value="Failed to get servers after retries", inline=False)
            await interaction.edit_original_response(embed=embed)
            return None

        cursor = servers.get("nextPageCursor")
        total_servers += len(servers.get("data", []))

        for server in servers.get("data", []):
            tokens = server.get("playerTokens", [])
            all_player_tokens.extend(tokens)
            total_players_not_matched += len(tokens)
            server_data.extend([(token, server) for token in tokens])

        # Update the embed with progress
        embed.clear_fields()
        embed.add_field(name="Fetching Servers", value=f"Total Servers Loaded: {total_servers}", inline=False)
        embed.add_field(name="Colecting Players Token", value=f"{total_players_not_matched}", inline=False)
        await interaction.edit_original_response(embed=embed)

        # If cursor is None, break out of the loop
        if cursor is None:
            break

    # Now that all servers are loaded, start matching players
    chunk_size = 100
    while all_player_tokens:
        chunk = all_player_tokens[:chunk_size]
        all_player_tokens = all_player_tokens[chunk_size:]
        thumbnails = await fetch_thumbnails(chunk)
        if not thumbnails:
            embed.add_field(name="Error", value="Thumbnail Rate Limit is A Bitch", inline=False)
            await interaction.edit_original_response(embed=embed)
            return

        for thumb in thumbnails.get("data", []):
            if thumb["imageUrl"] == target_thumbnail_url:
                for token, server in server_data:
                    if token == thumb["requestId"].split(":")[1]:
                        return server.get("id")

        # Update the total players not matched field
        total_players_not_matched -= len(chunk)
        embed.set_field_at(1, name="Matching Players Token With Target Token", value=f"{total_players_not_matched}", inline=False)
        await interaction.edit_original_response(embed=embed)

    return None


# Cog for checking T-shirt ownership

class CheckTshirtCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="checktshirtpurchase", description="Loop Check if a user owns a specific T-shirt For 10 Minutes")
    @discord.app_commands.describe(username="The Roblox username", tshirt_id="The T-Shirt Asset ID")
    @commands.has_permissions(administrator=True)  # Restricting command to users with admin permissions
    async def checktshirt(self, interaction: discord.Interaction, username: str, tshirt_id: str):
        await interaction.response.defer()  # Defer the response to avoid timeout

        user_id = get_user_id(username)
        if not user_id:
            embed = discord.Embed(color=0x780606)  # Gold color
            embed.add_field(name="Error", value="User not found", inline=False)
            await interaction.edit_original_response(embed=embed)
            return

        embed = discord.Embed(color=0x780606)  # Gold color
        embed.add_field(name="Checking Purchase Of T-Shirt", value="Starting check...", inline=False)
        message = await interaction.followup.send(embed=embed, ephemeral=True)

        end_time = datetime.now() + timedelta(minutes=10)
        while datetime.now() < end_time:
            ownership_status = check_ownership(user_id, tshirt_id)
            if ownership_status:
                embed.clear_fields()
                embed.add_field(name="Purchase Detected", value=f"{username} has bought T-shirt {tshirt_id}!", inline=False)
                await message.edit(embed=embed)
                return

            # Calculate the remaining time
            remaining_time = end_time - datetime.now()
            minutes, seconds = divmod(remaining_time.seconds, 60)
            time_str = f"{minutes}m {seconds}s"

            # Update embed with real-time countdown status
            embed.clear_fields()
            embed.add_field(name="T Shirt Purchase Detector", value=f"Scanning For Purchase \n\nTime Left: {time_str}", inline=False)
            await message.edit(embed=embed)

            await asyncio.sleep(1)  # Wait 1 second before checking again

        # After 5 minutes of checking
        embed.clear_fields()
        embed.add_field(name="Status", value=f"Scan Finished {username} did not purchase {tshirt_id} T Shirt In Duration of 10 minutes.", inline=False)
        await message.edit(embed=embed)

# Cog for searching player in a specific game
class SnipeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="snipe", description="Search for a player in a specific game")
    @discord.app_commands.describe(username="The Roblox username (LETTER CASE MATTER!)", place_id="The game place ID", method="Search method: RealTime or LoadServersScan")
    @discord.app_commands.choices(method=[
        discord.app_commands.Choice(name="RealTime", value="realtime"),
        discord.app_commands.Choice(name="LoadServersScan", value="loadserversscan"),
    ])
    @commands.has_permissions(administrator=True)  # Restricting command to users with admin permissions
    async def snipe_command(self, interaction: discord.Interaction, username: str, place_id: int, method: str):
        # Check if there is an active job
        if any(active_jobs.values()):
            for user_id in active_jobs:
                if user_id != interaction.user.id:
                    user = self.bot.get_user(user_id)
                    if user:
                        embed = discord.Embed(color=0x780606)  # Gold color
                        embed.add_field(name="Sniper", value=f"{user.name} is currently running a search. Please wait until their search is finished before starting a new one.", inline=False)
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return

        active_jobs[interaction.user.id] = True
        await interaction.response.defer()  # Defer the response to avoid timeout

        # Initial embed with progress information
        embed = discord.Embed(color=0x780606)  # Gold color
        embed.add_field(name="Status", value="Starting to search...", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

        # Use the selected method
        if method == "realtime":
            job_id = await search_player(interaction, place_id, username, embed)
        elif method == "loadserversscan":
            job_id = await load_all_servers_and_search_player(interaction, place_id, username, embed)
        else:
            embed.clear_fields()
            embed.add_field(name="Invalid Method", value="Please choose either 'RealTime' or 'LoadServersScan'.", inline=False)
            await interaction.edit_original_response(embed=embed)
            active_jobs[interaction.user.id] = False
            return

        # Process the result
        if job_id:
            # Player found case
            embed.clear_fields()
            embed.add_field(name=f"Player: {username} Found!", value="", inline=False)
            embed.add_field(name="DeepLink BloxStrap", value=f"roblox://experiences/start?placeId={place_id}&gameInstanceId={job_id}", inline=False)
            embed.add_field(name="Instructions For DeepLink BloxStrap", value="Copy DeepLink, Enter https://www.roblox.com/home and Paste It Into URL Then Enter", inline=False)
            embed.add_field(name="DeepLink Roblox Console", value=f'Roblox.GameLauncher.joinGameInstance({place_id},"{job_id}")', inline=False)
            embed.add_field(name="Instructions For DeepLink Roblox Console", value="Copy DeepLink, Enter https://www.roblox.com/home Turn Inspect Element then Select Console And Paste It In Then Enter", inline=False)
            embed.add_field(name="Job ID", value=f"{job_id}", inline=False)
        else:
            # Player not found case
            embed.clear_fields()
            embed.add_field(name=f"Player: {username} was not found in PlaceID: {place_id}", value="", inline=False)

        await interaction.edit_original_response(embed=embed)
        active_jobs[interaction.user.id] = False





    @discord.app_commands.command(name="snipet", description="Continuously search for a player in a specific game for 15 minutes")
    @discord.app_commands.describe(username="The Roblox username (LETTER CASE MATTER!)", place_id="The game place ID")
    @commands.has_permissions(administrator=True)  # Restricting command to users with admin permissions
    async def snipet_command(self, interaction: discord.Interaction, username: str, place_id: str):
        # Check if there is an active job
        if any(active_jobs.values()):
            for user_id in active_jobs:
                if user_id != interaction.user.id:
                    user = self.bot.get_user(user_id)
                    if user:
                        embed = discord.Embed(color=0x780606)  # Gold color
                        embed.add_field(name="Active Job", value=f"{user.name} is currently running a search. Please wait until their search is finished before starting a new one.", inline=False)
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return

        active_jobs[interaction.user.id] = True
        await interaction.response.defer()  # Defer the response to avoid timeout

        # Initial embed with progress information
        embed = discord.Embed(color=0x780606)  # Gold color
        embed.add_field(name="Status", value="Starting to search...", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

        end_time = datetime.now() + timedelta(minutes=10)
        found = False

        while datetime.now() < end_time:
            job_id = await search_player(interaction, place_id, username, embed)

            if job_id:
                # Player found case
                embed.clear_fields()
                embed.add_field(name=f"Player: {username} Found!", value="", inline=False)
                embed.add_field(name="DeepLink BloxStrap", value=f"roblox://experiences/start?placeId={place_id}&gameInstanceId={job_id}", inline=False)
                embed.add_field(name="Instructions For DeepLink BloxStrap", value="Copy DeepLink, Enter https://www.roblox.com/home and Paste It Into URL Then Enter", inline=False)
                embed.add_field(name="DeepLink Roblox Console", value=f'Roblox.GameLauncher.joinGameInstance({place_id},"{job_id}")', inline=False)
                embed.add_field(name="Instructions For DeepLink Roblox Console", value="Copy DeepLink, Enter https://www.roblox.com/home Turn Inspect Element then Select Console And Paste It In Then Enter", inline=False)
                embed.add_field(name="Job ID", value=f"{job_id}", inline=False)
                found = True
                break  # Exit loop if player is found

            # Dynamic cooldown
            for remaining in range(10, 0, -1):  # Countdown from 20 to 1
                embed.clear_fields()
                embed.add_field(name="Rate Limit Cooldown", value=f"Waiting {remaining} seconds before retrying...", inline=False)
                await interaction.edit_original_response(embed=embed)
                await asyncio.sleep(1)  # Wait 1 second

        if not found:
            # Player not found after 10 minutes
            embed.clear_fields()
            embed.add_field(name=f"Player: {username} was not found in PlaceID: {place_id} after 10 minutes", value="", inline=False)

        await interaction.edit_original_response(embed=embed)
        active_jobs[interaction.user.id] = False


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
