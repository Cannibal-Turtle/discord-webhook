# Discord Novel Feed Bot

Discord bot scripts for posting novel feed updates, comments, new novel launches, new arcs, extras, and completion announcements.

This repo is the **general Discord announcement layer**. It reads generated RSS feeds from [`rss-feed`](https://github.com/Cannibal-Turtle/rss-feed), imports shared novel metadata from `novel_mappings.py`, then posts styled messages to Discord using the Discord bot API.

The old single-webhook setup is legacy. Current scripts use:

```text
DISCORD_BOT_TOKEN
channel IDs from GitHub secrets/config
```

---

## What This Repo Does

This repo handles:

1. **Free chapter announcements**
   - Posts new public/free chapters.

2. **Paid/advance chapter announcements**
   - Posts new paid/locked/advance chapters.

3. **Comment announcements**
   - Posts new comments from hosting sites.
   - Supports Novel Updates comment styling through the comments feed.

4. **New novel launch alerts**
   - Detects first public drops such as `Chapter 1`, `Ch. 1`, `Episode 1`, `Ep. 1`, `1.1`, or `Prologue`.

5. **New arc alerts**
   - Detects new locked/advance arcs using per-novel arc history.

6. **Side story / extra alerts**
   - Detects when extras or side stories begin.

7. **Completion announcements**
   - Announces when the final paid chapter appears.
   - Announces when the full series unlocks for free.
   - Supports only-free completion paths.

This repo no longer owns NU weekly reader reports. Those live in `rss-feed`.

---

## Repository Structure

Important files and folders:

```text
discord-webhook/
├─ .github/workflows/
│  ├─ chapters_discord.yml
│  ├─ comments_discord.yml
│  ├─ rss_to_discord.yml
│  └─ fix-embed-other-server.yml
├─ config/
│  ├─ embeds.json
│  ├─ feeds.json
│  ├─ files.json
│  ├─ novel_discord_map.toml
│  ├─ roles.json
│  └─ tag_roles.json
├─ arc_history/
│  ├─ amlwc_history.json
│  ├─ hiaflg_history.json
│  ├─ tdlbkgc_history.json
│  └─ tvitpa_history.json
├─ message_templates/
│  ├─ comments.toml
│  ├─ completed_novels.toml
│  ├─ free_chapters.toml
│  ├─ new_arcs.toml
│  ├─ new_extras.toml
│  ├─ new_novels.toml
│  └─ paid_chapters.toml
├─ requirements/
│  ├─ chapters.txt
│  ├─ comments.txt
│  └─ rss_dispatch.txt
├─ bot_free_chapters.py
├─ bot_paid_chapters.py
├─ bot_comments.py
├─ new_novel_checker.py
├─ new_arc_checker.py
├─ new_extra_checker.py
├─ completed_novel_checker.py
├─ config_loader.py
├─ message_context.py
├─ message_renderer.py
├─ state.json
├─ state_rss.json
├─ README.md
├─ PRIVACY.md
└─ TERMS.md
```

---

## Mapping Source

Novel metadata comes from the `rss-feed` repo.

`rss-feed` stores editable novel data in split TOML files:

```text
rss-feed/
├─ novel_mappings.py
└─ mappings/
   ├─ output_feeds.toml
   ├─ hosts/
   │  └─ mistmint_haven.toml
   └─ novels/
      ├─ tvitpa.toml
      ├─ tdlbkgc.toml
      ├─ amlwc.toml
      └─ ...
```

Even though the data is split into TOML files, this repo still imports:

```python
from novel_mappings import HOSTING_SITE_DATA
```

`novel_mappings.py` remains the compatibility front door.

---

## Install the RSS Mapping Package

The GitHub Actions workflows should install the latest `rss-feed` package:

```bash
pip install --upgrade git+https://github.com/Cannibal-Turtle/rss-feed.git@main
```

This lets scripts import:

```python
from novel_mappings import HOSTING_SITE_DATA
```

and helper functions such as:

```python
get_novel_details_by_short_code(short_code)
find_novel_by_short_code(short_code)
short_code_has_free_chapters(short_code)
short_code_has_paid_chapters(short_code)
short_code_has_comments_feed(short_code)
```

The installed package provides shared mappings, not this repo’s Discord configs.

---

## Required Python Dependencies

Use the requirement files in `requirements/` from the workflows.

Typical install commands are:

```bash
pip install -r requirements/chapters.txt
pip install -r requirements/comments.txt
pip install -r requirements/rss_dispatch.txt
pip install --upgrade git+https://github.com/Cannibal-Turtle/rss-feed.git@main
```

Common direct dependencies include:

```bash
pip install discord.py feedparser python-dateutil aiohttp requests tomli
```

`tomli` is only needed for Python versions below 3.11, but it is safe to include.

---

## GitHub Repository Secrets

Add these in:

```text
Settings → Secrets and variables → Actions
```

| Secret | Purpose |
| --- | --- |
| `DISCORD_BOT_TOKEN` | Discord bot token |
| `PAT_GITHUB` | Optional Personal Access Token for the free chapter → rss-feed status card update callback |

---

## GitHub Actions Permissions

Go to:

```text
Settings → Actions → General
```

Under workflow permissions, enable:

```text
Read and write permissions
```

Also allow actions and reusable workflows.

A PAT may still be needed for cross-repo dispatch.

---

## Config Files

### `config/files.json`

Central paths used by scripts:

```json
{
  "state_path": "state.json",
  "rss_state_path": "state_rss.json",
  "nu_readers_path": "nu_readers.json",
  "novel_discord_map_file": "config/novel_discord_map.toml",
  "tag_role_map_file": "config/tag_roles.json",
  "arc_history_dir": "arc_history"
}
```

`state_path` is for legacy/general state.

`rss_state_path` is for RSS dedupe keys such as:

```text
free_seen_guids
paid_seen_guids
comments_seen_guids
last_post_time_free
last_post_time_paid
last_post_time_comments
```

`arc_history_dir` stores per-novel arc tracking JSON.

---

### `config/feeds.json`

Defines RSS source URLs and state keys:

```json
{
  "free": {
    "url": "https://raw.githubusercontent.com/Cannibal-Turtle/rss-feed/main/free_chapters_feed.xml",
    "last_guid_key": "free_last_guid",
    "seen_key": "free_seen_guids",
    "last_post_time_key": "last_post_time_free"
  },
  "paid": {
    "url": "https://raw.githubusercontent.com/Cannibal-Turtle/rss-feed/main/paid_chapters_feed.xml",
    "last_guid_key": "paid_last_guid",
    "seen_key": "paid_seen_guids",
    "last_post_time_key": "last_post_time_paid"
  },
  "comments": {
    "url": "https://raw.githubusercontent.com/Cannibal-Turtle/rss-feed/main/aggregated_comments_feed.xml",
    "last_guid_key": "comments_last_guid",
    "seen_key": "comments_seen_guids",
    "last_post_time_key": "last_post_time_comments"
  },
  "seen_cap": 500,
  "time_backstop": true
}
```

`seen_cap` limits how many GUIDs are kept per feed.

`time_backstop` helps prevent old items from reposting after state resets.

---

### `config/server.json`

Server/channel behavior lives here. `translator_url` is optional and can be omitted.

```json
{
  "guild_id": "1329384099609051136",
  "free_chapters": "1329384438542499892",
  "paid_chapters": "1342475922581884968",
  "comments": "1361685556526055586",
  "announcements": "1330049962129489930",
  "mod": "1329655743799889962",
  "novel_cards_archive": "1463476725253144751",
  "announce_first_arc_release": true,
  "announce_first_chapter_release": true,
  "include_novel_updates_comments": true
}
```

Optional server-level fallback if you want the translator/profile link to be clickable even when it is not available from RSS or `rss-feed` mappings:

```json
{
  "translator_url": "https://www.mistminthaven.com/account/@CannibalTurtle-5082"
}
```

Translator/profile URL lookup order is RSS `translator_url`, then `rss-feed` mapping `translator_url`, then optional `config/server.json` `translator_url`, then empty string.

---

### `config/roles.json`

Global Discord role IDs:

```json
{
  "free_global": "1342483851338846288",
  "paid_global": "1342484466043453511",
  "new": "1329502873503006842",
  "ongoing": "1329502951764525187",
  "complete": "1329502614110474270",
  "nsfw": "1343352825811439616",
  "admin": "1329392448798982214"
}
```

Scripts convert IDs into mentions with:

```python
role_id_to_mention(role_id)
```

Keep IDs as raw numbers in JSON, not `<@&...>` strings.

---

### `config/novel_discord_map.toml`

Discord-only per-novel data lives here.

Example:

```toml
[AMLWC]
role_id = "1517842780003635240"
custom_emoji = "<:ghostcat:1517845090779791490>"
role_url = "https://discord.com/channels/.../..."
```

This file should contain:

| Field | Purpose |
| --- | --- |
| `role_id` | Novel role ID used for pings |
| `custom_emoji` | Novel emoji used in display text |
| `role_url` | Link to the role-selection message or channel |

Do **not** put title, host, feed flags, cover image, NSFW, membership, or chapter metadata here. Those belong in `rss-feed/mappings/novels/*.toml`.

---

### `config/tag_roles.json`

Tag-to-role map used for new novel announcements.

Keys should be lowercase/normalized tag names:

```json
{
  "quick transmigration": "1329427832077684736",
  "infinite flow": "1329428382089347102",
  "comedy": "1330469306936328286",
  "bl": "1330469077784727562"
}
```

Use this for language, genre, and content tags that should ping.

---

### `config/embeds.json`

Embed appearance settings:

```json
{
  "colors": {
    "free_chapter": "FFF9BF",
    "paid_chapter": "A87676",
    "comments": "F0C7A4",
    "novel_updates_comments": "2D3F51",
    "new_novel": "AEC6CF",
    "arc_unlocked": "FFF9BF",
    "arc_locked": "A87676"
  }
}
```

Colors can be:

```json
"FFF9BF"
```

or:

```json
"#FFF9BF"
```

Some message templates may also use:

```toml
color = { key = "paid_chapter", default = "A87676" }
```

or, where supported by Python:

```json
"paid_chapter": "novel"
```

`"novel"` means the script resolves the color from the novel TOML in `rss-feed`, usually `theme_color` or `discord_color`.

---

## What Belongs Where

### In `rss-feed/mappings/novels/*.toml`

Put novel metadata:

```toml
host = "Mistmint Haven"
title = "After the Male Leads Went Crazy, They All Turned Into Male Ghosts"
short_code = "AMLWC"
novel_url = "https://..."
featured_image = "https://..."

has_free = true
has_paid = true
has_comments = true

is_nsfw = false
is_membership = false

chapter_count = "93 Chapters"
last_chapter = "Chapter 93"
start_date = "2026-..."
history_file = "arc_history/amlwc_history.json"
discord_color = "#c90016"
```

### In `discord-webhook/config/novel_discord_map.toml`

Put Discord routing/display data:

```toml
[AMLWC]
role_id = "..."
custom_emoji = "<:...:...>"
role_url = "https://discord.com/channels/..."
```

---

## Main Bot Scripts

| Script | Purpose |
| --- | --- |
| `bot_free_chapters.py` | Reads free RSS feed and posts free chapter announcements |
| `bot_paid_chapters.py` | Reads paid RSS feed and posts paid/advance chapter announcements |
| `bot_comments.py` | Reads comments RSS feed and posts comment announcements |
| `new_novel_checker.py` | Detects first public chapter/new novel launch |
| `new_arc_checker.py` | Detects new advance/locked arcs |
| `new_extra_checker.py` | Detects side stories/extras |
| `completed_novel_checker.py` | Detects paid/free/only-free completion announcements |

All scripts share helpers from:

```text
config_loader.py
message_context.py
message_renderer.py
```

---

## Supported RSS Item Fields

The Discord scripts can use these values from the RSS item context:

```text
title
volume
chapter
chaptername
link
description
category
translator
short_code
featured_image_url
pub_date
pub_date_iso
host
host_logo_url
guid
guid_is_permalink
```

Templates can reference them as:

```toml
content = "New chapter for {title}"
description = "{chaptername}"
timestamp = "{pub_date_iso}"
```

---

## Message Templates

Templates live in:

```text
message_templates/
```

A basic template:

```toml
mode = "classic"
content = "{chapter_mention} New chapter for **{title}**"

[allowed_mentions]
parse = ["roles"]

[[embeds]]
title = "{chapter}"
url = "{link}"
description = "{chaptername}"
timestamp = "{pub_date_iso}"
color = { key = "free_chapter", default = "FFF9BF" }
```

### Template Modes

| Mode | Meaning |
| --- | --- |
| `classic` | Normal Discord content/embed/components payload |
| multi-message via `[[messages]]` | Sends several Discord messages in order |

### Conditions

Many fields support `*_when` keys:

```toml
description = "{chaptername}"
description_when = "chaptername"
```

If `chaptername` is empty, that field is dropped.

### Link Preview Suppression

For pure text messages where Discord link previews are unwanted:

```toml
suppress_embeds = true
```

### Allowed Mentions

Allowed mentions should be explicit:

```toml
[allowed_mentions]
parse = ["roles"]
```

or for messages that should not ping:

```toml
[allowed_mentions]
parse = []
```

If the content includes roles but `allowed_mentions` does not allow roles, the role text may appear without pinging.

### Embeds

Templates support embed fields such as:

```toml
[[embeds]]
title = "{title}"
url = "{link}"
description = "{description}"
color = { key = "comments", default = "F0C7A4" }

[embeds.author]
name = "{translator}"
url = "{translator_url}"
url_when = "translator_url"
```

`translator_url` is only a template placeholder. The scripts fill it from `translator_url`; do not configure it in `config/embeds.json`.

```toml

[embeds.thumbnail]
url = "{featured_image_url}"
url_when = "featured_image_url"

[embeds.footer]
text = "{host}"
icon_url = "{host_logo_url}"
icon_url_when = "host_logo_url"
```

### Buttons

Templates can include link buttons:

```toml
[components]
[[components.action_rows]]
[[components.action_rows.buttons]]
style = "link"
label = "Read here"
url = "{link}"
```

### Multi-Message Templates

`new_arcs.toml` uses a multi-message shape:

```toml
[[messages]]
name = "header"
content = "..."

[[messages]]
name = "unlocked"
when = "has_unlocked"
content = "..."

[[messages]]
name = "locked"
content = "..."
```

The Python checker builds one context, then `render_message_sequence(...)` sends the enabled messages in order.

---

## Feed Requirements Per Checker

### Free Chapter Bot

Needs free-feed items with:

```text
title
link
chapter
chaptername
host
short_code
pub_date/guid
```

### Paid Chapter Bot

Needs paid-feed items with:

```text
title
link
chapter
chaptername
host
short_code
category containing paid/locked/advance info
pub_date/guid
```

### Comment Bot

Needs comment-feed items with:

```text
title
link
author
comment_title/comment body/reply chain where available
host
short_code
pub_date/guid
```

### New Novel Checker

Detects first drops like:

```text
Chapter 1
Ch. 1
Episode 1
Ep. 1
1.1
Prologue
```

Uses RSS metadata + novel TOML to build a launch announcement.

### New Arc Checker

Uses paid feed + novel `history_file`.

If a novel has:

```toml
history_file = "arc_history/amlwc_history.json"
```

then arc tracking can run.

If it has:

```toml
history_file = ""
```

then the checker safely skips arc tracking for that novel.

### Extra Checker

Detects side stories/extras from chapter labels.

### Completion Checker

Supports:

- paid completion
- free completion/unlocked full series
- only-free completion

Uses fields such as:

```toml
chapter_count = "93 Chapters"
last_chapter = "Chapter 93"
start_date = ""
```

If `start_date = ""`, the duration phrase is safely omitted.

Completion banner behavior is configured at the top of `message_templates/completed_novels.toml`:

```toml
[settings.banner]
enabled = true
ratio = "8:3"
crop = "auto"
```

Set `ratio = "original"` to attach the full featured image without cropping or resizing. Other ratio values such as `4:1` or `8:3` create a cropped banner.

---

## Arc History

Arc history files live in:

```text
arc_history/
```

Example:

```text
arc_history/amlwc_history.json
```

Each file tracks which arcs were already announced so the bot does not repost old arcs.

For a new arc-tracked novel:

1. Add `history_file` in the novel TOML in `rss-feed`.
2. Create the matching JSON file in this repo.
3. Initialize it with valid JSON:

```json
{}
```

The current arc checker saves history even when an announcement is skipped, so stale old arcs do not keep triggering.

### First Chapter/Arc Launch Announcement Switch

By default, the arc checker treats the first detected arc as a bootstrap setup step. This prevents old or existing Arc 1 data from being announced accidentally when arc tracking is first added.

The switch lives in `config/server.json`:

```json
"announce_first_arc_release": false
"announce_first_chapter_release": false
```

The first detected arc is saved into arc history, but no first arc announcement is posted.

This works for:

* free-only first arc
* paid-only first arc
* first run where unlocked and locked arc sections both have content

The arc checker only renders sections that have content:

* `has_unlocked = true` shows the Unlocked section
* `has_locked = true` shows the Locked section

So a free-only first arc will not show an empty Locked embed, and a paid-only first arc will not show an empty Unlocked embed.

First chapter/arc announcements are also delayed until the new novel launch announcement has been recorded in state. This prevents the first arc announcement from posting before the new novel launch message.

---

## NSFW Behavior

NSFW status comes from the RSS/novel metadata, not the Discord mapping.

For RSS-generated items, the category can include NSFW text.

In `rss-feed` novel TOML:

```toml
is_nsfw = true
```

The Discord bot can then add the NSFW role from:

```json
config/roles.json
```

The series role and NSFW role are joined safely, so missing pieces do not create duplicate spaces.

---

## State Files

State files prevent duplicate posts.

Current files:

```text
state.json
state_rss.json
arc_history/*.json
```

The RSS state tracks seen GUIDs and last post times.

If a state file becomes empty or invalid, the bot can crash with:

```text
JSONDecodeError
```

Fix it by committing valid JSON:

```json
{}
```

---

## Workflows

### `chapters_discord.yml`

Runs the free and paid chapter bots.

Triggered by:

```text
repository_dispatch
workflow_dispatch
```

### `comments_discord.yml`

Runs the comments bot.

Triggered by:

```text
repository_dispatch
workflow_dispatch
```

### `rss_to_discord.yml`

Runs checker-style announcements such as:

```text
new arcs
new extras
completion checks
```

Triggered by:

```text
repository_dispatch
schedule
workflow_dispatch
```

### Optional free chapter status card update callback

Free chapter announcements can optionally trigger a status card refresh back in the `rss-feed` repo.

This flow is intentionally optional and non-fatal. If the callback config is missing, disabled, unreachable, or `PAT_GITHUB` is not configured, the free chapter announcement should still post normally.

Flow:

```text
rss-feed updates free_chapters_feed.xml
→ rss-feed dispatches discord-webhook with feed=free
→ bot_free_chapters.py posts the new free chapter message
→ status_update_dispatcher.py checks rss-feed config/integrations.json
→ if card_status_update.enabled=true, it sends repository_dispatch to rss-feed
→ rss-feed runs update_novel_status.yml
→ tools/update_novel_status.py updates the configured novel status card embeds
```

Required file in this repo:

```text
status_update_dispatcher.py
```

`bot_free_chapters.py` calls this after free chapter posts are sent:

```python
trigger_status_update(title, host)
```

The dispatcher reads the integration config from the URL configured in:

```json
{
  "rss_feed_integrations_url": "https://raw.githubusercontent.com/Cannibal-Turtle/rss-feed/main/config/integrations.json"
}
```

That value belongs in:

```text
config/files.json
```

Required config in `rss-feed/config/integrations.json`:

```json
{
  "card_status_update": {
    "enabled": true,
    "repo": "Cannibal-Turtle/rss-feed",
    "event_type": "update-novel-status"
  }
}
```

Required secret in the `discord-webhook` repo:

```text
PAT_GITHUB
```

`PAT_GITHUB` is only required for the optional status card update callback.

If `PAT_GITHUB` is missing, `status_update_dispatcher.py` should skip the callback and print a warning instead of crashing the free chapter bot.

Example skip behavior:

```text
⚠️ PAT_GITHUB missing; skipped optional card status update.
```

The chapter posting flow must not depend on this callback succeeding.

### `fix-embed-other-server.yml`

Manual maintenance workflow for patching/fixing embeds by URL.

---

## Adding a New Novel

### 1. Add Novel Metadata in `rss-feed`

Create:

```text
rss-feed/mappings/novels/code.toml
```

Required basics:

```toml
host = "Mistmint Haven"
title = "Novel Title"
short_code = "CODE"
novel_url = "https://..."
featured_image = "https://..."

has_free = true
has_paid = true
has_comments = true
is_nsfw = false
is_membership = false
```

Optional status/checker fields:

```toml
chapter_count = "93 Chapters"
last_chapter = "Chapter 93"
start_date = ""
history_file = ""
discord_color = "#c90016"
```

### 2. Add Discord Data in This Repo

Edit:

```text
config/novel_discord_map.toml
```

Add:

```toml
[CODE]
role_id = "..."
custom_emoji = "<:...:...>"
role_url = "https://discord.com/channels/..."
```

### 3. Add Tag Roles if Needed

Edit:

```text
config/tag_roles.json
```

Only add tags that should ping.

### 4. Add Arc History if Needed

If the novel uses arc tracking:

```toml
history_file = "arc_history/code_history.json"
```

Then create:

```text
arc_history/code_history.json
```

with:

```json
{}
```

### 5. Check Feed Flags

Make sure the novel TOML flags match the feeds you expect:

```toml
has_free = true
has_paid = true
has_comments = true
```

---

## Adding a New Host

For a new host:

1. Add a host TOML file in `rss-feed/mappings/hosts/`.
2. Add novel TOML files in `rss-feed/mappings/novels/`.
3. Implement host utilities in `rss-feed/host_utils/` if needed.
4. Ensure RSS feeds include the host’s items.
5. Add Discord role/emoji/role URL data in this repo if announcements should ping.
6. Add feed/channel handling here only if the host needs different Discord behavior.

Most new host metadata belongs in `rss-feed`, not this repo.

---

## Troubleshooting

### Bot reposted old items

Check:

```text
state_rss.json
seen GUID keys
last post time keys
config/feeds.json
```

Make sure state files are committed after successful workflow runs.

### Novel role did not ping

Check:

1. `config/novel_discord_map.toml` has the correct `role_id`.
2. The template has `allowed_mentions` with roles enabled.
3. The bot role has permission to mention the role.
4. The role is mentionable or the bot has enough permission to ping it.

### Embed color crashed

Check `config/embeds.json`.

Valid colors:

```json
"FFF9BF"
"#FFF9BF"
"novel"
```

Invalid colors:

```json
"yellow"
"FFF"
"not-a-color"
```

If using `"novel"`, make sure the novel TOML has:

```toml
discord_color = "#c90016"
```

or another supported novel color field.

### JSON config crashed

JSON does not allow comments or trailing commas.

Bad:

```json
{
  "state_path": "state.json", // comment
}
```

Good:

```json
{
  "state_path": "state.json"
}
```

### Arc checker skipped a novel

Check:

```toml
history_file = "arc_history/code_history.json"
```

If the field is empty, the skip is intentional.

Also confirm the history file exists and contains valid JSON.

### Completion checker skipped a novel

Check:

```toml
chapter_count = "93 Chapters"
last_chapter = "Chapter 93"
```

If `last_chapter` does not match the feed item’s chapter label, completion may not trigger.

---

## Design Guarantees

- Discord-specific role IDs, emojis, and role URLs live in this repo.
- Novel metadata lives in `rss-feed`.
- `HOSTING_SITE_DATA` remains import-compatible through `novel_mappings.py`.
- Split TOML mappings are supported through the installed `rss-feed` package.
- Embed colors can use fixed hex values or `"novel"` where supported.
- `"novel"` colors resolve to novel color fields from RSS novel TOML.
- Empty `history_file` safely skips arc tracking.
- Empty `start_date` safely removes the duration phrase from completion messages.
- State files prevent duplicate chapter/comment announcements.
- Arc history prevents duplicate arc announcements.
- Cross-repo dispatch can trigger notifier workflows automatically.

---

## Workflow Overview

```text
rss-feed regenerates XML feeds
   ↓
rss-feed dispatches event to discord-webhook
   ↓
discord-webhook installs latest rss-feed package
   ↓
bot scripts read feeds + HOSTING_SITE_DATA
   ↓
Discord announcements are posted
   ↓
state/history files are updated and committed
```

---

## Ready Checklist

Before running the notifier:

1. `rss-feed` has the novel TOML file.
2. `rss-feed` has the correct feed flags:
   - `has_free`
   - `has_paid`
   - `has_comments`
3. This repo has the short code in `config/novel_discord_map.toml`.
4. `config/embeds.json` has valid colors.
5. If using `"novel"` colors, the novel TOML has a valid color field.
6. If using arc tracking, `history_file` is set and the history JSON exists.
7. Required Discord channel secrets exist.
8. `DISCORD_BOT_TOKEN` exists.
9. The workflow installs the latest `rss-feed` package.
10. State/history files are committed after successful runs.

---

## How It Looks

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
