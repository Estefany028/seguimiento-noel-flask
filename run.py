import os
import threading
import worker
from app import app

def start_worker():
    worker.main()

if __name__ == "__main__":
    t = threading.Thread(target=start_worker, daemon=True)
    t.start()

    print("Worker iniciado en background")

    port = int(os.environ.get("PORT", 10000))

    app.run(host="0.0.0.0", port=port)
