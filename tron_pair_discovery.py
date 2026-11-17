import requests
import json
import os
import time
from datetime import datetime

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
TRONGRID_API_KEY = os.environ.get("TRONGRID_API_KEY", "")

# USDT TRC-20 Contract
USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
STATE_FILE = "pair_state.json"

# The number of consecutive transactions to check
TARGET_STREAK = 5 

# --- TELEGRAM ---
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

# --- FETCH NEW EVENTS ---
def get_new_transfer_events(min_timestamp):
    url = f"https://api.trongrid.io/v1/contracts/{USDT_CONTRACT}/events"
    params = {
        "event_name": "Transfer",
        "only_confirmed": "true",
        "limit": 200, # Fetch a batch to process
        "min_block_timestamp": min_timestamp,
        "order_by": "block_timestamp,asc" # Process oldest to newest
    }
    headers = {}
    if TRONGRID_API_KEY:
        headers["TRON-PRO-API-KEY"] = TRONGRID_API_KEY

    try:
        response = requests.get(url, params=params, headers=headers, timeout=20)
        response.raise_for_status()
        return response.json().get("data", [])
    except Exception as e:
        print(f"API Error: {e}")
        return []

# --- MAIN LOGIC ---
def main():
    # 1. Load State
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
    else:
        # Start from 30 minutes ago on the first run
        state = {"last_timestamp": int(time.time() * 1000) - (30 * 60 * 1000), "receivers": {}}

    last_timestamp = state["last_timestamp"]
    receivers = state["receivers"]

    # 2. Fetch events
    events = get_new_transfer_events(last_timestamp)
    
    if not events:
        print("No new events found.")
        return

    print(f"Processing {len(events)} new events...")
    max_timestamp = last_timestamp

    # 3. Analyze
    for event in events:
        tx_time = event.get("block_timestamp", 0)
        if tx_time > max_timestamp:
            max_timestamp = tx_time

        result = event.get("result", {})
        sender = result.get("from")
        receiver = result.get("to")

        if not sender or not receiver:
            continue

        # Initialize receiver state if not present
        if receiver not in receivers:
            receivers[receiver] = {"history": [], "alerted": False}

        # Add sender to the history list
        history = receivers[receiver]["history"]
        history.append(sender)

        # Keep only the last 5 transactions in the list
        if len(history) > TARGET_STREAK:
            history.pop(0) # Remove the oldest one

        # Check if we have a full streak of 5 identical senders
        if len(history) == TARGET_STREAK:
            # Check if all items in the list are the same
            if len(set(history)) == 1: 
                if not receivers[receiver]["alerted"]:
                    receivers[receiver]["alerted"] = True
                    
                    message = (
                        f"🎯 <b>5 Consecutive Transactions from Same Sender!</b>\n\n"
                        f"👤 <b>Sender:</b> <code>{sender}</code>\n"
                        f"📥 <b>Receiver:</b> <code>{receiver}</code>\n"
                        f"🔁 <b>Streak:</b> 5 Transactions\n"
                        f"💰 <b>Token:</b> USDT\n"
                        f"⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    send_telegram_message(message)
                    print(f"Alert sent! {sender} sent 5 in a row to {receiver}")
            else:
                # If a different sender breaks the streak, reset the alert flag
                # so we can alert again if they start a new streak of 5
                receivers[receiver]["alerted"] = False

    # 4. Save state
    state["last_timestamp"] = max_timestamp
    state["receivers"] = receivers
    
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)
    
    print(f"State saved. Tracking {len(receivers)} unique receiver addresses.")

if __name__ == "__main__":
    main()
