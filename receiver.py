# receiver.py
import threading
import queue
import time
import random
import pyautogui
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

typing_queue = queue.Queue()
pause_event = threading.Event()
randomize_flag = True
typer_thread = None

class Command(BaseModel):
    action: str
    data: str | int | None = None

def typing_worker():
    while True:
        if pause_event.is_set():
            time.sleep(0.1)
            continue
        try:
            item = typing_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        if item == "STOP":
            break
        if isinstance(item, str):
            pyautogui.write(item)
        elif isinstance(item, dict):
            cmd = item["cmd"]
            count = item.get("count", 1)
            for _ in range(count):
                if cmd == "backspace":
                    pyautogui.press("backspace")
                elif cmd == "left":
                    pyautogui.press("left")
                elif cmd == "right":
                    pyautogui.press("right")
                time.sleep(random.uniform(0.3, 1.5) if randomize_flag else 0.1)
        time.sleep(random.uniform(0.3, 1.5) if randomize_flag else 0.1)

@app.on_event("startup")
async def startup_event():
    global typer_thread
    pause_event.clear()
    typer_thread = threading.Thread(target=typing_worker, daemon=True)
    typer_thread.start()

@app.on_event("shutdown")
def shutdown_event():
    typing_queue.put("STOP")

@app.post("/command")
async def receive_command(cmd: Command):
    global randomize_flag

    if cmd.action == "type":
        if not cmd.data or not isinstance(cmd.data, str):
            raise HTTPException(status_code=400, detail="Data must be a string for 'type'")
        for char in cmd.data:
            typing_queue.put(char)

    elif cmd.action == "pause":
        pause_event.set()

    elif cmd.action == "resume":
        pause_event.clear()

    elif cmd.action == "toggle_random":
        randomize_flag = not randomize_flag
        return {"randomize": randomize_flag}

    elif cmd.action == "stop":
        with typing_queue.mutex:
            typing_queue.queue.clear()
        pause_event.set()
        return {"status": "typing stopped"}

    elif cmd.action in ["backspace", "left", "right"]:
        if not isinstance(cmd.data, int):
            raise HTTPException(status_code=400, detail="Data must be an integer for this command")
        typing_queue.put({"cmd": cmd.action, "count": cmd.data})

    else:
        raise HTTPException(status_code=400, detail="Unknown action")

    return {"status": "command received"}

@app.get("/status")
def get_status():
    return {
        "paused": pause_event.is_set(),
        "randomize": randomize_flag,
        "queue_size": typing_queue.qsize(),
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
