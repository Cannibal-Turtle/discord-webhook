import discord, asyncio, os

TOKEN = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID = 1329655743799889962  # normal text channel

async def main():
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        ch = client.get_channel(CHANNEL_ID)
        print("ready, sending test message")
        await ch.send("🧪 re-entry test — please ignore")
        print("send returned")
        await client.close()

    await client.start(TOKEN)

asyncio.run(main())
