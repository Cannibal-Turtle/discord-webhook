import os
import asyncio
from fastapi import FastAPI, Request, HTTPException
from discord import Intents
from discord.ext import commands

BOT_TOKEN  = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", 0))
PORT       = int(os.getenv("PORT", "8000"))

if not BOT_TOKEN or not CHANNEL_ID:
    raise RuntimeError("Missing DISCORD_BOT_TOKEN or DISCORD_CHANNEL_ID")

# --- Discord Bot Setup ---
intents = Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
_ready = asyncio.Event()

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    _ready.set()

# --- FastAPI Setup ---
app = FastAPI()

@app.post("/webhook")
async def relay_webhook(req: Request):
    data    = await req.json()
    content = data.get("content")
    if content is None:
        raise HTTPException(400, "Missing content")
    await _ready.wait()
    channel = bot.get_channel(CHANNEL_ID)
    await channel.send(
        content,
        allowed_mentions=data.get("allowed_mentions"),
        embeds=data.get("embeds"),
    )
    return {"status": "ok"}

@app.on_event("startup")
async def start_discord_bot():
    # Launch the bot in the background
    asyncio.create_task(bot.start(BOT_TOKEN))

if __name__ == "__main__":
    import uvicorn
    # This will now run in the main thread and print all logs
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
