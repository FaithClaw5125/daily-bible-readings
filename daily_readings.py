#!/usr/bin/env python3
"""
Daily USCCB Bible Readings Email - v2
Fetches today's readings from bible.usccb.org, generates an AI theme intro
and per-reading summaries, then emails them to recipients.

Usage:
    python3 daily_readings_v2.py [--test]

    --test  Send only to sfaith5125@hotmail.com for review.
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

ALL_RECIPIENTS = os.environ.get("MAIL_RECIPIENT", "").split(",")
TEST_RECIPIENT = ["sfaith5125@hotmail.com"]

SENDER_EMAIL  = os.environ.get("SMTP_USER", "")
SENDER_NAME   = "Daily Bible Readings"
SMTP_HOST     = os.environ.get("SMTP_HOST", "smtp.mail.me.com")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER     = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ─────────────────────────────────────────────────────────────────────────────


def get_today_url():
    """Build the USCCB URL for today's readings."""
    now = datetime.now()
    date_str = now.strftime("%m%d%y")
    return f"https://bible.usccb.org/bible/readings/{date_str}.cfm", now


def fetch_html(url):
    """Fetch raw HTML from the USCCB readings page."""
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def clean_html(raw):
    """Strip HTML tags and clean up whitespace."""
    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def extract_page_title(html):
    """Extract the liturgical day title."""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        title = clean_html(m.group(1))
        title = re.sub(r"\s*\|\s*USCCB.*$", "", title).strip()
        return title
    return "Daily Mass Readings"


def extract_sections(html):
    """Extract all reading sections. Returns list of {title, reference, text}."""
    sections = []
    pattern = re.compile(
        r'<h3[^>]*class="name"[^>]*>(.*?)</h3>'
        r'.*?<div[^>]*class="address"[^>]*>(.*?)</div>'
        r'.*?<div[^>]*class="content-body"[^>]*>(.*?)</div>',
        re.DOTALL | re.IGNORECASE
    )
    for m in pattern.finditer(html):
        title = clean_html(m.group(1)).strip()
        ref   = clean_html(m.group(2)).strip()
        body  = clean_html(m.group(3)).strip()
        if title and body:
            sections.append({"title": title, "reference": ref, "text": body})
    return sections


def is_reading(title):
    """Return True if this section is an actual reading (not a psalm, verse, or prayer)."""
    skip_keywords = ["psalm", "responsorial", "verse before", "alleluia", "gospel acclamation", "sequence"]
    t = title.lower()
    return not any(kw in t for kw in skip_keywords)


def generate_ai_content(day_title, sections):
    """
    Use Claude to generate:
    - A 1-2 sentence overall theme for the day's readings
    - A 2-3 sentence summary per reading (what the Church wants us to know)
      Only for actual readings — psalms, verses, and prayers are skipped.
    Returns: (theme_str, {section_index: summary_str})
    """
    try:
        import anthropic

        # Only summarize actual readings
        reading_sections = [(i, sec) for i, sec in enumerate(sections) if is_reading(sec['title'])]

        # Build the prompt using only readings
        readings_text = ""
        for idx, (i, sec) in enumerate(reading_sections, 1):
            readings_text += f"\n\nREADING_{idx} - {sec['title']} ({sec['reference']}):\n{sec['text'][:1000]}"

        prompt = f"""You are a Catholic theologian helping prepare a daily Mass readings email.

Liturgical day: {day_title}

Today's readings:
{readings_text}

Please provide:

1. THEME: A 1-2 sentence overarching theme that connects all of today's readings. Start with "Today's readings..."

2. SUMMARIES: For each reading, provide a concise 2-3 sentence summary of what the Church wants us to know and take away. Be warm, pastoral, and accessible — not academic.

Format your response EXACTLY like this:
THEME: [your 1-2 sentence theme here]

SUMMARY_1: [summary for READING_1]

SUMMARY_2: [summary for READING_2]

(continue numbering for each reading in order)"""

        api_key = ANTHROPIC_API_KEY or os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            # Try to read from openclaw config location
            key_path = os.path.expanduser("~/.openclaw/secrets/anthropic_api_key")
            if os.path.exists(key_path):
                with open(key_path) as f:
                    api_key = f.read().strip()

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        response = message.content[0].text

        # Parse theme
        theme_match = re.search(r"THEME:\s*(.+?)(?=\n\nSUMMARY_1:|\nSUMMARY_1:)", response, re.DOTALL)
        if not theme_match:
            theme_match = re.search(r"THEME:\s*(.+?)(?=\n\n)", response, re.DOTALL)
        theme = theme_match.group(1).strip() if theme_match else ""

        # Parse summaries — split on SUMMARY_N: labels (model may add "(title)" after number)
        summary_parts = re.split(r"\n+SUMMARY_\d+[^:]*:\s*", response)
        parsed = [p.strip() for p in summary_parts[1:]]

        # Map summaries back to their original section indexes
        summaries = {}
        for idx, (section_index, _) in enumerate(reading_sections):
            summaries[section_index] = parsed[idx] if idx < len(parsed) else ""

        return theme, summaries

    except Exception as e:
        print(f"⚠️  AI content generation failed: {e}")
        return "", {}


def build_plain_text(day_title, sections, date, url, theme, summaries):
    """Build the plain text version of the email."""
    lines = []
    lines.append("=" * 60)
    lines.append("DAILY MASS READINGS")
    lines.append(date.strftime('%A, %B %-d, %Y'))
    lines.append(day_title)
    lines.append("=" * 60)
    lines.append("")

    if theme:
        lines.append("TODAY'S THEME")
        lines.append("-" * 40)
        lines.append(theme)
        lines.append("")
        lines.append("")

    for i, sec in enumerate(sections):
        lines.append(f"── {sec['title'].upper()} ──")
        if sec["reference"]:
            lines.append(sec["reference"])
        lines.append("")
        lines.append(sec["text"])
        lines.append("")
        if summaries and summaries.get(i):
            lines.append("What the Church wants us to know:")
            lines.append(summaries[i])
            lines.append("")
        lines.append("")

    lines.append("-" * 60)
    lines.append(f"Source: {url}")
    lines.append("United States Conference of Catholic Bishops")
    return "\n".join(lines)


def build_html_email(day_title, sections, date, url, theme, summaries):
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
  .theme-box {{ background: #fdf8f0; border-left: 4px solid #6b0000; padding: 14px 18px; margin: 20px 0 30px 0; border-radius: 0 6px 6px 0; }}
  .theme-box p {{ margin: 0; font-style: italic; font-size: 15px; color: #444; line-height: 1.6; }}
  .theme-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; color: #6b0000; font-weight: bold; margin-bottom: 6px; font-family: Arial, sans-serif; }}
  .church-insight {{ background: #f5f5f5; border-radius: 6px; padding: 14px 18px; margin-top: 16px; }}
  .church-insight-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #888; font-weight: bold; margin-bottom: 6px; font-family: Arial, sans-serif; }}
  .church-insight p {{ margin: 0; font-size: 14px; color: #444; line-height: 1.65; }}
  .footer {{ font-size: 11px; color: #aaa; border-top: 1px solid #eee; margin-top: 40px; padding-top: 10px; }}
</style>
</head>
<body>
<h1>Daily Mass Readings</h1>
<h2>{date.strftime('%A, %B %-d, %Y')} &mdash; {day_title}</h2>
"""

    if theme:
        html += f"""
<div class="theme-box">
  <div class="theme-label">Today's Theme</div>
  <p>{theme}</p>
</div>
"""

    for i, sec in enumerate(sections):
        ref_html = f'<div class="reference">{sec["reference"]}</div>' if sec["reference"] else ""
        body_paras = sec["text"].split("\n\n")
        body_html = "".join(
            f"<p>{para.replace(chr(10), '<br>')}</p>"
            for para in body_paras if para.strip()
        )

        summary_html = ""
        if summaries and summaries.get(i):
            summary_paras = summaries[i].split("\n\n")
            summary_body = "".join(
                f"<p>{para.replace(chr(10), '<br>')}</p>"
                for para in summary_paras if para.strip()
            )
            summary_html = f"""
<div class="church-insight">
  <div class="church-insight-label">What the Church Wants Us to Know</div>
  {summary_body}
</div>"""

        html += f"""
<h3>{sec['title']}</h3>
{ref_html}
{body_html}
{summary_html}
"""

    html += f"""
<div class="footer">
  Source: <a href="{url}">{url}</a><br>
  United States Conference of Catholic Bishops
</div>
</body>
</html>"""
    return html


def send_email(subject, plain_text, html_body, recipients):
    """Send the email via SMTP, one message per recipient to avoid bulk-send rejections."""
    if not SMTP_HOST or not SENDER_EMAIL or not SMTP_PASSWORD:
        print("ERROR: SMTP credentials not configured.")
        sys.exit(1)

    failed = []
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)

        for recipient in recipients:
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"]    = f"{SENDER_NAME} <{SENDER_EMAIL}>"
                msg["To"]      = recipient

                msg.attach(MIMEText(plain_text, "plain", "utf-8"))
                msg.attach(MIMEText(html_body,  "html",  "utf-8"))

                server.sendmail(SENDER_EMAIL, [recipient], msg.as_string())
                print(f"✅ Sent to {recipient}")
            except Exception as e:
                print(f"❌ Failed to send to {recipient}: {e}")
                failed.append(recipient)

    if failed:
        print(f"⚠️  Failed recipients: {failed}")
    else:
        print(f"✅ Email sent to all {len(recipients)} recipients")


def main():
    test_mode = "--test" in sys.argv
    recipients = TEST_RECIPIENT if test_mode else ALL_RECIPIENTS

    if test_mode:
        print("🧪 TEST MODE — sending only to sfaith5125@hotmail.com")

    url, date = get_today_url()
    print(f"Fetching readings for {date.strftime('%B %-d, %Y')}...")

    try:
        html = fetch_html(url)
    except urllib.error.HTTPError as e:
        print(f"ERROR: Could not fetch page ({e.code}).")
        sys.exit(1)

    day_title = extract_page_title(html)
    sections  = extract_sections(html)

    if not sections:
        print("WARNING: No reading sections found.")
        sys.exit(1)

    print(f"Found {len(sections)} section(s): {[s['title'] for s in sections]}")
    print("Generating AI theme and summaries...")

    theme, summaries = generate_ai_content(day_title, sections)

    if theme:
        print(f"✅ Theme: {theme[:80]}...")
    else:
        print("⚠️  No theme generated — sending without AI content")

    subject    = f"Daily Mass Readings — {date.strftime('%B %-d, %Y')} | {day_title}"
    plain_text = build_plain_text(day_title, sections, date, url, theme, summaries)
    html_body  = build_html_email(day_title, sections, date, url, theme, summaries)

    send_email(subject, plain_text, html_body, recipients)


if __name__ == "__main__":
    main()
