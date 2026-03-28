#!/usr/bin/env python3
"""
Daily USCCB Bible Readings Email
Fetches today's readings from bible.usccb.org and emails them to the recipient.

Usage:
    python3 daily_readings.py

Configuration:
    Edit the CONFIG section below with your SMTP credentials.
"""

import urllib.request
import ssl
import re
import smtplib
import sys
import os
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import unescape

# ─── Load .env if present (never committed to git) ───────────────────────────
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

# ─── CONFIG ───────────────────────────────────────────────────────────────────

RECIPIENT     = os.environ.get("MAIL_RECIPIENT", "").split(",")
SENDER_EMAIL  = os.environ.get("SMTP_USER", "")
SENDER_NAME   = "Daily Bible Readings"
SMTP_HOST     = os.environ.get("SMTP_HOST", "smtp.mail.me.com")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER     = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

# ─────────────────────────────────────────────────────────────────────────────


def get_today_url():
    """Build the USCCB URL for today's readings."""
    now = datetime.now()
    date_str = now.strftime("%m%d%y")   # e.g. 032726
    return f"https://bible.usccb.org/bible/readings/{date_str}.cfm", now


def fetch_html(url):
    """Fetch raw HTML from the USCCB readings page."""
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def clean_html(raw):
    """Strip HTML tags and clean up whitespace."""
    # Replace <br> variants with newlines
    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    # Replace </p> with double newlines
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    # Strip all remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities
    text = unescape(text)
    # Collapse excessive whitespace/blank lines (max 2 consecutive newlines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def html_to_html_clean(raw):
    """Light HTML cleanup for the HTML email version."""
    # Remove script/style blocks
    cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML entities that are non-breaking spaces etc, keep structure
    cleaned = re.sub(r"&nbsp;", " ", cleaned)
    return cleaned


def extract_page_title(html):
    """Extract the liturgical day title (e.g. 'Friday of the Fifth Week of Lent')."""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        title = clean_html(m.group(1))
        # Strip " | USCCB" suffix if present
        title = re.sub(r"\s*\|\s*USCCB.*$", "", title).strip()
        return title
    return "Daily Mass Readings"


def extract_sections(html):
    """
    Extract all reading sections from the page.
    Returns a list of dicts: {title, reference, text}
    """
    sections = []

    # Find all h3.name blocks
    pattern = re.compile(
        r'<h3[^>]*class="name"[^>]*>(.*?)</h3>'    # section title
        r'.*?<div[^>]*class="address"[^>]*>(.*?)</div>'  # reference
        r'.*?<div[^>]*class="content-body"[^>]*>(.*?)</div>',  # content
        re.DOTALL | re.IGNORECASE
    )

    for m in pattern.finditer(html):
        title_raw = m.group(1)
        ref_raw   = m.group(2)
        body_raw  = m.group(3)

        title = clean_html(title_raw).strip()
        ref   = clean_html(ref_raw).strip()
        body  = clean_html(body_raw).strip()

        if title and body:
            sections.append({
                "title": title,
                "reference": ref,
                "text": body
            })

    return sections


def build_plain_text(day_title, sections, date, url):
    """Build the plain text version of the email."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"DAILY MASS READINGS")
    lines.append(f"{date.strftime('%A, %B %-d, %Y')}")
    lines.append(day_title)
    lines.append("=" * 60)
    lines.append("")

    for sec in sections:
        lines.append(f"── {sec['title'].upper()} ──")
        if sec["reference"]:
            lines.append(sec["reference"])
        lines.append("")
        lines.append(sec["text"])
        lines.append("")
        lines.append("")

    lines.append("-" * 60)
    lines.append(f"Source: {url}")
    lines.append("United States Conference of Catholic Bishops")
    return "\n".join(lines)


def build_html_email(day_title, sections, date, url):
    """Build the HTML version of the email."""
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: Georgia, serif; max-width: 680px; margin: 0 auto; padding: 20px; color: #222; background: #fff; }}
  h1 {{ font-size: 22px; color: #6b0000; border-bottom: 2px solid #6b0000; padding-bottom: 8px; }}
  h2 {{ font-size: 14px; color: #888; font-weight: normal; margin-top: -10px; }}
  h3 {{ font-size: 16px; color: #6b0000; margin-top: 30px; margin-bottom: 2px; text-transform: uppercase; letter-spacing: 0.05em; }}
  .reference {{ font-size: 13px; color: #555; font-style: italic; margin-bottom: 12px; }}
  p {{ line-height: 1.7; margin: 6px 0; }}
  .footer {{ font-size: 11px; color: #aaa; border-top: 1px solid #eee; margin-top: 40px; padding-top: 10px; }}
  .r-verse {{ font-weight: bold; }}
</style>
</head>
<body>
<h1>Daily Mass Readings</h1>
<h2>{date.strftime('%A, %B %-d, %Y')} &mdash; {day_title}</h2>
"""

    for sec in sections:
        ref_html = f'<div class="reference">{sec["reference"]}</div>' if sec["reference"] else ""
        # Convert newlines to <p> tags in body
        body_paras = sec["text"].split("\n\n")
        body_html = "".join(
            f"<p>{para.replace(chr(10), '<br>')}</p>"
            for para in body_paras if para.strip()
        )
        html += f"""
<h3>{sec['title']}</h3>
{ref_html}
{body_html}
"""

    html += f"""
<div class="footer">
  Source: <a href="{url}">{url}</a><br>
  United States Conference of Catholic Bishops
</div>
</body>
</html>"""
    return html


def send_email(subject, plain_text, html_body):
    """Send the email via SMTP."""
    if not SMTP_HOST or not SENDER_EMAIL or not SMTP_PASSWORD:
        print("ERROR: SMTP credentials not configured. Edit the CONFIG section in daily_readings.py")
        sys.exit(1)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    msg["To"]      = ", ".join(RECIPIENT) if isinstance(RECIPIENT, list) else RECIPIENT

    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_body,  "html",  "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT, msg.as_string())

    print(f"✅ Email sent to {RECIPIENT}")


def main():
    url, date = get_today_url()
    print(f"Fetching readings for {date.strftime('%B %-d, %Y')}...")
    print(f"URL: {url}")

    try:
        html = fetch_html(url)
    except urllib.error.HTTPError as e:
        print(f"ERROR: Could not fetch page ({e.code}). No readings posted for today yet?")
        sys.exit(1)

    day_title = extract_page_title(html)
    sections  = extract_sections(html)

    if not sections:
        print("WARNING: No reading sections found. Page structure may have changed.")
        sys.exit(1)

    print(f"Found {len(sections)} section(s): {[s['title'] for s in sections]}")

    subject    = f"Daily Mass Readings — {date.strftime('%B %-d, %Y')} | {day_title}"
    plain_text = build_plain_text(day_title, sections, date, url)
    html_body  = build_html_email(day_title, sections, date, url)

    # Print preview
    print("\n" + "="*60)
    print(plain_text[:1200])
    print("="*60 + "\n")

    send_email(subject, plain_text, html_body)


if __name__ == "__main__":
    main()
