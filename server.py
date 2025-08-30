from flask import Flask
import multiprocessing
import os
import Extractor

app = Flask(__name__)

# --- Flask route for UptimeRobot ---
@app.route("/")
def home():
    return "Bot running ✅"

# --- Run bot in separate process ---
def run_bot():
    Extractor.main()

if __name__ == "__main__":
    # Start bot process
    p = multiprocessing.Process(target=run_bot)
    p.start()

    # Start flask server
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
