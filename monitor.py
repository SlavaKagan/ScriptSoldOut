# monitor.py
import os
import smtplib
import logging
import time
import json
from email.message import EmailMessage
from typing import Optional, List, Tuple

import requests
from bs4 import BeautifulSoup

# --- Configuration from env ---
# Multiple URLs: accept newline, comma-separated, or JSON array.
_TARGET_URLS_RAW = os.getenv("TARGET_URLS", "").strip()
SEARCH_TEXT = os.getenv("SEARCH_TEXT", "SOLD OUT").strip()
RECIPIENT = os.getenv("RECIPIENT_EMAIL", "slava15.92@gmail.com").strip()
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "20"))
REQUEST_DELAY_SEC = float(os.getenv("REQUEST_DELAY_SEC", "1.0"))  # polite delay between requests
CSS_SELECTOR = os.getenv("CSS_SELECTOR", "").strip()  # optional: narrow search area

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("monitor")

def parse_urls(raw: str) -> List[str]:
    if not raw:
        return []
    # JSON array support
    if raw.startswith("["):
        try:
            arr = json.loads(raw)
            return [u.strip() for u in arr if isinstance(u, str) and u.strip()]
        except Exception:
            logger.warning("Failed to parse TARGET_URLS as JSON; will try splitting text.")
    # newline or comma separated
    parts = []
    for sep in ["\n", ","]:
        if sep in raw:
            parts = [p.strip() for p in raw.split(sep)]
            parts = [p for p in parts if p]
            break
    return parts if parts else [raw]

def fetch_html(url: str, timeout: int = TIMEOUT) -> Optional[str]:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; MonitorBot/1.1; +https://example.com/monitor)"
        }
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.exception("Error fetching URL %s: %s", url, e)
        return None

def page_contains_text(html: str, text: str, css_selector: str = "") -> bool:
    soup = BeautifulSoup(html, "html.parser")
    if css_selector:
        selection = soup.select(css_selector)
        haystack = " ".join(el.get_text(separator=" ", strip=True) for el in selection)
    else:
        haystack = soup.get_text(separator=" ", strip=True)
    return text.lower() in haystack.lower()

def send_email(subject: str, body: str) -> bool:
    if not all([SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASS]):
        logger.error("SMTP credentials not fully configured.")
        return False
    try:
        msg = EmailMessage()
        msg["From"] = SMTP_USER
        msg["To"] = RECIPIENT
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.send_message(msg)
        logger.info("Email sent to %s", RECIPIENT)
        return True
    except Exception as e:
        logger.exception("Failed to send email: %s", e)
        return False

def check_urls(urls: List[str], search_text: str, selector: str) -> Tuple[List[str], List[str]]:
    hits, misses = [], []
    for url in urls:
        logger.info("Checking %s for text '%s' ...", url, search_text)
        html = fetch_html(url)
        if html is None:
            misses.append(url + " [fetch error]")
        else:
            if page_contains_text(html, search_text, selector):
                hits.append(url)
            else:
                misses.append(url)
        time.sleep(REQUEST_DELAY_SEC)
    return hits, misses

def main():
    urls = parse_urls(_TARGET_URLS_RAW)
    if not urls:
        logger.error("No TARGET_URLS configured. Set the TARGET_URLS env var.")
        return

    hits, misses = check_urls(urls, SEARCH_TEXT, CSS_SELECTOR)

    logger.info("Done. Hits: %d, Misses: %d", len(hits), len(misses))

    if hits:
        subject = f"[ALERT] Found '{SEARCH_TEXT}' on {len(hits)}/{len(urls)} URL(s)"
        not_found_lines = [f"- {u}" for u in misses] if misses else ["- (none)"]

        body_lines = [
            f"Search text: '{SEARCH_TEXT}'",
            f"CSS selector: '{CSS_SELECTOR or 'N/A'}'",
            "",
            "Found on:",
            *[f"- {u}" for u in hits],
            "",
            "Not found on:",
            *not_found_lines,
            "",
            "Checked by monitor.py"
        ]
        send_email(subject, "\n".join(body_lines))
    else:
        logger.info("No matches found. No email sent.")

if __name__ == "__main__":
    main()
