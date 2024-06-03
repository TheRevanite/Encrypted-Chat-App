from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from flask_socketio import join_room, leave_room, send, SocketIO, emit
import random
import secrets
from string import ascii_uppercase
from datetime import datetime
import sqlite3

app = Flask(__name__)
app.config["SECRET_KEY"] = secrets.token_hex(16)
socketio = SocketIO(app)

rooms = {}

conn = sqlite3.connect('chat.db', check_same_thread=False)
c = conn.cursor()

def create_table():
    c.execute("DROP TABLE IF EXISTS messages")
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  room_number TEXT,
                  user TEXT,
                  encrypted_message TEXT,
                  datetime TEXT)''')
    conn.commit()

create_table()

def caesar_encrypt(text, shift=3):
    result = ""
    for char in text:
        if char.isalpha():
            base = ord("a") if char.islower() else ord("A")
            result += chr((ord(char) - base + shift) % 26 + base)
        else:
            result += char
    return result

def caesar_decrypt(encrypted_text):
    return caesar_encrypt(encrypted_text, -3)

def generate_unique_code(length):
    while True:
        code = "".join(random.choice(ascii_uppercase) for _ in range(length))
        if code not in rooms:
            break
    return code

@app.route("/", methods=["POST", "GET"])
def home():
    session.clear()
    if request.method == "POST":
        name = request.form.get("name")
        code = request.form.get("code")
        join = request.form.get("join", False)
        create = request.form.get("create", False)

        if not name:
            return render_template("home.html", error="Please enter a name.", code=code, name=name)

        if join != False and not code:
            return render_template("home.html", error="Please enter a room code.", code=code, name=name)
        
        room = code
        if create != False:
            room = generate_unique_code(4)
            rooms[room] = {"members": 0, "messages": []}
        elif code not in rooms:
            return render_template("home.html", error="Room does not exist.", code=code, name=name)
        
        session["room"] = room
        session["name"] = name
        return redirect(url_for("room"))

    return render_template("home.html")

@app.route("/room")
def room():
    room = session.get("room")
    if room is None or session.get("name") is None or room not in rooms:
        return redirect(url_for("home"))
    
    c.execute("SELECT user, encrypted_message FROM messages WHERE room_number=?", (room,))
    encrypted_messages = c.fetchall()
    decrypted_messages = []
    for user, encrypted_message in encrypted_messages:
        decrypted_message = caesar_decrypt(encrypted_message)
        decrypted_messages.append({"user": user, "message": decrypted_message})

    return render_template("room.html", code=room, messages=decrypted_messages)

@app.route("/get_users/<room>")
def get_users(room):
    c.execute("SELECT DISTINCT user FROM messages WHERE room_number=?", (room,))
    users = c.fetchall()
    return jsonify(users=[user[0] for user in users], count=len(users))

@socketio.on("message")
def message(data):
    room = session.get("room")
    if room not in rooms:
        return 
    
    content = {
        "name": session.get("name"),
        "message": data["data"]
    }

    encrypted_message = caesar_encrypt(data["data"])
    c.execute("INSERT INTO messages (room_number, user, encrypted_message, datetime) VALUES (?, ?, ?, ?)",
              (room, session.get("name"), encrypted_message, datetime.now()))
    conn.commit()
    send(content, to=room) 
    print(f"{session.get('name')} said: {data['data']}")

@socketio.on("connect")
def connect(auth):
    room = session.get("room")
    name = session.get("name")
    if not room or not name:
        return
    if room not in rooms:
        leave_room(room)
        return
    
    join_room(room)
    send({"name": name, "message": "has entered the room!"}, to=room)
    rooms[room]["members"] += 1
    print(f"{name} joined room {room}")

@socketio.on("disconnect_request")
def disconnect_request():
    room = session.get("room")
    name = session.get("name")
    leave_room(room)

    if room in rooms:
        rooms[room]["members"] -= 1
        if rooms[room]["members"] <= 0:
            del rooms[room]

    send({"name": name, "message": "has left the room"}, to=room)
    print(f"{name} has left the room {room}")


    socketio.emit("force_disconnect")

if __name__ == "__main__":
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)
