from flask import Flask, request, render_template_string
import requests
import asyncio
import threading

app = Flask(__name__)

# Function to get user ID from username
def get_user_id(username):
    url = "https://users.roblox.com/v1/usernames/users"
    params = {"usernames": [username]}
    try:
        response = requests.post(url, json=params, timeout=10)  # Set a timeout for requests
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
    while retries > 0:
        try:
            response = requests.get(url, timeout=10)  # Set a timeout for requests
            if response.status_code == 429:
                print(f"Rate limit hit. Retrying after {delay} seconds...")
                await asyncio.sleep(delay)
                retries -= 1
                continue

            response.raise_for_status()
            data = response.json()
            if 'data' in data and len(data['data']) > 0:
                return data['data'][0]['imageUrl']
            return None

        except requests.RequestException as e:
            print(f"Failed to fetch thumbnail: {e}")
            retries -= 1

    return None

# Function to get game servers with retry logic
async def get_servers(place_id, cursor=None, retries=120, initial_delay=1):
    url = f"https://games.roblox.com/v1/games/{place_id}/servers/Public?limit=100"
    if cursor:
        url += f"&cursor={cursor}"
    delay = initial_delay

    while retries > 0:
        try:
            response = requests.get(url, timeout=10)  # Set a timeout for requests
            if response.status_code == 429:
                print(f"Rate limit fetching servers hit. Retrying after {delay} seconds...")
                await asyncio.sleep(delay)
                retries -= 1
                continue

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            print(f"Failed to fetch servers: {e}")
            retries -= 1

    return None

# Function to fetch thumbnails with retry logic
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

    while retries > 0:
        try:
            response = requests.post(url, json=body, timeout=10)  # Set a timeout for requests

            if response.status_code == 429:
                print(f"Rate limit fetching thumbnails hit. Retrying after {delay} seconds...")
                await asyncio.sleep(delay)
                retries -= 1
                continue

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            print(f"Failed to fetch thumbnails: {e}")
            retries -= 1

    return None

# Function to search for player
async def search_player(username, place_id):
    user_id = get_user_id(username)
    if not user_id:
        return "User Does Not Exist"

    target_thumbnail_url = await get_avatar_thumbnail(user_id)
    if not target_thumbnail_url:
        return "Server Issues, Run Command again"

    cursor = None
    all_player_tokens = []
    total_servers = 0
    total_players_not_matched = 0

    while True:
        fetch_count = 0

        while fetch_count < 3:
            servers = await get_servers(place_id, cursor)
            if not servers:
                return "Failed to get servers after retries"

            cursor = servers.get("nextPageCursor")
            total_servers += len(servers.get("data", []))

            for server in servers.get("data", []):
                tokens = server.get("playerTokens", [])
                all_player_tokens.extend(tokens)
                total_players_not_matched += len(tokens)

            fetch_count += 1

        chunk_size = 100
        while all_player_tokens:
            chunk = all_player_tokens[:chunk_size]
            all_player_tokens = all_player_tokens[chunk_size:]
            thumbnails = await fetch_thumbnails(chunk)
            if not thumbnails:
                return "Thumbnail Rate Limit Hit"

            for thumb in thumbnails.get("data", []):
                if thumb["imageUrl"] == target_thumbnail_url:
                    return f"Player found in server ID: {server.get('id')}"

        if cursor is None:
            break

    return "Player not found"

# HTML template as a string
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Roblox Player Search</title>
</head>
<body>
    <h1>Search for a Roblox Player</h1>
    <form method="POST">
        <label for="username">Username:</label>
        <input type="text" id="username" name="username" required>
        <br>
        <label for="placeid">Place ID:</label>
        <input type="text" id="placeid" name="placeid" required>
        <br>
        <button type="submit">Search</button>
    </form>

    {% if search_result %}
        <h2>Search Result:</h2>
        <p>{{ search_result }}</p>
    {% endif %}
</body>
</html>
"""

# Route for the homepage
@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        username = request.form.get('username')
        place_id = request.form.get('placeid')

        # Run the search function asynchronously and wait for the result
        result = asyncio.run(search_player(username, place_id))
        return render_template_string(HTML_TEMPLATE, search_result=result)

    return render_template_string(HTML_TEMPLATE, search_result=None)

# Keep-alive route
@app.route('/keep_alive')
def keep_alive():
    return "I'm alive!"

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080)  # Start the Flask app
