// feeds/freeChecker.js
const Parser = require("rss-parser"),
      fs     = require("fs"),
      parser = new Parser(),
      STATE_FILE = "./state.json";

async function runFreeChecker(channel) {
  const feed = await parser.parseURL(process.env.FREE_FEED_URL);
  const state = JSON.parse(fs.readFileSync(STATE_FILE));
  const last = state.lastFreeGuid || "";
  
  // find any items newer than last  
  const news = feed.items.filter(i => i.guid > last);
  for (let item of news) {
    await channel.send(`🆓 New Free Chapter: **${item.title}**\n${item.link}`);
  }
  
  if (news.length) {
    state.lastFreeGuid = news[0].guid;            // assume feed sorted newest→oldest
    fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
  }
}

module.exports = { runFreeChecker };
