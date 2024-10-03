from flask import Flask, request, render_template_string
import discord
from discord.ext import commands
import requests
import asyncio

# Initialize Flask app
app = Flask(__name__)

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

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

# Function to fetch player thumbnails
async def fetch_player_thumbnail(user_id):
    url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=150x150&format=Png"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data and 'data' in data and len(data['data']) > 0:
            thumbnail_url = data['data'][0]['imageUrl']
            return thumbnail_url
        return None
    except requests.RequestException as e:
        print(f"Error fetching thumbnail: {e}")
        return None

# Function to search for a player
async def search_player(username):
    user_id = get_user_id(username)
    if not user_id:
        return None, None

    thumbnail_url = await fetch_player_thumbnail(user_id)
    return user_id, thumbnail_url

# HTML template as a string
html_template = """
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
        <label for="username">Roblox Username:</label>
        <input type="text" id="username" name="username" required>
        <br>
        <input type="submit" value="Search">
    </form>

    {% if user_id %}
        <h2>Player found!</h2>
        <p>User ID: {{ user_id }}</p>
        <img src="{{ thumbnail_url }}" alt="Player Thumbnail">
    {% elif result %}
        <h2>{{ result }}</h2>
    {% endif %}
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        username = request.form.get('username')

        if username:
            # Call the search_player function
            user_id, thumbnail_url = asyncio.run(search_player(username))
            if user_id:
                return render_template_string(html_template, user_id=user_id, thumbnail_url=thumbnail_url)
            else:
                return render_template_string(html_template, result=f"Player {username} not found.")

    return render_template_string(html_template, result=None)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
