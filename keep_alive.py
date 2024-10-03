from flask import Flask, request, jsonify, render_template
import threading
import requests
import asyncio

app = Flask(__name__)

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

    return None

# Function to get game servers with retry logic
async def get_servers(place_id, cursor=None, retries=120, initial_delay=1): 
    url = f"https://games.roblox.com/v1/games/{place_id}/servers/Public?limit=100"
    if cursor:
        url += f"&cursor={cursor}"
    delay = initial_delay
    original_retries = retries  # Store the original retry count

    while retries > 0:  # Use a while loop to control retries
        try:
            response = requests.get(url)
            if response.status_code == 429:  # Rate limit error
                print(f"Rate limit Fetching Servers hit. Retrying after {delay} seconds...")
                await asyncio.sleep(delay)
                retries -= 1  # Decrement retry count
                continue

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            print(f"Failed: {e}")
            retries -= 1  # Decrement retry count

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
        embed.add_field(name="Error", value="Server Issues. Run Command again.", inline=False)
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
            embed.add_field(name="Fetching Servers", value=f"Total Servers Checked: {total_servers}", inline=False)
            embed.add_field(name="Matching Players ID With Target", value=f"{total_players_not_matched}", inline=False)
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
                embed.add_field(name="Error", value="Thumbnail Rate Limit Exceeded", inline=False)
                await interaction.edit_original_response(embed=embed)
                return

            for thumb in thumbnails.get("data", []):
                if thumb["imageUrl"] == target_thumbnail_url:
                    for token, server in server_data:
                        if token == thumb["requestId"].split(":")[1]:
                            return server.get("id")

            # Update the total players not matched field
            total_players_not_matched -= len(chunk)
            embed.set_field_at(1, name="Matching Players ID With Target", value=f"{total_players_not_matched}", inline=False)
            await interaction.edit_original_response(embed=embed)

        # If cursor is None, we have exhausted the servers and should exit
        if cursor is None:
            break

    return None

# Function to handle the sniper logic
async def snipe_logic(username, place_id):
    embed = ...  # Initialize your embed object here (this will depend on your existing code context)
    interaction = ...  # Initialize your interaction object here (same as above)
    await search_player(interaction, place_id, username, embed)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    username = request.form.get('username')
    place_id = request.form.get('place_id')

    # Use RealTime scan as requested
    if username and place_id:
        # Call the snipe logic with username and place_id
        asyncio.run(snipe_logic(username, place_id))  # This will need to be adjusted based on your integration
        return jsonify({"status": "Searching..."})  # Adjust as necessary
    else:
        return jsonify({"error": "Please provide both username and place ID."}), 400

# Function to keep the app alive
def keep_alive():
    app.run(host='0.0.0.0', port=8080)

# Run the app in a separate thread to keep it alive
if __name__ == '__main__':
    threading.Thread(target=keep_alive).start()
