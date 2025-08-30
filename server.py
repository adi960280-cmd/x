from flask import Flask
import threading
import os

# Flask app
app = Flask(__name__)

# --- Extractor Bot Run Function ---
def run_bot():
    import Extractor   # yahi tera main bot package hai
    Extractor.main()   # uska entrypoint call kar

# --- Routes ---
@app.route("/")
def home():
    return "Bot running ✅"

# --- Main ---
if __name__ == "__main__":
    # Bot background thread me run hoga
    threading.Thread(target=run_bot, daemon=True).start()
    
    # Flask server foreground me run hoga
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
