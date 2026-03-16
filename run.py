import threading
import worker
from app import app

def start_worker():
    worker.main()

if __name__ == "__main__":
    t = threading.Thread(target=start_worker, daemon=True)
    t.start()

    print("Worker iniciado en background")

    app.run(host="0.0.0.0", port=10000)
