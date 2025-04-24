# Discord Novel Arc, Extras & Completion Notifier

Automatically monitors paid and free RSS feeds for your novels, tracks arc history, side stories/extras published, and fires three types of Discord announcements via webhook:

1. **New Arc Alerts** (locked‑advance content)
2. **Side Stories/Extra Alerts** (locked‑advance content, fires one time for each novel)
3. **Completion Announcements** when the final chapter appears (paid) and full series unlocks (free)

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

## 📂 User Setup Guide (pick one)

### Option 1:📋 Install Mapping Package

If you’d rather always pull the latest `novel_mappings.py` from the rss-feed repo, add this to your CI’s install step:
```
pip install --upgrade git+https://github.com/Cannibal-Turtle/rss-feed.git@main
```
Your `rss-feed repo` needs a `pyproject.toml` at its root, for example:

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "cannibal-turtle-rss-feed"
version = "0.1.0"
description = "Mapping data for feeds"
authors = [ { name = "Cannibal Turtle" } ]
readme = "README.md"
requires-python = ">=3.7"
license = { text = "MIT" }
classifiers = [
  "Programming Language :: Python :: 3",
]

[project.urls]
Homepage = "https://github.com/Cannibal-Turtle/rss-feed"

[tool.setuptools]
# explicitly list each standalone .py you want installed
py-modules = [
  "novel_mappings",
]
```
With that in place, you do not need a local `config.json`—both `new_arc_checker.py` and `completed_novel_checker.py` will import `HOSTING_SITE_DATA` directly.

### 📋 Option 2: Configuration to Add a New Novel to Track

Only if you choose not to install the mapping package.

1. Add or update config.json at the repo root:

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

2. Script changes in both `new_arc_checker.py` and `completed_novel_checker.py`:
- Remove the mapping-package import:
   ```diff
   - from novel_mappings import HOSTING_SITE_DATA
   ```
- Re-add your CONFIG_PATH constant:
   ```diff
   + CONFIG_PATH = "config.json"
   ```
- Bring back `load_config()` helper (which reads config.json).
- Swap the bottom if `__name__ == "__main__":` block to loop over:
  ```python
   config = load_config()
   state  = load_state()
   for novel in config["novels"]:
       process_novel(novel, state)
   save_state(state)```

> Each novel must have a **unique `history_file`** to store its arc history.

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
   ```fix
   python new_arc_checker.py
   ```
1. **New Extra Checker**
   ```fix
   python new_extra_checker.py
   ```
3. **Completion Checker**
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

---

## 🆕 UPDATE: New Bot Scripts (v2.1)

We’ve just added three standalone Python bots (migrated from MonitoRSS) that post directly as your own Discord bot:

| Script                     | Purpose                                            |
|----------------------------|----------------------------------------------------|
| `bot_free_chapters.py`     | Posts new **free** chapters (🔓) in oldest→newest order. |
| `bot_paid_chapters.py`     | Posts new **advance/paid** chapters (🔒) in oldest→newest order. |
| `bot_comments.py`          | Posts new comments with from hosting sites.

### 🔧 What You Need to Add

1. **Repository Secrets**  
   In **Settings → Secrets and variables → Actions**, add:

   | Name                              | Value                                            |
   |-----------------------------------|--------------------------------------------------|
   | `DISCORD_BOT_TOKEN`               | Bot’s token                    
   | `DISCORD_FREE_CHAPTERS_CHANNEL`   | Channel ID for free-chapter posts                |
   | `DISCORD_ADVANCE_CHAPTERS_CHANNEL`| Channel ID for paid-chapter posts                |
   | `DISCORD_COMMENTS_CHANNEL`        | Channel ID for comment posts                     |

2. **Dependencies**  
   Ensure your CI/workflow install step includes:
   ```bash
   pip install discord.py feedparser python-dateutil aiohttp
   ```
### 🔗 Triggering

These scripts are invoked by your `rss-feed` repository workflows, and can also be scheduled by cron.

### 📷 How It Looks

<table>
  <tr>
    <td align="center">
      <strong>Advance Chapters</strong><br/>
      <img src="https://github.com/user-attachments/assets/8ec6e5c2-4125-496a-9681-2bf602f0e7ee" width="300" alt="Advance Chapters screenshot"/>
    </td>
    <td align="center">
      <strong>Free Chapters</strong><br/>
      <img src="https://github.com/user-attachments/assets/e0a6dfb2-2705-41b3-bd8e-a3bb8280ae1b" width="300" alt="Free Chapters screenshot"/>
    </td>
  </tr>
  <tr>
    <td colspan="2" align="center">
      <strong>Comments</strong><br/>
      <img src="https://github.com/user-attachments/assets/85db67db-683f-4059-b969-05c2ca15b285" width="600" alt="Comments screenshot"/>
    </td>
  </tr>
</table>



