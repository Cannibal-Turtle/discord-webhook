# Discord Novel Feed Bot

Discord bot scripts for posting novel feed updates, comments, new novel launches, new arcs, extras, Novel Updates analytics, and completion announcements.

This repo reads generated RSS feeds from `rss-feed`, imports novel metadata from `novel_mappings.py`, and posts announcements to Discord using the Discord bot API.

The old single-webhook setup is legacy. Current scripts use:

```text
DISCORD_BOT_TOKEN
channel IDs from repo secrets/config
```

---

## What This Repo Does

This repo handles:

1. **Free Chapter Announcements**

   * Posts new public/free chapters.

2. **Paid/Advance Chapter Announcements**

   * Posts new paid/locked/advance chapters.

3. **Comment Announcements**

   * Posts new comments from hosting sites and Novel Updates.

4. **New Novel Launch Alerts**

   * Detects first public drops like `Chapter 1`, `Ch. 1`, `Episode 1`, `Ep. 1`, `1.1`, or `Prologue`.

5. **New Arc Alerts**

   * Detects new locked/advance arcs.

6. **Side Story / Extra Alerts**

   * Detects when extras or side stories begin.

7. **Completion Announcements**

   * Announces when the final paid chapter appears.
   * Announces when the full series unlocks for free.

8. **Novel Updates Analytics**

   * Posts Novel Updates comment alerts.
   * Posts weekly reader statistics.

---

## Repository Structure

Important files and folders:

```text
discord-webhook/
├─ config/
│  ├─ embeds.json
│  ├─ feeds.json
│  ├─ files.json
│  ├─ novel_discord_map.toml
│  ├─ roles.json
│  └─ tag_roles.json
├─ arc_history/
│  ├─ tvitpa_history.json
│  ├─ tdlbkgc_history.json
│  └─ ...
├─ message_templates/
│  ├─ free_chapter.toml
│  ├─ paid_chapter.toml
│  ├─ comments.toml
│  ├─ new_novel.toml
│  └─ completed_novel.toml
├─ bot_free_chapters.py
├─ bot_paid_chapters.py
├─ bot_comments.py
├─ new_novel_checker.py
├─ new_arc_checker.py
├─ new_extra_checker.py
├─ completed_novel_checker.py
├─ nu_weekly_readers.py
├─ config_loader.py
├─ host_mistmint.py
└─ README.md

---

## Mapping Source

Novel metadata now comes from the `rss-feed` repo.

The `rss-feed` repo stores editable novel data in split TOML files:

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

`novel_mappings.py` remains the compatibility layer/front door.

---

## Install the RSS Mapping Package

The GitHub Actions workflow should install the latest `rss-feed` package:

```bash
pip install --upgrade git+https://github.com/Cannibal-Turtle/rss-feed.git@main
```

This lets scripts import:

```python
from novel_mappings import HOSTING_SITE_DATA
```

and helper functions like:

```python
get_novel_details_by_short_code(short_code)
find_novel_by_short_code(short_code)
short_code_has_free_chapters(short_code)
short_code_has_paid_chapters(short_code)
short_code_has_comments_feed(short_code)
```

---

## Required Python Dependencies

Install these in the workflow:

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

| Secret                             | Purpose                                                  |
| ---------------------------------- | -------------------------------------------------------- |
| `DISCORD_BOT_TOKEN`                | Discord bot token                                        |
| `DISCORD_CHANNEL_ID`               | General/news announcement channel                        |
| `DISCORD_FREE_CHAPTERS_CHANNEL`    | Free chapter posts                                       |
| `DISCORD_ADVANCE_CHAPTERS_CHANNEL` | Paid/advance chapter posts                               |
| `DISCORD_COMMENTS_CHANNEL`         | Comment posts                                            |
| `DISCORD_MOD_CHANNEL_ID`           | Optional mod/alert posts                                 |
| `GH_PAT`                           | Personal Access Token for workflow dispatch/history push |

Legacy only:

| Secret            | Purpose                                                     |
| ----------------- | ----------------------------------------------------------- |
| `DISCORD_WEBHOOK` | Old webhook URL, no longer required for current bot scripts |

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

A PAT may still be required for cross-repo dispatch.

---

## Config Files

Config lives in:

```text
config/
```

---

## `config/files.json`

This file stores paths used by scripts.

Example:

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

Optional future field:

```json
{
  "message_templates_dir": "message_templates"
}
```

Do not use the old field:

```json
"novel_role_id_map_file": "config/novel_role_id_map.json"
```

The old JSON role map has been replaced by TOML.

---

## `config/novel_discord_map.toml`

Discord-specific novel data belongs here.

This includes:

* Discord role ID
* Custom emoji
* Role URL

Example:

```toml
[TVITPA]
role_id = "1329391480435114005"
custom_emoji = "<:emoji_62:1365400946330435654>"
role_url = "https://discord.com/channels/1329384099609051136/1329419555600203776/1330466188349800458"

[TDLBKGC]
role_id = "1431675643078250646"
custom_emoji = "<:468087cutebunny:1431678613002125313>"
role_url = "https://discord.com/channels/1329384099609051136/1329419555600203776/1330466188349800458"

[AMLWC]
role_id = "1517842780003635240"
custom_emoji = "<:ghostcat:1517845090779791490>"
role_url = "https://discord.com/channels/1329384099609051136/1329419555600203776/1330466188349800458"
```

Use raw role IDs:

```toml
role_id = "1517842780003635240"
```

not role mentions:

```toml
role_id = "<@&1517842780003635240>"
```

The bot converts role IDs to mentions automatically.

---

## What Belongs in `rss-feed` vs `discord-webhook`

### `rss-feed/mappings/novels/*.toml`

Novel metadata belongs in `rss-feed`.

Examples:

```toml
title = "After the Male Leads Went Crazy, They All Turned Into Male Ghosts"
short_code = "AMLWC"
novel_url = "https://mistminthaven.com/novel/..."
featured_image = "https://mistminthaven.com/wp-content/uploads/cover.jpg"

has_free = true
has_paid = true
has_comments = true

is_nsfw = false
is_membership = false

chapter_count = "92 Chapters"
last_chapter = "Chapter 92"
start_date = ""
history_file = "arc_history/amlwc_history.json"

discord_color = "#c90016"
```

### `discord-webhook/config/novel_discord_map.toml`

Discord-only presentation data belongs here.

Examples:

```toml
[AMLWC]
role_id = "1517842780003635240"
custom_emoji = "<:ghostcat:1517845090779791490>"
role_url = "https://discord.com/channels/..."
```

Do not duplicate role IDs, custom emojis, or role URLs inside the RSS mapping.

---

## `config/embeds.json`

Embed colors are configured here.

JSON does not allow `#` comments. Use `_comment` if you want notes.

Example:

```json
{
  "_comment": "Color values can be fixed hex codes or \"novel\". When set to \"novel\", the bot uses theme_color/discord_color from rss-feed/mappings/novels/*.toml.",

  "colors": {
    "free_chapter": "FFF9BF",
    "paid_chapter": "A87676",
    "comments": "F0C7A4",
    "novel_updates_comments": "2D3F51",
    "new_novel": "AEC6CF",
    "arc_unlocked": "FFF9BF",
    "arc_locked": "A87676",
    "nu_weekly": "2D3F51"
  }
}
```

---

## Novel-Specific Embed Colors

Each color can use either a fixed hex code:

```json
"paid_chapter": "A87676"
```

or the novel’s default color from `rss-feed/mappings/novels/*.toml`:

```json
"paid_chapter": "novel"
```

When set to `"novel"`, the bot uses the novel’s:

```toml
theme_color = "#c90016"
```

or:

```toml
discord_color = "#c90016"
```

If no novel color is found, the script falls back to the default color.

Example mixed config:

```json
{
  "colors": {
    "free_chapter": "novel",
    "paid_chapter": "novel",
    "comments": "F0C7A4",
    "novel_updates_comments": "2D3F51",
    "new_novel": "novel",
    "arc_unlocked": "novel",
    "arc_locked": "novel",
    "nu_weekly": "2D3F51"
  }
}
```

Supported special values:

```text
novel
theme
theme_color
discord_color
```

Recommended value:

```json
"paid_chapter": "novel"
```

---

## `config/tag_roles.json`

This file maps novel tags to Discord role IDs.

Example:

```json
{
  "Quick Transmigration": "123456789",
  "Infinite Flow": "123456789",
  "Transmigration": "123456789",
  "BL": "123456789",
  "Comedy": "123456789"
}
```

Tags are normalized by lowercasing and trimming extra spaces.

---

## `config/feeds.json`

This file stores feed URLs or feed-related config used by the bots.

The actual RSS feed URLs normally come from `rss-feed` mapping data, but this file can still store repo-level feed config when needed.

---

## `config/roles.json`

This file stores global role config.

Example uses:

* Global announcement role
* NSFW role
* News role
* Other server-wide roles

Novel-specific roles should stay in:

```text
config/novel_discord_map.toml
```

not `roles.json`.

---

## Main Bot Scripts

| Script                       | Purpose                                  |
| ---------------------------- | ---------------------------------------- |
| `bot_free_chapters.py`       | Posts new free/public chapters           |
| `bot_paid_chapters.py`       | Posts new paid/advance chapters          |
| `bot_comments.py`            | Posts new comments                       |
| `new_novel_checker.py`       | Posts first public drop/new novel launch |
| `new_arc_checker.py`         | Posts new locked/advance arc alerts      |
| `new_extra_checker.py`       | Posts extras/side story alerts           |
| `completed_novel_checker.py` | Posts paid/free completion announcements |
| `nu_weekly_readers.py`       | Posts Novel Updates weekly reader stats  |

---

## Supported RSS Item Fields

The bots read generated RSS/XML feeds from `rss-feed`.

Example item:

```xml
<item>
  <title>After the Male Leads Went Crazy, They All Turned Into Male Ghosts</title>
  <volume>Arc 1: The Charming Landlord Is Too Hard to Handle</volume>
  <chapter>Chapter 2</chapter>
  <chaptername>***1.2***</chaptername>
  <link>https://mistminthaven.com/novel/.../chapter-2/</link>
  <description><![CDATA[A short chapter summary or excerpt...]]></description>
  <category>SFW</category>
  <translator>Cannibal Turtle</translator>
  <short_code>AMLWC</short_code>
  <featuredImage url="https://mistminthaven.com/wp-content/uploads/cover.jpg"/>
  <coin>🪙 5</coin>
  <pubDate>Fri, 18 Apr 2025 12:00:00 +0000</pubDate>
  <host>Mistmint Haven</host>
  <hostLogo url="https://mistminthaven.com/logo.png"/>
  <guid isPermaLink="false">amlwc-chapter-2</guid>
</item>
```

Important fields:

| Tag               | Purpose                                    |
| ----------------- | ------------------------------------------ |
| `<title>`         | Novel title                                |
| `<volume>`        | Arc/volume name                            |
| `<chapter>`       | Chapter label, used for completion checks  |
| `<chaptername>`   | Chapter title/name, used for arc detection |
| `<link>`          | Chapter URL                                |
| `<description>`   | Chapter summary/excerpt                    |
| `<category>`      | SFW/NSFW                                   |
| `<translator>`    | Translator name                            |
| `<short_code>`    | Stable novel short code                    |
| `<featuredImage>` | Cover image                                |
| `<coin>`          | Paid chapter cost/display                  |
| `<pubDate>`       | Publish date                               |
| `<host>`          | Hosting site                               |
| `<hostLogo>`      | Host logo                                  |
| `<guid>`          | Unique item ID                             |

Only `<chapter>` and `<link>` are strictly required for completion checks.

Arc alerts also use `<chaptername>` or `<volume>`.

---

## Feed Requirements Per Checker

### Free Chapter Bot

Requires:

```text
free_feed
```

Posts new public/free chapters.

---

### Paid Chapter Bot

Requires:

```text
paid_feed
```

Posts new paid/advance chapters.

---

### Comment Bot

Requires:

```text
comments_feed
```

Posts new comments.

---

### New Series Launch Alerts

Requires:

```text
free_feed
```

Behavior:

* Fires only when a public first drop appears.
* Detects labels like:

  * `Chapter 1`
  * `Ch. 1`
  * `Episode 1`
  * `Ep. 1`
  * `1.1`
  * `Prologue`
* Skips paywalled-only debuts.

---

### New Arc Alerts

Requires:

```text
free_feed
paid_feed
history_file
```

Behavior:

* Compares free/public arcs against paid/advance arcs.
* Announces newly locked/advance arcs.
* If either feed is missing, the novel is skipped.
* If `history_file = ""`, arc tracking is skipped.

---

### Extras / Side Story Alerts

Requires:

```text
paid_feed
```

Behavior:

* Announces when extras or side stories begin dropping in paid/advance access.
* Fires one time for each novel.

---

### Completion Announcements

Runs twice:

```bash
python completed_novel_checker.py --feed paid
python completed_novel_checker.py --feed free
```

#### Paid Completion

Requires:

```text
paid_feed
last_chapter
```

Announces when the final paid/advance chapter is out.

If `start_date` exists, the message can include:

```text
After X of updates...
```

If `start_date = ""`, it uses the shorter no-duration version.

#### Free Completion

Requires:

```text
free_feed
last_chapter
```

Announces when the full series is unlocked/free.

#### Only-Free Completion

If a novel only has a free feed and no paid feed, the free completion path acts like normal novel completion.

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

The matching RSS novel TOML should have:

```toml
history_file = "arc_history/amlwc_history.json"
```

For novels without arc tracking:

```toml
history_file = ""
```

The checker should skip empty history files safely.

Arc history prevents duplicate arc announcements.

---

## NSFW Behavior

NSFW status comes from the RSS feed item category and/or novel mapping.

If a chapter is NSFW, the bot can add an NSFW role mention.

Novel-wide NSFW status is configured in `rss-feed`:

```toml
is_nsfw = true
```

The feed generator may also mark an item NSFW if chapter/chaptername contains labels like:

```text
(NSFW)
(R-18)
(18+)
(H)
(HH)
(HHH)
```

---

## Allowed Mentions

Role pings should be controlled with allowed mentions.

Recommended behavior:

```json
{
  "allowed_mentions": {
    "parse": ["roles"]
  }
}
```

Use empty allowed mentions when a message should not ping.

---

## Link Preview Suppression

Where supported, bot payloads should suppress link preview embeds.

For Discord message flags:

```json
"flags": 4
```

This keeps the custom embed clean.

---

## Workflows

### Triggering from `rss-feed`

The `rss-feed` repo regenerates XML feeds, commits them, and can trigger this repo using a repository dispatch event.

Example dispatch:

```bash
curl -X POST \
  -H "Accept: application/vnd.github.v3+json" \
  -H "Authorization: Bearer $GH_PAT" \
  https://api.github.com/repos/Cannibal-Turtle/discord-webhook/dispatches \
  -d '{"event_type":"trigger-discord-notify"}'
```

---

### Discord Notifier Workflow

The workflow can listen for:

```yaml
on:
  repository_dispatch:
    types: [trigger-discord-notify]
  workflow_dispatch:
  schedule:
    - cron: "*/10 * * * *"
```

Jobs may run:

```bash
python bot_free_chapters.py
python bot_paid_chapters.py
python bot_comments.py
python new_novel_checker.py --feed free
python new_arc_checker.py
python new_extra_checker.py
python completed_novel_checker.py --feed paid
python completed_novel_checker.py --feed free
python nu_weekly_readers.py
```

Adjust scheduling and job order as needed.

---

## Bot Chapter Scripts

### `bot_free_chapters.py`

Posts free/public chapter announcements.

Expected behavior:

* Reads the free feed.
* Skips already-seen GUIDs.
* Posts oldest to newest.
* Uses the novel role from `config/novel_discord_map.toml`.
* Uses custom emoji from `config/novel_discord_map.toml`.
* Uses embed color from `config/embeds.json`.
* If color is `"novel"`, uses `discord_color` or `theme_color` from `rss-feed`.

---

### `bot_paid_chapters.py`

Posts paid/advance chapter announcements.

Expected behavior:

* Reads the paid feed.
* Skips already-seen GUIDs.
* Posts oldest to newest.
* Uses the novel role from `config/novel_discord_map.toml`.
* Uses custom emoji from `config/novel_discord_map.toml`.
* Uses embed color from `config/embeds.json`.
* If color is `"novel"`, uses `discord_color` or `theme_color` from `rss-feed`.

---

### `bot_comments.py`

Posts comments.

Expected behavior:

* Reads comments feed.
* Skips already-seen comment GUIDs.
* Cleans or formats comment text.
* Uses comments color from `config/embeds.json`.
* Uses `novel_updates_comments` color for Novel Updates comments when applicable.

If comments have a `short_code`, comments can also use `"comments": "novel"`.

If no short code is available, `"novel"` falls back to the script default.

---

## New Novel Launch Checker

`new_novel_checker.py` detects first public drops.

Requires:

```text
free_feed
```

It detects:

```text
Chapter 1
Ch. 1
Episode 1
Ep. 1
1.1
Prologue
```

It should not announce paywalled-only debuts.

Discord role URL and custom emoji come from:

```text
config/novel_discord_map.toml
```

not RSS mapping.

---

## New Arc Checker

`new_arc_checker.py` detects locked/advance arcs.

Requires:

```text
free_feed
paid_feed
history_file
```

It uses:

```text
volume
chaptername
chapter
```

to infer arc names and arc starts.

If `history_file` is missing or empty, the novel is skipped.

Arc history should be saved even when announcement posting fails, as long as the arc was detected and should not be announced repeatedly.

---

## New Extra Checker

`new_extra_checker.py` detects side stories/extras.

Requires:

```text
paid_feed
```

It fires once per novel when extras or side stories begin appearing in paid/advance content.

---

## Completion Checker

`completed_novel_checker.py` runs in two modes.

### Paid Mode

```bash
python completed_novel_checker.py --feed paid
```

Announces when the final paid/advance chapter is out.

Uses:

```text
last_chapter
chapter_count
start_date
paid_feed
```

### Free Mode

```bash
python completed_novel_checker.py --feed free
```

Announces when the full series is unlocked/free.

Uses:

```text
last_chapter
chapter_count
free_feed
```

If the novel has only free chapters, this also acts as the full translation completion announcement.

---

## Novel Updates Analytics

### Comments

Novel Updates comments can be posted through the comments bot.

Use a separate color key:

```json
"novel_updates_comments": "2D3F51"
```

### Weekly Readers

`nu_weekly_readers.py` posts weekly reader statistics.

Use:

```json
"nu_weekly": "2D3F51"
```

This color should usually stay fixed, not `"novel"`, because weekly stats may not belong to one novel embed color in every context.

---

## Adding a New Novel

### 1. Add Novel Metadata in `rss-feed`

Create a new TOML file:

```text
rss-feed/mappings/novels/code.toml
```

Required fields:

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

Optional fields:

```toml
chapter_count = ""
last_chapter = ""
start_date = ""
history_file = ""
discord_color = ""
custom_description = """
"""
```

---

### 2. Add Discord Data in This Repo

Edit:

```text
config/novel_discord_map.toml
```

Add:

```toml
[CODE]
role_id = "123456789"
custom_emoji = "<:emoji_name:123456789>"
role_url = "https://discord.com/channels/..."
```

---

### 3. Add Tag Roles if Needed

Edit:

```text
config/tag_roles.json
```

Example:

```json
{
  "Quick Transmigration": "123456789",
  "Comedy": "123456789"
}
```

---

### 4. Add Arc History if Needed

If the novel uses arc tracking, set this in `rss-feed` novel TOML:

```toml
history_file = "arc_history/code_history.json"
```

The file will live in this repo:

```text
discord-webhook/arc_history/code_history.json
```

If the novel does not use arc tracking, leave:

```toml
history_file = ""
```

---

### 5. Check Feed Flags

In `rss-feed` novel TOML:

```toml
has_free = true
has_paid = true
has_comments = true
```

Set these based on what the novel actually has.

Scripts may skip a novel if the required feed is missing.

---

## Adding a New Host

Most host-specific work happens in `rss-feed`.

In `rss-feed`:

1. Add host TOML:

   ```text
   mappings/hosts/new_host.toml
   ```

2. Add host utility logic in:

   ```text
   host_utils.py
   ```

3. Add novel TOML files under:

   ```text
   mappings/novels/
   ```

In this repo:

1. Make sure bot scripts can parse the feed output.
2. Add any Discord-specific config needed.
3. Add role/tag mappings if needed.

---

## Message Templates

Future message templates may live in:

```text
message_templates/
```

Recommended structure:

```text
message_templates/
├─ free_chapter.toml
├─ paid_chapter.toml
├─ comments.toml
├─ new_novel.toml
├─ completed_novel.toml
└─ membership_update.toml
```

These templates should stay top-level instead of inside `config/`, because they are editable message layouts rather than small config values.

Example paid chapter template shape:

```toml
content = "{role_mention}"

[[embeds]]
title = "{custom_emoji} {title}"
url = "{link}"
description = """
## {chapter} — {chaptername}

{volume}

{coin}

{description}
"""
color = "paid_chapter"

[embeds.thumbnail]
url = "{featured_image}"

[embeds.footer]
text = "{host} · {translator}"
icon_url = "{host_logo}"

[[embeds.fields]]
name = "Chapter"
value = "[{chapter} — {chaptername}]({link})"
inline = true
```

Templates require a renderer before scripts can use them.

---

## Message Templates

Discord message layouts are now handled through TOML files in:

```text
message_templates/
```

### Template mode

Most templates use:

```toml
mode = "classic"
```

`classic` means a normal Discord message payload: `content`, `embeds`, `components`, `allowed_mentions`, and `flags`.

Keep `mode = "classic"` unless a script/template is specifically updated for another payload style later.

### Multiline content

Use TOML literal strings for readable Discord messages:

```toml
content = '''
Line one
Line two
'''
```

The renderer strips the first/last template-only newline, but keeps intentional blank lines inside the message.

### Suppressing embeds

Use:

```toml
suppress_embeds = true
```

instead of manually setting Discord flags in Python.

### Allowed mentions

Mentions only ping if both are true:

1. the mention exists in `content`
2. `allowed_mentions` permits it

Role-ping example:

```toml
content = "{chapter_mention} New chapter!"

[allowed_mentions]
parse = ["roles"]
```

No-ping example:

```toml
[allowed_mentions]
parse = []
```

For user-only pings:

```toml
[allowed_mentions]
parse = []
users = ["{ping_user_id}"]
```

### Embeds

Embed colors can use config keys with fallback values:

```toml
color = { key = "paid_chapter", default = "A87676" }
```

Optional fields can use `_when` guards:

```toml
[embeds.thumbnail]
url = "{featured_image_url}"
url_when = "featured_image_url"
```

If the placeholder is empty, the guarded field is skipped.

### Buttons

Classic link buttons are written like this:

```toml
[components]
[[components.action_rows]]
[[components.action_rows.buttons]]
style = "link"
label = "Read here"
url = "{link}"
```

### Multi-message templates

Templates like `new_arcs.toml` can send multiple messages from one event:

```toml
[[messages]]
name = "header"
content = "..."

[[messages]]
name = "locked"
content = "..."
```

Each `[[messages]]` block can have its own `content`, `embeds`, `allowed_mentions`, `when`, and `suppress_embeds`.

Example conditional message:

```toml
[[messages]]
name = "unlocked"
when = "has_unlocked"
content = "Unlocked arcs:"
```

The message only sends when `has_unlocked` is truthy in the Python context.

### Editing rule

Edit TOML when changing Discord wording, emojis, spacing, embeds, colors, buttons, or ping behavior.

Edit Python only when changing detection logic, feed parsing, state handling, routing, or placeholder/context values.

---

## State Files

State files prevent duplicate posts.

Common state files:

```text
state.json
state_rss.json
nu_readers.json
```

These paths are configured in:

```text
config/files.json
```

Do not delete state files unless intentionally resetting the bot.

---

## Troubleshooting

### Bot reposted old items

Check:

```text
state.json
state_rss.json
```

The seen GUID may be missing or reset.

---

### Novel role did not ping

Check:

```text
config/novel_discord_map.toml
```

Make sure the short code matches exactly:

```toml
[AMLWC]
role_id = "1517842780003635240"
```

Also check `allowed_mentions`.

---

### Embed color crashed

If `config/embeds.json` says:

```json
"paid_chapter": "novel"
```

then the script must use:

```python
resolve_embed_color(...)
```

not:

```python
embed_color(...)
```

`embed_color(...)` expects a real hex color and will crash on `"novel"`.

---

### JSON config crashed

JSON does not support comments.

This is invalid:

```json
# comment
{
  "colors": {}
}
```

Use `_comment` instead:

```json
{
  "_comment": "This is a note.",
  "colors": {}
}
```

---

### Arc checker skipped a novel

Check the RSS novel TOML:

```toml
history_file = ""
```

If empty, arc checking skips the novel.

For arc tracking, set:

```toml
history_file = "arc_history/code_history.json"
```

Also make sure the novel has both:

```toml
has_free = true
has_paid = true
```

---

### Completion checker skipped a novel

Check:

```toml
last_chapter = ""
```

If empty, completion checking may skip the novel.

Set:

```toml
last_chapter = "Chapter 92"
chapter_count = "92 Chapters"
```

---

## Design Guarantees

* Discord-specific role IDs, emojis, and role URLs live in this repo.
* Novel metadata lives in `rss-feed`.
* `HOSTING_SITE_DATA` remains import-compatible through `novel_mappings.py`.
* Split TOML mappings are supported through the installed `rss-feed` package.
* Embed colors can use fixed hex values or `"novel"`.
* `"novel"` colors resolve to `theme_color` or `discord_color` from RSS novel TOML.
* Empty `history_file` safely skips arc tracking.
* Empty `start_date` safely removes the duration phrase from completion messages.
* State files prevent duplicate chapter/comment announcements.
* Arc history prevents duplicate arc announcements.
* Cross-repo dispatch can trigger notifier workflows automatically.

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

   * `has_free`
   * `has_paid`
   * `has_comments`
3. This repo has the short code in:

   * `config/novel_discord_map.toml`
4. `config/embeds.json` has valid colors.
5. If using `"novel"` colors, scripts use `resolve_embed_color(...)`.
6. If using arc tracking, `history_file` is set.
7. Required Discord channel secrets exist.
8. `DISCORD_BOT_TOKEN` exists.
9. Workflow installs the latest `rss-feed` package.
10. State/history files are committed after successful runs.

---

Now you are ready to automate chapter, comment, arc, extra, new novel, Novel Updates, and completion announcements to Discord.

---

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

