# Discord Novel Arc & Completion Notifier

Automatically monitors paid and free RSS feeds for your novels, tracks arc history, and fires two types of Discord announcements via webhook:

1. **New Arc Alerts** (locked‑advance content)
2. **Completion Announcements** when the final chapter appears (paid) and full series unlocks (free)

All notifications use a single Discord webhook URL stored in the `DISCORD_WEBHOOK` secret.

---

## ⚙️ GitHub Repository Settings

### 🔧 Repository Secrets Setup

| Name              | Value                                  |
|-------------------|----------------------------------------|
| `DISCORD_WEBHOOK` | Your Discord webhook URL               |
| `GH_PAT`          | Personal Access Token for history push |

### 🔑 1. Add the Discord Webhook URL to Secrets
1. Go to **Settings** → **Secrets and variables** → **Actions**.
2. Click **New repository secret**.
3. Set **Name** to `DISCORD_WEBHOOK`.
4. Set **Value** to your Discord webhook URL.
5. Click **Add secret**.

### 🔑 2. Add a Personal Access Token (PAT) from the Source Repository
To allow the script to update the **novel history JSON files** and push changes back to GitHub, you need to **generate and store a Personal Access Token (PAT) from the source repository that triggers this script**.

#### ✅ **Generate a PAT from the Source Repository**
1. Go to [GitHub Personal Access Tokens](https://github.com/settings/tokens).
2. Click **"Generate new token (classic)"**.
3. Select **Expiration** (no expiration).
4. Under **Scopes**, check:
   - ✅ `repo` (Full control of private repositories)
   - ✅ `workflow` (Required for GitHub Actions)
5. Click **Generate token** and **copy** it.

#### ✅ **Store the PAT in the Source Repository**
1. Go to **Settings** → **Secrets and variables** → **Actions**.
2. Click **New repository secret**.
3. Set **Name** to `GH_PAT`.
4. Set **Value** to the **Personal Access Token** copied earlier.
5. Click **Add secret**.

🚨 **Important:**  
- The PAT must be set in **the repository where GitHub Actions runs the script** (i.e., the **source repo that triggers Discord updates**).  
- If this repo is **forked**, the PAT must be added to the **forked repository’s** secrets, not just the original.

---

### 🛠️ 3. Set GitHub Actions Permissions
1. Go to **Settings** → **Actions** → **General**.
2. Under **Workflow permissions**, select:
   - ✅ **Allow all actions and reusable workflows**
   - ✅ **Read and write permissions**
3. Click **Save**.

---

## 📂 User Setup Guide

### 📋 4. Configuration to Add a New Novel to Track
To add a new novel, update `config.json` with the following fields:

```json
{
  "novels": [
    {
      "novel_title": "Your Novel Title",
      "role_mention": "<@&DISCORD_ROLE_ID>",
      "chapter_count": "Total number of chapters",
      "last_chapter": "Last chapter for novel",
      "start_date": "31/8/2024",
      "free_feed": "https://your-free-feed-url.xml",
      "paid_feed": "https://your-paid-feed-url.xml",
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
## 📑 Supported RSS Item Fields

The scripts look for these XML tags in each `<item>`:

| Tag           | Purpose                                             |
|---------------|-----------------------------------------------------|
| `<chaptername>` | Contains the chapter label (e.g. “Chapter 5”, “Extra 8”) — used to detect paid & free completions   |
| `<link>`        | URL to the chapter page — used to construct message links                                    |
| `<nameextend>`  | Used for arc detection (looks for markers like “001”, “(1)”, “.1”) when generating New Arc Alerts |
| `<volume>`      | Optional alternative base name for arcs if present                                           |

> Only `<chaptername>` and `<link>` are strictly required for completion checks. Arc alerts also use `<nameextend>` or `<volume>`.

---

## ⚙️ Workflows

### Feed Generation (in your feeds repo)

- `update-paid-feed.yml` and `update-free-feed.yml`:
  - Cron/dispatch regenerates the respective XML feed file.
  - Commits changes and triggers the notifier via:
    ```bash
    curl -X POST \
      -H "Accept: application/vnd.github.v3+json" \
      -H "Authorization: Bearer $GH_PAT" \
      https://api.github.com/repos/USER/discord-notifier/dispatches \
      -d '{"event_type":"trigger-discord-notify"}'
    ```

### Discord Notifier (in your notifier repo)

The workflow listens for:
- `on: repository_dispatch.types = [trigger-discord-notify]`
- A scheduled cron
- Manual workflow dispatch

**Jobs:**
1. **New Arc Checker**
   ```bash
   python new_arc_rss_checker.py
   ```
2. **Completion Checker**
   ```yaml
   - name: Paid Completion
     run: python completed_novel_checker.py --feed paid

   - name: Free Completion
     run: python completed_novel_checker.py --feed free
   ```
---

## 🎯 Notes
- If a novel has no history of previous arcs, then history file like `tvitpa_history.json` must be inserted manually before it can pick up automatically from the RSS feed.
- Arcs are stored persistently and prevent duplicate notifications.
- NSFW detection adds an extra Discord role mention.
- Every Discord webhook payload uses `"allowed_mentions":{"parse":["roles"]}` to color role pings and `"flags":4` to suppress all link‑preview embeds.

---
🚀 **Now, you're ready to automate new arc and novel completion announcements to Discord!**
