# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "fastmcp>=2.0.0",
#   "httpx>=0.27",
#   "pyzotero>=1.5.18",
#   "resend>=2.0.0",
#   "python-dotenv>=1.0",
# ]
# ///
"""
Paper-Podcast MCP server.

Provides Zotero library access and email delivery tools for the
paper-to-podcast pipeline:

  1. list_collection_items  -> read papers from a Zotero collection
  2. download_attachment    -> download PDF attachment to local disk
  3. move_item_to_collection -> move item between collections
  4. add_tag_to_item        -> tag a paper as processed
  5. send_email_with_attachment -> email with MP3/file attachment via Resend

Run with:  uv run server.py
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv(Path(__file__).resolve().parent / ".env")

mcp = FastMCP("paper-podcast")


def _zotero_client():
    from pyzotero import zotero

    api_key = os.environ.get("ZOTERO_API_KEY", "").strip()
    library_id = os.environ.get("ZOTERO_LIBRARY_ID", "").strip()
    library_type = os.environ.get("ZOTERO_LIBRARY_TYPE", "user").strip() or "user"
    if not api_key or not library_id:
        raise RuntimeError("ZOTERO_API_KEY and ZOTERO_LIBRARY_ID must be set in .env.")
    return zotero.Zotero(library_id, library_type, api_key)


def _resolve_collection(zot, collection_name: str) -> tuple[str, bool]:
    for col in zot.collections():
        if col.get("data", {}).get("name") == collection_name:
            return col["key"], False
    resp = zot.create_collections([{"name": collection_name}])
    return resp["successful"]["0"]["key"], True


@mcp.tool
def list_collection_items(
    collection_name: str,
    tag_filter: str | None = None,
) -> dict[str, Any]:
    """List all items in a Zotero collection.

    Args:
        collection_name: Name of the collection to read from.
        tag_filter: If set, only return items that have this tag.

    Returns:
        Each item has: item_key, title, authors, abstract, date, venue, doi, url, tags.
    """
    try:
        zot = _zotero_client()
        collection_key = None
        for col in zot.collections():
            if col.get("data", {}).get("name") == collection_name:
                collection_key = col["key"]
                break
        if not collection_key:
            return {"ok": False, "items": [], "count": 0,
                    "error": f"Collection '{collection_name}' not found."}

        raw_items = zot.everything(zot.collection_items(collection_key))
        items = []
        for it in raw_items:
            data = it.get("data", {})
            if data.get("itemType") == "attachment":
                continue
            tags = [t["tag"] for t in data.get("tags", [])]
            if tag_filter and tag_filter not in tags:
                continue
            creators = data.get("creators", [])
            authors = [
                f"{c.get('firstName', '')} {c.get('lastName', '')}".strip()
                for c in creators if c.get("creatorType") == "author"
            ]
            items.append({
                "item_key": it["key"],
                "title": data.get("title", ""),
                "authors": authors,
                "abstract": data.get("abstractNote", ""),
                "date": data.get("date", ""),
                "venue": data.get("publicationTitle", ""),
                "doi": data.get("DOI", ""),
                "url": data.get("url", ""),
                "tags": tags,
            })
        return {"ok": True, "items": items, "count": len(items), "error": None}
    except Exception as exc:
        return {"ok": False, "items": [], "count": 0, "error": str(exc)}


@mcp.tool
def download_attachment(
    item_key: str,
    download_dir: str,
) -> dict[str, Any]:
    """Download the PDF attachment of a Zotero item to a local directory.

    Args:
        item_key: The Zotero item key (parent item, not the attachment itself).
        download_dir: Directory to save the file into.
    """
    try:
        zot = _zotero_client()
        children = zot.children(item_key)
        att = None
        for child in children:
            cd = child.get("data", {})
            if cd.get("itemType") == "attachment" and cd.get("contentType", "").startswith("application/pdf"):
                att = child
                break
        if not att:
            return {"ok": False, "path": None, "filename": None,
                    "error": f"No PDF attachment found for item {item_key}."}

        dest = Path(download_dir)
        dest.mkdir(parents=True, exist_ok=True)
        filename = att["data"].get("filename", f"{item_key}.pdf")
        filepath = dest / filename
        zot.dump(att["key"], filename, dest)
        return {"ok": True, "path": str(filepath), "filename": filename, "error": None}
    except Exception as exc:
        return {"ok": False, "path": None, "filename": None, "error": str(exc)}


@mcp.tool
def move_item_to_collection(
    item_key: str,
    target_collection: str,
    remove_from_source: bool = True,
) -> dict[str, Any]:
    """Move a Zotero item into a different collection.

    Args:
        item_key: The Zotero item key.
        target_collection: Name of the destination collection (created if missing).
        remove_from_source: If True, remove from all other collections.
    """
    try:
        zot = _zotero_client()
        target_key, _ = _resolve_collection(zot, target_collection)
        item = zot.item(item_key)
        data = item["data"]
        if remove_from_source:
            data["collections"] = [target_key]
        else:
            cols = data.get("collections", [])
            if target_key not in cols:
                cols.append(target_key)
            data["collections"] = cols
        zot.update_item(item)
        return {"ok": True, "collection_key": target_key, "error": None}
    except Exception as exc:
        return {"ok": False, "collection_key": None, "error": str(exc)}


@mcp.tool
def add_tag_to_item(
    item_key: str,
    tag: str,
) -> dict[str, Any]:
    """Add a tag to an existing Zotero item.

    Args:
        item_key: The Zotero item key.
        tag: Tag string to add.
    """
    try:
        zot = _zotero_client()
        item = zot.item(item_key)
        tags = item["data"].get("tags", [])
        if not any(t["tag"] == tag for t in tags):
            tags.append({"tag": tag})
            item["data"]["tags"] = tags
            zot.update_item(item)
        return {"ok": True, "error": None}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool
def send_email_with_attachment(
    subject: str,
    html: str,
    attachment_path: str,
    attachment_filename: str | None = None,
    to: str | None = None,
) -> dict[str, Any]:
    """Send an email with a file attachment via Resend.

    Args:
        subject: Email subject line.
        html: Email body as HTML.
        attachment_path: Absolute path to the file to attach.
        attachment_filename: Filename for the attachment in the email.
        to: Recipient address. Defaults to the RESEND_TO env var.
    """
    import resend

    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    if not api_key:
        return {"ok": False, "id": None, "error": "RESEND_API_KEY is not set.", "to": to or ""}

    sender = os.environ.get("RESEND_FROM", "onboarding@resend.dev").strip()
    recipient = (to or os.environ.get("RESEND_TO", "")).strip()
    if not recipient:
        return {"ok": False, "id": None, "error": "No recipient (set RESEND_TO or pass `to`).", "to": ""}

    file_path = Path(attachment_path)
    if not file_path.exists():
        return {"ok": False, "id": None, "error": f"File not found: {attachment_path}", "to": recipient}

    filename = attachment_filename or file_path.name
    file_content = base64.b64encode(file_path.read_bytes()).decode("ascii")

    resend.api_key = api_key
    try:
        result = resend.Emails.send({
            "from": sender,
            "to": [recipient],
            "subject": subject,
            "html": html,
            "attachments": [{"filename": filename, "content": file_content}],
        })
        return {"ok": True, "id": result.get("id"), "error": None, "to": recipient}
    except Exception as exc:
        return {"ok": False, "id": None, "error": str(exc), "to": recipient}


if __name__ == "__main__":
    mcp.run()
