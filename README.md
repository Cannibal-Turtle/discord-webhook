# Discord Novel Arc Notifier

This project automatically checks RSS feeds for new novel arcs and sends formatted Discord notifications. It supports multiple novels with persistent arc history and NSFW detection (restricted by novel title). All messages use a global Discord webhook (set as a GitHub secret named `DISCORD_WEBHOOK`).

---

## 📂 Files Overview

### 1️⃣ `config.json`
_Update the fields as needed._

```json
{
  "novels": [
    {
      "name": "Quick Transmigration",
      "role_mention": "<@&1329391480435114005>",
      "free_feed": "https://cannibal-turtle.github.io/rss-feed/free_chapters_feed.xml",
      "paid_feed": "https://cannibal-turtle.github.io/rss-feed/paid_chapters_feed.xml",
      "novel_title": "Quick Transmigration: The Villain Is Too Pampered and Alluring",
      "novel_link": "https://dragonholic.com/novel/quick-transmigration-the-villain-is-too-pampered-and-alluring/",
      "host": "Dragonholic",
      "custom_emoji": "<:Hehe:1329429547229122580>",
      "discord_role_url": "https://discord.com/channels/123/456/789",
      "history_file": "tvitpa_history.json"
    }
  ]
}
```

---

### 2️⃣ `tvitpa_history.json`
_Store previously unlocked and locked arcs._

```json
{
  "unlocked": [ "【Arc 1】 ..." ],
  "locked": [ "【Arc 6】 ..." ],
  "last_announced": ""
}
```

---

### 3️⃣ `new_arc_rss_checker.py`
_This script:_
- Loads novel settings from `config.json`
- Fetches free and paid RSS feeds
- Updates `tvitpa_history.json`
- Checks for a new locked arc and sends a Discord notification

---

## 🔧 Setup & Usage

### ✅ 1. Add GitHub Secrets
Go to **Settings > Secrets and variables > Actions** and add:
- **`DISCORD_WEBHOOK`** → Your Discord webhook URL

---

### 📌 2. Set Up GitHub Actions
Ensure `.github/workflows/rss_to_discord.yml` exists:

```yaml
name: Check RSS and Send to Discord

on:
  schedule:
    - cron: "0 16 * * *"  # Runs daily at 16:00 UTC
  workflow_dispatch:  # Allows manual trigger

jobs:
  rss_to_discord:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: pip install feedparser requests

      - name: Run RSS Checker
        run: python new_arc_rss_checker.py
        env:
          DISCORD_WEBHOOK: ${{ secrets.DISCORD_WEBHOOK }}
```

---

### 🚀 Running Manually
To trigger a manual check:
1. Go to **Actions** in your GitHub repository
2. Select **Check RSS and Send to Discord**
3. Click **Run workflow**

---

## 🎯 Notes
- Arcs are stored persistently in `tvitpa_history.json`
- The script prevents duplicate notifications
- NSFW detection adds an extra Discord role mention

---
🚀 **Now, you're ready to automate novel arc announcements to Discord!**
```
