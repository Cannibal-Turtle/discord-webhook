// feeds/paidChecker.js
const Parser = require("rss-parser"),
      fs     = require("fs"),
      parser = new Parser(),
      STATE_FILE = "./state.json";

async function runPaidChecker(channel) {
  const feed = await parser.parseURL(process.env.PAID_FEED_URL);
  const state = JSON.parse(fs.readFileSync(STATE_FILE));
  const last = state.lastPaidGuid || "";
  
  const news = feed.items.filter(i => i.guid > last);
  for (let item of news) {
    await channel.send(`💰 New Paid Chapter: **${item.title}**\n${item.link}`);
  }
  
  if (news.length) {
    state.lastPaidGuid = news[0].guid;
    fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
  }
}

module.exports = { runPaidChecker };
