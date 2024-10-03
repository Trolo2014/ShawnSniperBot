from flask import Flask, render_template, request
from threading import Thread
import os

app = Flask(__name__)

# Home route with input form
@app.route('/')
def index():
    return '''
        <form action="/snipe" method="post">
            <label for="username">Roblox Username:</label><br>
            <input type="text" id="username" name="username" required><br>
            <label for="placeid">PlaceID:</label><br>
            <input type="text" id="placeid" name="placeid" required><br><br>
            <input type="submit" value="Search">
        </form>
    '''

# Route for sniping with form input
@app.route('/snipe', methods=['POST'])
def snipe():
    username = request.form['username']
    placeid = request.form['placeid']
    
    # Here you would integrate your snipe function
    # Replace with your actual snipe logic
    found_match = snipe_function(username, placeid)
    
    if found_match:
        roblox_join_url = f"roblox://placeID={placeid}&username={username}"
        return f"Match found! Click to join: <a href='{roblox_join_url}'>Join Game</a>"
    else:
        return f"No match found for username: {username} and placeID: {placeid}"

def snipe_function(username, placeid):
    # Simulate the snipe search logic (replace this with your actual logic)
    # Returns True if a match is found, otherwise False
    if username == "test_user" and placeid == "123456789":
        return True
    return False

# Keep the app running continuously
def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
