# sender_web/app.py

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import sys
import uvicorn
import os

# Create FastAPI app
app = FastAPI()

# Setup Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Read receiver URL from command-line or default to localhost
RECEIVER_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "receiver_url": RECEIVER_URL
    })

# Run the app directly via `python app.py`
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=False)
