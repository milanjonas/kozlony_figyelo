#!/usr/bin/env python3
"""
Facebook oldalak poszt-figyelo -> Telegram ertesito

Mukodese:
1. Vegigmegy a lent felsorolt oldalakon.
2. Minden oldalnal lekeri a legfrissebb posztot a Graph API-n keresztul.
3. Osszehasonlitja egy korabban elmentett allapottal (fb_last_posts.json).
4. Ha uj poszt van -> Telegram uzenetet kuld, es frissiti az allapotot.

Szukseges kornyezeti valtozok (GitHub Secrets-ben allitva):
- FB_ACCESS_TOKEN   -> a System User access tokene
- TELEGRAM_TOKEN    -> mar korabban beallitva a Kozlony figyelohoz
- TELEGRAM_CHAT_ID  -> mar korabban beallitva a Kozlony figyelohoz
"""

import os
import sys
import json
import requests

# --- Oldalak listaja: nev -> Page ID ---
PAGES = {
    "Belugyminiszterium": "1245149585348607",
    "Gazdasagi es Energetikai Miniszterium": "1304549466074937",
    "Oktatasi es Gyermekugyi Miniszterium": "1278249628702924",
    "Tudomanyos es Technologiai Miniszterium": "1249657131564658",
    "Szocialis es Csaladugyi Miniszterium": "1248519985010688",
    "Videk- es Telepulesfejlesztesi Miniszterium": "1293985917125887",
    "Elo Kornyezetert Felelos Miniszterium": "1241935639001747",
    "Kulugyminiszterium": "1224465490752382",
    "Magyarorszag Kormanya": "120370174702378",
}

GRAPH_API_VERSION = "v26.0"
STATE_FILE = "fb_last_posts.json"

def _clean(value):
    """Levagja a kornyezeti valtozok elejerol/vegerol az esetleges
    szokozoket vagy sortoreseket, amik masolaskor bekerulhettek."""
    return value.strip() if value else value


FB_ACCESS_TOKEN = _clean(os.environ.get("FB_ACCESS_TOKEN"))
   TELEGRAM_TOKEN = _clean(os.environ.get("TELEGRAM_TOKEN"))
   # Kulon Telegram cset/csoport a Facebook ertesiteseknek (nem a Kozlonyos csoport)
   TELEGRAM_CHAT_ID = _clean(os.environ.get("FB_TELEGRAM_CHAT_ID"))

# Debug info: a token hosszat kiirjuk (magat a tokent SOHA nem irjuk ki),
# hogy lassuk, tenyleg a vart hosszusagu erkezett-e meg.
if FB_ACCESS_TOKEN:
    print(f"[debug] FB_ACCESS_TOKEN hossza: {len(FB_ACCESS_TOKEN)} karakter")
else:
    print("[debug] FB_ACCESS_TOKEN ures vagy hianyzik!")


def read_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def write_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_page_tokens():
    """Lekeri az osszes olyan oldal SAJAT access tokenjet, amihez a
    rendszerfelhasznalonak hozzaferese van. Ez szukseges, mert a
    rendszerfelhasznalo sajat tokenje onmagaban nem mindig eleg egy
    adott oldal posztjainak lekerdezesehez."""
    tokens = {}
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/accounts"
    params = {
        "fields": "id,name,access_token",
        "limit": 100,
        "access_token": FB_ACCESS_TOKEN,
    }

    while url:
        response = requests.get(url, params=params, timeout=15)
        data = response.json()

        if "error" in data:
            print(f"HIBA az oldal-tokenek lekeresekor: {data['error'].get('message')}")
            break

        for entry in data.get("data", []):
            tokens[entry["id"]] = entry.get("access_token")

        # lapozas, ha 100-nal tobb oldal lenne
        next_url = data.get("paging", {}).get("next")
        url = next_url
        params = {}  # a next_url mar tartalmazza az osszes parametert

    return tokens


def get_latest_post(page_id, page_token):
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/posts"
    params = {
        "fields": "id,message,created_time,permalink_url,attachments{media_type}",
        "limit": 1,
        "access_token": page_token,
    }
    response = requests.get(url, params=params, timeout=15)
    data = response.json()

    if "error" in data:
        print(f"HIBA a(z) {page_id} oldalnal: {data['error'].get('message')}")
        return None

    posts = data.get("data", [])
    if not posts:
        return None

    return posts[0]


def guess_content_type(post):
    attachments = post.get("attachments", {}).get("data", [])
    if attachments:
        return attachments[0].get("media_type", "ismeretlen")
    return "szoveg"


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
    if not FB_ACCESS_TOKEN:
        print("HIBA: FB_ACCESS_TOKEN nincs beallitva.")
        sys.exit(1)

    page_tokens = get_page_tokens()
    print(f"[debug] {len(page_tokens)} oldal-token erkezett meg.")

    state = read_state()
    changed = False

    for page_name, page_id in PAGES.items():
        page_token = page_tokens.get(page_id)
        if not page_token:
            print(f"HIBA a(z) {page_name} ({page_id}) oldalnal: nincs sajat token, "
                  f"valoszinuleg nincs hozzarendelve a rendszerfelhasznalohoz.")
            continue

        latest = get_latest_post(page_id, page_token)
        if latest is None:
            continue

        latest_id = latest["id"]
        last_known_id = state.get(page_id)

        if latest_id == last_known_id:
            print(f"{page_name}: nincs uj poszt.")
            continue

        content_type = guess_content_type(latest)
        message_text = latest.get("message", "(nincs szoveges tartalom)")
        link = latest.get("permalink_url", "")
        created = latest.get("created_time", "")

        # Uj posztnal rovidebb kivonatot kuldunk, ha tul hosszu a szoveg
        excerpt = message_text[:200] + ("..." if len(message_text) > 200 else "")

        telegram_text = (
            f"📢 Uj poszt: {page_name}\n\n"
            f"Tipus: {content_type}\n"
            f"Idopont: {created}\n\n"
            f"{excerpt}\n\n"
            f"{link}"
        )
        send_telegram_message(telegram_text)

        state[page_id] = latest_id
        changed = True

    if changed:
        write_state(state)
    else:
        print("Egyik oldalon sem volt uj poszt.")


if __name__ == "__main__":
    main()
