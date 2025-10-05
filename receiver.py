# receiver.py (modified)

import threading
import queue
import time
import random
import pyautogui
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn
import asyncio

app = FastAPI()

broadcast_queue = asyncio.Queue()


# CORS (for fetch requests from UI)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # you can restrict
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

typing_queue = queue.Queue()
pause_event = threading.Event()
randomize_flag = True
auto_pause_after_line = False

# Keep track of connected WebSocket clients
connected_status_sockets: list[WebSocket] = []

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
            if item == "\n":
                pyautogui.press("enter")
                # After pressing Enter, auto-pause if enabled
                if auto_pause_after_line:
                    pause_event.set()
                    # Notify clients of status change
                    _broadcast_status()
            else:
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
                # Possibly add more commands
                if randomize_flag:
                    time.sleep(random.uniform(0.3, 1.5))
                else:
                    time.sleep(0.1)

        # Random delay between actions
        if randomize_flag:
            time.sleep(random.uniform(0.3, 1.5))
        else:
            time.sleep(0.1)

        # After any action, broadcast status (queue size, pause, etc.)
        _broadcast_status()


def _get_status_dict():
    return {
        "paused": pause_event.is_set(),
        "randomize": randomize_flag,
        "auto_pause_after_line": auto_pause_after_line,
        "queue_size": typing_queue.qsize(),
    }

def _broadcast_status():
    import json
    msg = json.dumps({"type": "status", "data": _get_status_dict()})
    try:
        broadcast_queue.put_nowait(msg)
    except Exception as e:
        print("Failed to queue broadcast:", e)

async def broadcast_loop():
    while True:
        msg = await broadcast_queue.get()
        disconnected = []
        for ws in connected_status_sockets:
            try:
                await ws.send_text(msg)
            except:
                disconnected.append(ws)

        # Remove any disconnected sockets
        for ws in disconnected:
            try:
                connected_status_sockets.remove(ws)
            except:
                pass


@app.on_event("startup")
async def startup_event():
    pause_event.clear()

    # Start typing thread (non-async)
    t = threading.Thread(target=typing_worker, daemon=True)
    t.start()

    # Start async broadcaster loop
    asyncio.create_task(broadcast_loop())



@app.on_event("shutdown")
def shutdown_event():
    typing_queue.put("STOP")


@app.websocket("/ws/status")
async def status_ws_endpoint(ws: WebSocket):
    await ws.accept()
    connected_status_sockets.append(ws)
    try:
        # Send initial status
        init = _get_status_dict()
        await ws.send_json({"type": "status", "data": init})
        while True:
            # Keep connection alive; we don't expect messages from client for now
            # But we need to receive, or else disconnect
            msg = await ws.receive_text()
            # Optionally you can allow client to request status explicitly
            if msg == "get_status":
                await ws.send_json({"type": "status", "data": _get_status_dict()})
    except WebSocketDisconnect:
        # Remove from list
        try:
            connected_status_sockets.remove(ws)
        except ValueError:
            pass
    except Exception as e:
        print("WebSocket error:", e)
        try:
            connected_status_sockets.remove(ws)
        except ValueError:
            pass


@app.post("/command")
async def receive_command(cmd: Command):
    global randomize_flag, auto_pause_after_line

    # For toggles, we will broadcast status after the state change
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
        # broadcast
        _broadcast_status()
        return {"randomize": randomize_flag}

    elif cmd.action == "toggle_auto_pause":
        auto_pause_after_line = not auto_pause_after_line
        _broadcast_status()
        return {"auto_pause_after_line": auto_pause_after_line}

    elif cmd.action == "stop":
        with typing_queue.mutex:
            typing_queue.queue.clear()
        pause_event.set()
        _broadcast_status()
        return {"status": "typing stopped"}

    elif cmd.action in ["backspace", "left", "right"]:
        if not isinstance(cmd.data, int):
            raise HTTPException(status_code=400, detail="Data must be int for " + cmd.action)
        typing_queue.put({"cmd": cmd.action, "count": cmd.data})

    else:
        raise HTTPException(status_code=400, detail="Unknown action")

    _broadcast_status()
    return {"status": "command received"}


@app.get("/status")
def get_status():
    return _get_status_dict()


if __name__ == "__main__":
    uvicorn.run("receiver:app", host="0.0.0.0", port=8000, reload=False)
