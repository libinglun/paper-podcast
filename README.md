# Paper Podcast

Turn academic papers into podcasts automatically. Drop a paper into your Zotero "To Review" collection, and Paper Podcast will feed it to Google NotebookLM, generate an Audio Overview, and email you the audio with a short digest — so you can listen to papers on the go.

**You never edit JSON.** Just tell Claude what you want — it handles the config for you.

---

## What You Get

A podcast-style audio episode for each paper, delivered to your inbox with:

- The paper's title, authors, and venue
- A short digest summarising the key ideas
- The full audio file attached (playable on any device)
- The paper automatically tagged and moved to a "Listened" collection in Zotero

You choose the podcast format — deep dive, brief overview, critique, or debate — and how often you want them (daily, weekly, or on demand).

---

## How It Works

```
Zotero "To Review"  ──►  Download PDF  ──►  NotebookLM Audio Overview  ──►  Email + MP3
                                                                              │
                                                              Tag & move to "Listened"
```

1. Picks the next unprocessed paper from your Zotero collection
2. Downloads the PDF attachment via the Zotero API
3. Opens NotebookLM in a stealth browser, creates a notebook, uploads the PDF
4. Generates an Audio Overview (with auto-retry on transient failures)
5. Downloads the audio file
6. Emails you the audio with a digest of the paper
7. Tags the paper as processed and moves it to your "Listened" collection

---

## What You Need

Collect these before starting. Claude will walk you through each one during setup.

- **[Claude Code](https://docs.anthropic.com/en/docs/claude-code)** — the AI assistant this skill runs inside
- **[uv](https://docs.astral.sh/uv/)** — a lightweight Python tool runner; one install command, no configuration
- **[notebooklm-skill](https://github.com/PleasePrompto/notebooklm-skill)** — browser automation for NotebookLM (handles authentication and stealth)
- **[Zotero API key](https://www.zotero.org/settings/keys)** — free; needs read+write access to your library
- **[Zotero numeric user ID](https://www.zotero.org/settings/keys)** — the number shown next to "Your userID for use in API calls"
- **[Resend API key](https://resend.com/api-keys)** — free tier is enough; this is what sends the email

> **Don't have everything yet?** No problem. Start the setup and Claude will guide you step by step.

---

## Quick Start

**1. Install the skill** — clone into your skills folder:

```bash
git clone https://github.com/libinglun/paper-podcast.git ~/.claude/skills/paper-podcast
```

**2. Install the NotebookLM skill** (if you haven't already):

```bash
git clone https://github.com/PleasePrompto/notebooklm-skill.git ~/.claude/skills/notebooklm
```

**3. Set up secrets** — copy the template and fill in your keys:

```bash
cd ~/.claude/skills/paper-podcast
cp .env.example .env
# Edit .env with your Zotero API key, Resend API key, etc.
```

**4. Register the MCP server:**

```bash
claude mcp add paper-podcast -- uv run ~/.claude/skills/paper-podcast/server.py
```

**5. Authenticate NotebookLM** (one-time browser login):

```bash
cd ~/.claude/skills/notebooklm
python scripts/run.py auth_manager.py setup
```

**6. Say "paper to podcast"** or type `/paper-podcast` in Claude Code.

Claude picks the next paper from your Zotero "To Review" collection, generates a podcast, and emails it to you.

---

## Changing Settings

Just tell Claude what you want. No JSON editing required.

| Say this...                       | What happens                                    |
|-----------------------------------|-------------------------------------------------|
| "Use debate format"               | Switches podcast style to a two-host debate     |
| "Make it weekly"                  | Updates frequency and reschedules the cron job  |
| "Send to a different email"       | Updates the recipient address                   |
| "Make the episodes shorter"       | Switches audio length to short                  |
| "Don't delete notebooks after"    | Keeps NotebookLM notebooks for later reference  |
| "Change source collection"        | Picks papers from a different Zotero collection |
| "Focus on methodology"            | Adds a focus prompt for the AI hosts            |
| "Show my current settings"        | Prints your full config                         |

---

## Podcast Formats

NotebookLM supports four Audio Overview formats:

| Format | Description |
|--------|-------------|
| **Deep dive** (default) | Two hosts explore the paper in depth — like a study group |
| **Brief** | Quick summary hitting the key points |
| **Critique** | Hosts critically analyse the methodology and claims |
| **Debate** | Hosts take opposing sides on the paper's conclusions |

Each format also has three length options: **short**, **default**, or **long**.

---

## Scheduling

Paper Podcast can run automatically on a schedule, processing one paper per run.

**Set up via conversation:**
- "Run paper podcast every morning at 8"
- "Run it weekly on Mondays"

**Or manually via cron:**

```bash
# Daily at 8am
SKILL_DIR="$HOME/.claude/skills/paper-podcast"
(crontab -l 2>/dev/null | grep -v 'paper-podcast'; \
 echo "0 8 * * * cd $SKILL_DIR && bash scripts/run.sh >> cron.log 2>&1") | crontab -
```

Requires your machine to be awake at the scheduled time and `claude` CLI authenticated. Remove anytime with `crontab -e`.

---

## Troubleshooting

**NotebookLM auth expired** — re-authenticate:
```bash
cd ~/.claude/skills/notebooklm && python scripts/run.py auth_manager.py reauth
```

**No PDF in Zotero item** — the paper needs a PDF attachment in Zotero. Drag-and-drop a PDF onto the item, or use a browser extension to save the full text.

**Audio generation times out** — tell Claude "increase the generation timeout" or manually raise `generation_timeout_minutes` in config.json. Some longer papers take 10+ minutes.

**Email not delivered** — with Resend's free tier (`onboarding@resend.dev` sender), emails can only be delivered to your own Resend account email. Make sure `target_email` matches.

**MCP server won't start** — run `uv run server.py` inside the skill folder to see the error directly.

**Browser lock files** — if a previous run was interrupted, stale lock files may block new sessions. Kill any lingering Chrome processes and retry.

---

## Privacy

- All processing happens locally on your machine
- Your Zotero credentials and API keys stay in `.env` (git-ignored, never committed)
- NotebookLM access uses your own Google account via a local browser session
- No data is sent to third parties beyond Zotero, NotebookLM, and Resend (for email delivery)

---

## License

MIT
