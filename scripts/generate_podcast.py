#!/usr/bin/env python3
"""
Generate an Audio Overview (podcast) from a PDF via NotebookLM.

Flow:
  1. Create a new notebook
  2. Upload PDF as source
  3. Open Audio Overview customise dialog
  4. Configure format/length and click Generate
  5. Wait for generation to complete
  6. Download the audio file
  7. Optionally delete the notebook

Usage:
  python scripts/run.py generate_podcast.py \
    --pdf /path/to/paper.pdf \
    --output /path/to/output.mp3 \
    [--format deep-dive|brief|critique|debate] \
    [--length short|default|long] \
    [--focus "What should hosts focus on"] \
    [--keep-notebook] \
    [--show-browser]
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from patchright.sync_api import sync_playwright
from auth_manager import AuthManager
from browser_utils import BrowserFactory, StealthUtils

GENERATION_TIMEOUT_SECONDS = 900  # 15 minutes
GENERATION_POLL_INTERVAL = 10

FORMAT_MAP = {
    "deep-dive": "Deep dive",
    "brief": "Brief",
    "critique": "Critique",
    "debate": "Debate",
}

LENGTH_MAP = {
    "short": "Short",
    "default": "Default",
    "long": "Long",
}


def wait_for_notebook_ready(page, timeout=30):
    """Wait until the notebook is fully loaded (not 'creating')."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        url = page.url
        title = page.title()
        if "/creating" not in url and "Creating" not in title:
            return True
        time.sleep(1)
    return False


def create_notebook(page, max_retries=3):
    """Navigate to NotebookLM and create a new notebook. Returns notebook URL."""
    for attempt in range(1, max_retries + 1):
        print(f"  📓 Creating new notebook (attempt {attempt}/{max_retries})...")
        page.goto("https://notebooklm.google.com/", wait_until="domcontentloaded")
        time.sleep(5)

        create_btn = page.wait_for_selector(
            "button[aria-label='Create new notebook']", timeout=15000
        )
        create_btn.click()

        # Wait for the notebook to be created and URL to stabilize
        print("  ⏳ Waiting for notebook to initialize...")
        time.sleep(10)

        if wait_for_notebook_ready(page, timeout=30):
            notebook_url = page.url
            if "/notebook/" in notebook_url and "/creating" not in notebook_url:
                print(f"  ✅ Notebook created: {notebook_url}")
                return notebook_url

        # Check for error toast / "Try again" button
        try:
            retry_btn = page.query_selector("button:has-text('Try again')")
            if retry_btn and retry_btn.is_visible():
                print("  ⚠️ NotebookLM returned an error, retrying...")
                retry_btn.click()
                time.sleep(3)
                continue
        except Exception:
            pass

        # Check for snackbar/toast error text
        print(f"  ⚠️ Creation may have failed (URL: {page.url}), retrying...")
        time.sleep(3)

    raise RuntimeError("Failed to create notebook after multiple attempts")


def upload_pdf(page, pdf_path):
    """Upload a PDF file to the current notebook."""
    print(f"  📄 Uploading PDF: {pdf_path}")

    # The upload dialog may already be open for new notebooks.
    # If not, click "Add sources"
    upload_btn = page.query_selector("button:has-text('Upload files')")
    if not upload_btn:
        add_src = page.query_selector("button[aria-label='Add source']")
        if add_src:
            add_src.click()
            time.sleep(2)
        upload_btn = page.wait_for_selector(
            "button:has-text('Upload files')", timeout=10000
        )

    with page.expect_file_chooser() as fc_info:
        upload_btn.click()

    file_chooser = fc_info.value
    file_chooser.set_files(str(pdf_path))
    print("  ⏳ Waiting for source processing...")

    # Wait for the source to appear in the sources panel
    deadline = time.time() + 60
    while time.time() < deadline:
        sources = page.query_selector("section.source-panel")
        if sources:
            text = sources.inner_text()
            filename = Path(pdf_path).name
            if filename in text or "source" in text.lower():
                # Check if still processing
                if "processing" not in text.lower() and "uploading" not in text.lower():
                    break
        time.sleep(2)

    # Close upload dialog if still open
    try:
        close_btn = page.query_selector("[role='dialog'] button[aria-label='Close']")
        if close_btn and close_btn.is_visible():
            close_btn.click()
            time.sleep(1)
    except Exception:
        pass  # Dialog may have auto-closed

    # Also try pressing Escape to dismiss any remaining overlay
    page.keyboard.press("Escape")
    time.sleep(1)

    print("  ✅ Source uploaded")


def generate_audio_overview(page, format_type="deep-dive", length="default", focus=None):
    """Open Audio Overview dialog, configure, and click Generate."""
    print("  🎙️ Opening Audio Overview...")

    # Click "Customise Audio Overview"
    audio_btn = page.wait_for_selector(
        "button[aria-label='Customise Audio Overview']", timeout=15000
    )
    audio_btn.click()
    time.sleep(3)

    # Select format
    format_label = FORMAT_MAP.get(format_type, "Deep dive")
    print(f"  📋 Format: {format_label}")
    fmt_btn = page.query_selector(f"button:has-text('{format_label}')")
    if fmt_btn and fmt_btn.is_visible():
        fmt_btn.click()
        time.sleep(0.5)

    # Select length
    length_label = LENGTH_MAP.get(length, "Default")
    print(f"  📏 Length: {length_label}")
    len_btn = page.query_selector(f"button:has-text('{length_label}')")
    if len_btn and len_btn.is_visible():
        len_btn.click()
        time.sleep(0.5)

    # Set focus prompt
    if focus:
        print(f"  🎯 Focus: {focus}")
        textarea = page.query_selector(
            "textarea[aria-label='What should the AI hosts focus on in this episode?']"
        )
        if textarea:
            textarea.click()
            textarea.fill(focus)
            time.sleep(0.5)

    # Click Generate
    print("  🚀 Clicking Generate...")
    gen_btn = page.query_selector("button:has-text('Generate')")
    if not gen_btn:
        print("  ❌ Generate button not found")
        return False

    gen_btn.click()
    print("  ✅ Generation started")
    return True


def wait_for_audio_ready(page, timeout=GENERATION_TIMEOUT_SECONDS, max_retries=3):
    """Wait for the audio to be generated. Handles retry prompts. Returns True when ready."""
    print(f"  ⏳ Waiting for audio generation (up to {timeout // 60} min)...")
    deadline = time.time() + timeout
    start = time.time()
    retries_used = 0

    while time.time() < deadline:
        elapsed = int(time.time() - start)

        # Check for play button appearing in studio (indicates audio is ready)
        play_btns = page.query_selector_all("button[aria-label='Play']")
        visible_play = [b for b in play_btns if b.is_visible()]
        if visible_play:
            print(f"  ✅ Audio ready! (took {elapsed}s)")
            return True

        # Check for retry button (NotebookLM sometimes fails and offers retry)
        for retry_sel in [
            "button:has-text('Retry')",
            "button:has-text('Try again')",
            "button:has-text('Regenerate')",
        ]:
            retry_btn = page.query_selector(retry_sel)
            if retry_btn:
                try:
                    if retry_btn.is_visible():
                        retries_used += 1
                        if retries_used > max_retries:
                            print(f"  ❌ Failed after {max_retries} retries")
                            return False
                        print(f"  ⚠️ Generation failed, clicking retry ({retries_used}/{max_retries})...")
                        retry_btn.click()
                        time.sleep(5)
                        break
                except Exception:
                    pass

        # Check for error/failure text (but not if we already hit retry)
        for err_sel in [
            "button:has-text('Something went wrong')",
            "[class*='error-message']",
        ]:
            err_el = page.query_selector(err_sel)
            if err_el:
                try:
                    if err_el.is_visible():
                        text = err_el.inner_text().strip()[:100]
                        print(f"  ⚠️ Error detected: {text}")
                except Exception:
                    pass

        if elapsed % 30 == 0 and elapsed > 0:
            print(f"  ⏳ Still generating... ({elapsed}s elapsed)")

        # Keep session alive with small mouse movement
        if elapsed % 60 == 0 and elapsed > 0:
            page.mouse.move(400 + (elapsed % 10), 300)

        time.sleep(GENERATION_POLL_INTERVAL)

    print(f"  ❌ Timeout after {timeout}s")
    return False


def download_audio(page, output_path):
    """Click play on the audio, then download it."""
    print("  ⬇️ Downloading audio...")

    # Click play to activate the audio player
    play_btns = page.query_selector_all("button[aria-label='Play']")
    visible_play = [b for b in play_btns if b.is_visible()]
    if not visible_play:
        print("  ❌ No Play button found")
        return False

    visible_play[-1].click()
    time.sleep(3)

    # Click "See more options for audio player"
    more_btn = page.wait_for_selector(
        "button[aria-label='See more options for audio player']", timeout=10000
    )
    more_btn.click()
    time.sleep(1)

    # Click "Download" menu item
    download_item = page.wait_for_selector(
        "[role='menuitem']:has-text('Download')", timeout=5000
    )

    # Set up download listener
    with page.expect_download(timeout=120000) as download_info:
        download_item.click()

    download = download_info.value
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    download.save_as(str(dest))

    size_mb = dest.stat().st_size / (1024 * 1024)
    print(f"  ✅ Downloaded: {dest} ({size_mb:.1f} MB)")
    return True


def delete_notebook(page, notebook_url):
    """Delete the notebook to clean up."""
    print("  🗑️ Cleaning up notebook...")
    page.goto("https://notebooklm.google.com/", wait_until="domcontentloaded")
    time.sleep(3)

    # Extract notebook ID from URL
    match = re.search(r"/notebook/([a-f0-9-]+)", notebook_url)
    if not match:
        print("  ⚠️ Could not extract notebook ID for cleanup")
        return

    notebook_id = match.group(1)

    # Find the notebook's "more" menu by its link
    link = page.query_selector(f"a[href*='{notebook_id}']")
    if not link:
        print("  ⚠️ Notebook not found in list")
        return

    # Find the sibling "more_vert" button
    card = link.evaluate_handle("el => el.closest('[class*=project]') || el.parentElement")
    if card:
        more_btn = card.as_element().query_selector("button[aria-label='Project actions menu']")
        if more_btn:
            more_btn.click()
            time.sleep(1)

            delete_item = page.query_selector("[role='menuitem']:has-text('Delete')")
            if delete_item:
                delete_item.click()
                time.sleep(1)

                # Confirm deletion
                confirm = page.query_selector("button:has-text('Delete')")
                if confirm and confirm.is_visible():
                    confirm.click()
                    time.sleep(2)
                    print("  ✅ Notebook deleted")
                    return

    print("  ⚠️ Could not delete notebook automatically")


def main():
    parser = argparse.ArgumentParser(description="Generate NotebookLM Audio Overview")
    parser.add_argument("--pdf", required=True, help="Path to PDF file")
    parser.add_argument("--output", required=True, help="Output path for audio file")
    parser.add_argument("--format", default="deep-dive",
                        choices=["deep-dive", "brief", "critique", "debate"],
                        help="Audio format (default: deep-dive)")
    parser.add_argument("--length", default="default",
                        choices=["short", "default", "long"],
                        help="Audio length (default: default)")
    parser.add_argument("--focus", default=None,
                        help="What hosts should focus on")
    parser.add_argument("--keep-notebook", action="store_true",
                        help="Don't delete the notebook after generation")
    parser.add_argument("--show-browser", action="store_true",
                        help="Show the browser window")
    parser.add_argument("--timeout", type=int, default=GENERATION_TIMEOUT_SECONDS,
                        help=f"Generation timeout in seconds (default: {GENERATION_TIMEOUT_SECONDS})")

    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"❌ PDF not found: {args.pdf}")
        return 1

    auth = AuthManager()
    if not auth.is_authenticated():
        print("❌ Not authenticated. Run: python scripts/run.py auth_manager.py setup")
        return 1

    headless = not args.show_browser
    playwright = None
    context = None
    notebook_url = None

    try:
        playwright = sync_playwright().start()
        context = BrowserFactory.launch_persistent_context(playwright, headless=headless)
        page = context.new_page()

        # Step 1: Create notebook
        notebook_url = create_notebook(page)

        # Step 2: Upload PDF
        upload_pdf(page, pdf_path)

        # Step 3: Generate Audio Overview
        if not generate_audio_overview(page, args.format, args.length, args.focus):
            print("❌ Failed to start generation")
            return 1

        # Step 4: Wait for completion
        if not wait_for_audio_ready(page, timeout=args.timeout):
            print("❌ Audio generation failed or timed out")
            return 1

        # Step 5: Download
        if not download_audio(page, args.output):
            print("❌ Download failed")
            return 1

        # Step 6: Cleanup
        if not args.keep_notebook and notebook_url:
            delete_notebook(page, notebook_url)

        print(f"\n✅ Podcast saved to: {args.output}")
        return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        if context:
            try:
                context.close()
            except:
                pass
        if playwright:
            try:
                playwright.stop()
            except:
                pass


if __name__ == "__main__":
    sys.exit(main())
