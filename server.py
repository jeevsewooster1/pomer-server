from flask import Flask, request, jsonify
from dotenv import load_dotenv
import json
import os
import sys

load_dotenv()

app = Flask(__name__)
DATA_FILE = 'timer_data.json'
AUTH_TOKEN = os.getenv('SYNC_TOKEN')
PORT = int(os.getenv('PORT', 5555))

def log(msg):
    print(f"[LOG] {msg}", file=sys.stderr)

def load_data():
    if not os.path.exists(DATA_FILE):
        return None
    with open(DATA_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return None

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def count_history_entries(payload):
    """Counts total completed sessions across all days."""
    try:
        # payload structure: { "updatedAt": ..., "payload": { "history": { "2023-10-01": [...], ... } } }
        history = payload.get('payload', {}).get('history', {})
        count = 0
        for date_key, sessions in history.items():
            count += len(sessions)
        return count
    except Exception:
        return 0

@app.route('/sync', methods=['POST'])
def sync():
    auth_header = request.headers.get('Authorization')
    if not auth_header or auth_header != f"Bearer {AUTH_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401

    client_payload = request.json
    if not client_payload:
        return jsonify({"error": "Invalid payload"}), 400

    server_payload = load_data()

    # 1. First Sync (Server Empty)
    if not server_payload:
        log("Server empty. Initializing with client data.")
        save_data(client_payload)
        return jsonify({"status": "accepted", "serverData": None})

    # 2. Compare Data Richness (History Count)
    client_count = count_history_entries(client_payload)
    server_count = count_history_entries(server_payload)
    
    log(f"Comparing History: Client({client_count}) vs Server({server_count})")

    if client_count > server_count:
        log("Client has MORE data. Updating Server.")
        save_data(client_payload)
        return jsonify({"status": "accepted", "serverData": None})
    
    elif client_count < server_count:
        log("Client has LESS data (Potential wipe). Rejecting. Sending Server Data.")
        return jsonify({"status": "conflict", "serverData": server_payload})

    # 3. Tie-Breaker: Timestamps (Only if history counts are equal)
    else:
        client_ts = client_payload.get('updatedAt', 0)
        server_ts = server_payload.get('updatedAt', 0)
        log(f"History Equal. Comparing Time: Client({client_ts}) vs Server({server_ts})")

        if client_ts >= server_ts:
            log("Client is Newer/Equal. Updating Server.")
            save_data(client_payload)
            return jsonify({"status": "accepted", "serverData": None})
        else:
            log("Server is Newer. Sending Server Data.")
            return jsonify({"status": "conflict", "serverData": server_payload})

if __name__ == '__main__':
    log(f"Server running on port {PORT}...")
    app.run(host='0.0.0.0', port=PORT)
