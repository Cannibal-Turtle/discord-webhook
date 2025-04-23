// index.js
require("dotenv").config();
const { Client, GatewayIntentBits } = require("discord.js");
const cron = require("node-cron");

const { runFreeChecker } = require("./feeds/freeChecker");
const { runPaidChecker } = require("./feeds/paidChecker");

const client = new Client({ intents: [GatewayIntentBits.Guilds] });

async function doAllChecks() {
  const ch = await client.channels.fetch(process.env.DISCORD_CHANNEL_ID);
  await runExtraChecker(ch);
  await runArcChecker(ch);
  await runCompletionChecker(ch);
}

client.once("ready", () => {
  console.log(`✅ Logged in as ${client.user.tag}`);
  // run immediately
  doAllChecks().catch(console.error);
  // then every 15 minutes
  cron.schedule("*/15 * * * *", () => {
    console.log("🔄 Checking feeds…");
    doAllChecks().catch(console.error);
  });
});

client.login(process.env.DISCORD_BOT_TOKEN);
