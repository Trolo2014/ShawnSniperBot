from flask import Flask, render_template, request
from threading import Thread

app = Flask(__name__)

# Route for the home page with a form for username, place ID, and job ID
@app.route('/')
def index():
    return render_template('index.html')

# Route to handle the form submission for searching
@app.route('/search', methods=['POST'])
def search():
    username = request.form['username']
    placeid = request.form['placeid']
    jobid = request.form['jobid']

    # Dummy output to simulate the search functionality
    found_message = f"User '{username}' found in Place '{placeid}', Job ID '{jobid}'."

    return render_template('index.html', output=found_message)

# Route to handle search and join
@app.route('/searchjoin', methods=['POST'])
def searchjoin():
    username = request.form['username']
    placeid = request.form['placeid']
    jobid = request.form['jobid']

    # Construct the Roblox join game instance deep link using custom protocol
    join_link = f"roblox://placeID={placeid}&gameInstanceID={jobid}"
    found_message = f"User '{username}' found in Place '{placeid}', Job ID '{jobid}'."

    return render_template('index.html', output=found_message, join_link=join_link)

# Function to run the Flask app
def run():
    app.run(host='0.0.0.0', port=8080)

# Function to keep the server alive
def keep_alive():
    t = Thread(target=run)
    t.start()

# HTML template for the page (index.html)
html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Roblox Search & Join</title>
</head>
<body>
    <h1>Search and Join Roblox User</h1>
    
    <!-- Form for username, place ID, and job ID -->
    <form action="/search" method="POST">
        <label for="username">Username:</label>
        <input type="text" id="username" name="username" required><br><br>

        <label for="placeid">Place ID:</label>
        <input type="text" id="placeid" name="placeid" required><br><br>

        <label for="jobid">Job ID:</label>
        <input type="text" id="jobid" name="jobid" required><br><br>

        <!-- Search and Search & Join buttons -->
        <button type="submit">Search</button>
    </form>
    
    <form action="/searchjoin" method="POST" style="margin-top: 10px;">
        <input type="hidden" id="username" name="username" value="{{request.form['username']}}">
        <input type="hidden" id="placeid" name="placeid" value="{{request.form['placeid']}}">
        <input type="hidden" id="jobid" name="jobid" value="{{request.form['jobid']}}">
        <button type="submit">Search & Join</button>
    </form>

    <!-- Display output if available -->
    {% if output %}
        <h3>{{ output }}</h3>
        {% if join_link %}
            <p>Click below to join the game:</p>
            <a href="{{ join_link }}">Join Game</a>
        {% endif %}
    {% endif %}
</body>
</html>
"""

# Write the template to a file (index.html)
with open('templates/index.html', 'w') as file:
    file.write(html_template)

# Keep the Flask server running
keep_alive()
