```markdown
# Discord Novel Arc Notifier

This project automatically checks RSS feeds for new novel arcs and sends formatted Discord notifications. It supports multiple novels with persistent arc history and NSFW detection (restricted by novel title). All messages use a global Discord webhook (set as a GitHub secret named `DISCORD_WEBHOOK`).

---

## 📂 User Setup Guide

### ✅ 1. Add a New Novel to Track
To add a new novel, update `config.json` with the following fields:

```json
{
  "novels": [
    {
      "name": "Your Novel Name",
      "role_mention": "<@&DISCORD_ROLE_ID>",
      "free_feed": "https://your-free-feed-url.xml",
      "paid_feed": "https://your-paid-feed-url.xml",
      "novel_title": "Your Novel Title",
      "novel_link": "https://your-novel-link/",
      "host": "Your Hosting Site",
      "custom_emoji": "<:EmojiID>",
      "discord_role_url": "https://discord.com/channels/YOUR_ROLE_URL",
      "history_file": "your_novel_history.json"
    }
  ]
}
```

Each novel must have a **unique `history_file`** to store its arc history.

---

## 🎯 Notes
- **No need to manually edit `tvitpa_history.json`** – It updates automatically.
- Arcs are stored persistently and prevent duplicate notifications.
- NSFW detection adds an extra Discord role mention.

---
🚀 **Now, you're ready to automate novel arc announcements to Discord!**
```
