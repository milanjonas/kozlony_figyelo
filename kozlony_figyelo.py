#!/usr/bin/env python3
"""
Magyar Kozlony RSS feed figyelo -> Telegram ertesito

Mukodese:
1. Leszedi az RSS feedet.
2. Megnezi a legfrissebb elem egyedi azonositojat (guid).
3. Osszehasonlitja egy korabban elmentett ertekkel (last_guid.txt).
4. Ha uj -> Telegram uzenetet kuld, es elmenti az uj guid-ot.

Beallitando ertekek: TELEGRAM_TOKEN es TELEGRAM_CHAT_ID
(ezeket kornyezeti valtozokent adjuk at, ld. GitHub Actions utmutato)
"""

import os
import sys
import feedparser
import requests

RSS_URL = "https://www.magyarkozlony.hu/feed"
STATE_FILE = "last_guid.txt"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def read_last_guid():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None


def write_last_guid(guid):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(guid)


def send_telegram_message(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("HIBA: TELEGRAM_TOKEN vagy TELEGRAM_CHAT_ID nincs beallitva.")
        sys.exit(1)

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": False,
    }
    response = requests.post(url, data=payload, timeout=15)
    if response.status_code != 200:
        print(f"HIBA a Telegram kuldesnel: {response.status_code} - {response.text}")
    else:
        print("Ertesites elkuldve.")


def main():
    feed = feedparser.parse(RSS_URL)

    if not feed.entries:
        print("Nem talalhato elem a feedben (lehet, hogy a feed elerhetetlen).")
        return

    latest = feed.entries[0]
    latest_guid = latest.get("id") or latest.get("link")

    last_guid = read_last_guid()

    if latest_guid == last_guid:
        print("Nincs uj elem.")
        return

    title = latest.get("title", "Uj kozlemeny")
    link = latest.get("link", "")

    message = f"📰 Uj elem a Magyar Kozlonyben:\n\n{title}\n{link}"
    send_telegram_message(message)

    write_last_guid(latest_guid)


if __name__ == "__main__":
    main()
