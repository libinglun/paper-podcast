# paper-podcast

A Claude Code skill that turns academic papers into podcasts. It picks a paper from your Zotero library, feeds it to Google NotebookLM to generate an Audio Overview, downloads the audio, and emails it to you with a digest — so you can listen to papers on the go.

## How it works

```
Zotero "To Review"  →  NotebookLM Audio Overview  →  Email with MP3 + digest
       ↓                                                      ↓
  Download PDF        Browser automation (Patchright)    Mark as processed
```

1. Reads your Zotero "To Review" collection via the Zotero API
2. Downloads the PDF attachment
3. Opens NotebookLM in a stealth browser, creates a notebook, uploads the PDF
4. Generates an Audio Overview (configurable format: deep dive, brief, critique, debate)
5. Downloads the resulting audio file
6. Emails you the audio + a short digest (title, authors, abstract summary)
7. Tags the paper as `podcast-generated` and moves it to "Listened" in Zotero

## Setup

### Prerequisites

- [Claude Code](https://claude.com/claude-code) CLI installed
- [uv](https://docs.astral.sh/uv/) for dependency management
- [notebooklm-skill](https://github.com/PleasePrompto/notebooklm-skill) installed at `~/.claude/skills/notebooklm/` (provides browser auth + stealth utilities)
- A [Zotero](https://www.zotero.org/) account with API key (read+write access)
- A [Resend](https://resend.com/) account for email delivery

### Install

```bash
# Clone into Claude Code skills directory
git clone https://github.com/libinglun/paper-podcast.git ~/.claude/skills/paper-podcast

# Copy and fill in secrets
cd ~/.claude/skills/paper-podcast
cp .env.example .env
# Edit .env with your Zotero API key, Resend API key, etc.

# Register the MCP server
claude mcp add paper-podcast -- uv run ~/.claude/skills/paper-podcast/server.py

# Make sure notebooklm skill is authenticated
cd ~/.claude/skills/notebooklm
python scripts/run.py auth_manager.py status
```

### Configure

Edit `config.json` to customize:

```jsonc
{
  "zotero": {
    "source_collection": "To Review",    // Pick papers from here
    "target_collection": "Listened",     // Move processed papers here
    "processed_tag": "podcast-generated" // Skip already-processed papers
  },
  "delivery": {
    "frequency": "daily",                // "daily" or "weekly"
    "time": "08:00",
    "target_email": "you@example.com"
  },
  "notebooklm": {
    "format": "deep-dive",               // deep-dive | brief | critique | debate
    "length": "default",                 // short | default | long
    "focus": null,                       // Optional prompt for the AI hosts
    "cleanup_notebooks": true,           // Delete notebooks after download
    "generation_timeout_minutes": 15
  }
}
```

## Usage

### On-demand

In Claude Code, just say:

```
paper to podcast
```

Or invoke the skill directly:

```
/paper-podcast
```

### Scheduled (cron)

```bash
# Daily at 8am
SKILL_DIR="$HOME/.claude/skills/paper-podcast"
(crontab -l 2>/dev/null | grep -v 'paper-podcast'; \
 echo "0 8 * * * cd $SKILL_DIR && bash scripts/run.sh >> cron.log 2>&1") | crontab -
```

## MCP Tools

The bundled `server.py` exposes 5 tools via FastMCP:

| Tool | Description |
|------|-------------|
| `list_collection_items` | List papers in a Zotero collection |
| `download_attachment` | Download PDF from Zotero to local disk |
| `move_item_to_collection` | Move paper between collections |
| `add_tag_to_item` | Tag a paper (e.g. as processed) |
| `send_email_with_attachment` | Send email with file attachment via Resend |

## Notes

- NotebookLM outputs M4A/DASH audio despite the `.mp3` extension — plays fine on all devices
- With Resend's free tier (`onboarding@resend.dev` sender), emails can only be delivered to your Resend account email
- Audio generation typically takes 2-5 minutes; the script auto-retries on transient failures
- The browser runs headless by default; add `--show-browser` to `generate_podcast.py` for debugging
