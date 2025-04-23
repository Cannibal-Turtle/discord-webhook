# relay.py
import os
import asyncio
from fastapi import FastAPI, Request, HTTPException
from discord import Intents
from discord.ext import commands

BOT_TOKEN   = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID  = int(os.getenv("DISCORD_CHANNEL_ID", 0))

if not BOT_TOKEN or not CHANNEL_ID:
    raise RuntimeError("Missing DISCORD_BOT_TOKEN or DISCORD_CHANNEL_ID")

# Set up FastAPI for incoming posts
app = FastAPI()

# Set up discord.py bot
intents = Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
_ready = asyncio.Event()

@bot.event
async def on_ready():
    _ready.set()

# Relay endpoint
@app.post("/webhook")
async def relay_webhook(req: Request):
    data = await req.json()
    content = data.get("content")
    if content is None:
        raise HTTPException(400, "Missing content")
    # wait until bot is ready
    await _ready.wait()
    channel = bot.get_channel(CHANNEL_ID)
    await channel.send(content, allowed_mentions=data.get("allowed_mentions"), embeds=data.get("embeds"))
    return {"status":"ok"}

# Run both FastAPI and discord bot
def start():
    import uvicorn
    # run discord client in background
    loop = asyncio.get_event_loop()
    loop.create_task(bot.start(BOT_TOKEN))
    # then start FastAPI
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))

if __name__ == "__main__":
    start()
