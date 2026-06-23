---
name: paper-podcast
description: Automated paper-podcast pipeline — picks a paper from Zotero "To Review" collection, uploads it to NotebookLM, generates an Audio Overview podcast, downloads the MP3, emails it with a digest, and marks the paper as processed. Supports on-demand and scheduled runs.
---

# Paper Podcast

Convert academic papers from your Zotero library into NotebookLM Audio Overview
podcasts, delivered to your inbox with a digest summary.

## When to Use This Skill

Trigger when the user:
- Says "paper to podcast", "generate podcast", "podcast my papers"
- Asks to process papers from Zotero into audio
- Wants to listen to a paper
- Invokes `/paper-podcast`
- Asks to set up or change the paper podcast schedule

## Configuration

All settings live in `config.json` in this skill's directory:

```json
{
  "zotero": {
    "source_collection": "To Review",    // Zotero collection to pick papers from
    "target_collection": "Listened",     // Move processed papers here
    "processed_tag": "podcast-generated" // Tag added after processing
  },
  "delivery": {
    "frequency": "daily",                // "daily" or "weekly"
    "time": "08:00",                     // Local time for scheduled runs
    "target_email": "user@example.com"   // Email for podcast delivery
  },
  "notebooklm": {
    "format": "deep-dive",               // "deep-dive", "brief", "critique", "debate"
    "length": "default",                 // "short", "default", "long"
    "focus": null,                       // Optional focus prompt for hosts
    "cleanup_notebooks": true,           // Delete NotebookLM notebooks after
    "generation_timeout_minutes": 15     // Max wait for audio generation
  }
}
```

Edit the file directly with file-writing tools when the user asks to change settings.

## Dependencies

This skill has two components:

1. **Bundled MCP server** (`server.py`) — Zotero read/write and email tools:
   - `list_collection_items(collection_name)` — list papers in a Zotero collection
   - `download_attachment(item_key, download_dir)` — download PDF from Zotero
   - `move_item_to_collection(item_key, target_collection)` — move paper after processing
   - `add_tag_to_item(item_key, tag)` — tag paper as processed
   - `send_email_with_attachment(subject, html, attachment_path, to)` — email with MP3

2. **NotebookLM browser automation** (`scripts/generate_podcast.py`):
   - Requires the [notebooklm skill](https://github.com/PleasePrompto/notebooklm-skill) to be installed at `~/.claude/skills/notebooklm/` for auth and browser utilities

## Core Workflow

### On-Demand: Process One Paper

When the user asks to process a paper:

**Step 1: Read config**
```bash
cat <skill-dir>/config.json
```

**Step 2: List papers in source collection**
Use the `list_collection_items` MCP tool:
- `collection_name` = config's `zotero.source_collection`
- Show the user the list of available papers

**Step 3: Pick a paper**
- If user specifies which paper, use that one
- If not, pick the first (oldest) unprocessed paper (one without the `processed_tag`)

**Step 4: Download PDF from Zotero**
Use the `download_attachment` MCP tool:
- `item_key` = the chosen paper's item_key
- `download_dir` = `/tmp/paper-podcast`
- If no PDF attachment exists, tell the user and skip

**Step 5: Generate podcast via NotebookLM**
```bash
cd ~/.claude/skills/notebooklm && python scripts/run.py generate_podcast.py \
  --pdf "<downloaded_pdf_path>" \
  --output "/tmp/paper-podcast/<paper_title_slug>.mp3" \
  --format "<config.notebooklm.format>" \
  --length "<config.notebooklm.length>" \
  --timeout "<config.notebooklm.generation_timeout_minutes * 60>"
```
Add `--focus "<text>"` if config has a focus prompt.
Add `--keep-notebook` if config has `cleanup_notebooks: false`.

**Step 6: Compose digest email**
Write a brief HTML email with:
- Paper title (as heading)
- Authors and venue
- 2-3 sentence summary of the paper (from the abstract)
- Note that the podcast is attached

**Step 7: Send email with MP3 attachment**
Use the `send_email_with_attachment` MCP tool:
- `subject` = "🎙️ Paper Podcast: <paper_title>"
- `html` = the composed digest HTML
- `attachment_path` = the MP3 file path
- `to` = config's `delivery.target_email`

**Step 8: Mark paper as processed**
Use MCP tools:
1. `add_tag_to_item(item_key, config.zotero.processed_tag)`
2. `move_item_to_collection(item_key, config.zotero.target_collection)`

**Step 9: Clean up temp files**
```bash
rm -f "<pdf_path>" "<mp3_path>"
```

**Step 10: Report to user**
Tell the user: paper title, podcast duration/size, email sent to address.

### Scheduled: Automatic Daily/Weekly

The scheduled run follows the same workflow as on-demand but:
- Automatically picks the first unprocessed paper
- Runs silently without user interaction
- Skips if no unprocessed papers remain

**Setting up the schedule:**
```bash
# Get current crontab
crontab -l 2>/dev/null

# Add paper-podcast cron entry
SKILL_DIR="$HOME/.claude/skills/paper-podcast"
# Daily at configured time:
(crontab -l 2>/dev/null | grep -v 'paper-podcast'; \
 echo "0 8 * * * cd $SKILL_DIR && bash scripts/run.sh >> cron.log 2>&1") | crontab -
# Weekly (Monday):
(crontab -l 2>/dev/null | grep -v 'paper-podcast'; \
 echo "0 8 * * 1 cd $SKILL_DIR && bash scripts/run.sh >> cron.log 2>&1") | crontab -
```

## Changing Settings

When the user asks to change any setting, edit `config.json` directly:
- "make it weekly" → change `delivery.frequency` to `"weekly"` and update crontab
- "use debate format" → change `notebooklm.format` to `"debate"`
- "send to different email" → change `delivery.target_email`
- "don't delete notebooks" → change `notebooklm.cleanup_notebooks` to `false`
- "change source collection" → change `zotero.source_collection`

## Error Handling

- **No papers in collection**: Tell user the source collection is empty
- **No PDF attachment**: Skip paper, tell user it has no PDF
- **NotebookLM generation fails**: Report error, don't mark paper as processed
- **Email fails**: Report error, but still mark paper (podcast was generated)
- **Zotero API error**: Report the specific error from the MCP tool response

## Troubleshooting

| Problem | Solution |
|---------|----------|
| NotebookLM auth expired | Run: `cd ~/.claude/skills/notebooklm && python scripts/run.py auth_manager.py reauth` |
| No PDF in Zotero item | User must attach PDF to the Zotero item manually |
| Audio generation timeout | Increase `notebooklm.generation_timeout_minutes` in config |
| Email not delivered | Check that `delivery.target_email` matches Resend account email |
| Cron not running | Check: `crontab -l` and verify the entry exists |
