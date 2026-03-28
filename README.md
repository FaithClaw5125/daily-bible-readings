# Daily USCCB Bible Readings — Email Script

Fetches the daily Mass readings from [bible.usccb.org](https://bible.usccb.org) each morning and sends them to your configured recipient(s) as a nicely formatted email (both plain text and HTML).

---

## Setup

### 1. Configure SMTP credentials

Open `daily_readings.py` and fill in the `CONFIG` section:

```python
SENDER_EMAIL  = "youremail@gmail.com"
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587
SMTP_USER     = "youremail@gmail.com"
SMTP_PASSWORD = "your-app-password"
```

#### Gmail (recommended)
1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Create an App Password for "Mail"
3. Use that 16-character password as `SMTP_PASSWORD`
4. Set `SMTP_HOST = "smtp.gmail.com"`, `SMTP_PORT = 587`

#### Outlook / Hotmail (sending FROM Hotmail)
1. Use `SMTP_HOST = "smtp-mail.outlook.com"`, `SMTP_PORT = 587`
2. Enable "Allow apps that use less secure sign-in" in Outlook security settings
   OR use an App Password if you have 2FA enabled

---

### 2. Test it manually

```bash
cd ~/path/to/daily_readings
python3 daily_readings.py
```

You should see a preview of the readings and "✅ Email sent to [your recipient]"

---

### 3. Schedule it daily (macOS)

Install the included launchd plist to run automatically every morning at 7:00 AM:

```bash
# Edit the plist to set the correct path to your Python and script
nano com.dailyreadings.plist

# Then install:
cp com.dailyreadings.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.dailyreadings.plist
```

To uninstall:
```bash
launchctl unload ~/Library/LaunchAgents/com.dailyreadings.plist
rm ~/Library/LaunchAgents/com.dailyreadings.plist
```

---

## How It Works

1. Builds the USCCB URL for today's date (e.g. `032726.cfm` for March 27, 2026)
2. Fetches and parses the HTML to extract:
   - Reading 1
   - Responsorial Psalm
   - Verse Before the Gospel
   - Gospel
   - (Plus any other sections like Second Reading on Sundays)
3. Formats both a plain text and HTML version of the email
4. Sends via SMTP

## Notes

- The USCCB URL format is `MMDDYY.cfm` — the script generates this automatically each day
- Sunday readings include a **Second Reading** — the parser handles this automatically
- If the page isn't up yet (rare), the script exits gracefully without sending
