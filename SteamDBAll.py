import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
import csv

# 태그 ID
TAG_INDY = 492
GENRE_TAGS = {
    'Action': 19,
    'Adventure': 21,
    'RPG': 122,
    'Strategy': 9,
    'Simulation': 599,
    'Casual': 597,
    'Racing': 699,
    'Sports': 701,
    'Puzzle': 1664,
    'Platformer': 1625,
    'Deckbuilding': 17389
}

USER_AGENT = {"User-Agent": "Mozilla/5.0"}
SEARCH_URL = "https://store.steampowered.com/search/?tags={tag1},{tag2}&category1=998&page={page}"
STEAMSPY_URL = "https://steamspy.com/api.php?request=appdetails&appid={appid}"

def try_parse_date(text):
    formats = ["%Y년 %m월 %d일", "%d %b, %Y", "%b %d, %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None

def fetch_reviews_from_steamspy(appid):
    try:
        url = STEAMSPY_URL.format(appid=appid)
        response = requests.get(url, timeout=10)
        data = response.json()
        return data.get('positive', 0), data.get('negative', 0)
    except:
        return 0, 0

def clean_price(text):
    if not text:
        return "Unknown"
    text = text.strip().replace('\n', '').replace('\r', '')
    if "무료" in text or "Free" in text:
        return "Free"
    if "₩" in text:
        parts = text.split('₩')
        return "₩" + parts[-1].strip()
    return text.strip()

def collect_game_data():
    results = []
    year_range = range(2010, 2026)

    for genre_name, genre_id in GENRE_TAGS.items():
        print(f"\n▶ {genre_name} 장르 수집 중...")
        for page in range(1, 21):  # 최대 20페이지
            url = SEARCH_URL.format(tag1=TAG_INDY, tag2=genre_id, page=page)
            print(f"요청 중: {url}")
            try:
                res = requests.get(url, headers=USER_AGENT, timeout=10)
            except Exception as e:
                print(f"요청 실패: {e}")
                break

            soup = BeautifulSoup(res.text, 'html.parser')
            items = soup.select('.search_result_row')
            if not items:
                break

            for item in items:
                try:
                    link = item['href']
                    appid = link.split("/app/")[1].split("/")[0]
                    title = item.select_one('.title').text.strip()
                    release_text = item.select_one('.search_released').get_text(strip=True)
                    release_date = try_parse_date(release_text)
                    if not release_date or release_date.year not in year_range:
                        continue
                    year = release_date.year
                    price_raw = item.select_one('.search_price')
                    price = clean_price(price_raw.text if price_raw else "")

                    pos, neg = fetch_reviews_from_steamspy(appid)
                    results.append([appid, title, year, genre_name, price, pos, neg])
                    time.sleep(0.5)
                except Exception:
                    continue
            time.sleep(1)

    return results

# 실행 및 저장
if __name__ == "__main__":
    data = collect_game_data()
    header = ["AppID", "Name", "ReleaseYear", "Genre", "Price", "PositiveReviews", "NegativeReviews"]
    with open("IndieGameDetailList.csv", "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(data)
    print("\n✅ IndieGameDetailList.csv 저장 완료!")
