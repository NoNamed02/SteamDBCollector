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
URL_TEMPLATE = "https://store.steampowered.com/search/?tags={tag1},{tag2}&category1=998&page={page}"

# 날짜 파싱 함수
def try_parse_date(text):
    formats = ["%Y년 %m월 %d일", "%d %b, %Y", "%b %d, %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None

# 연도별 카운트 함수
def count_games_by_year(indie_tag, genre_tag, year_range):
    year_counts = {year: 0 for year in year_range}
    max_pages = 30

    for page in range(1, max_pages + 1):
        url = URL_TEMPLATE.format(tag1=indie_tag, tag2=genre_tag, page=page)
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
            release = item.select_one('.search_released')
            if not release:
                continue
            release_text = release.get_text(strip=True)
            if "출시" in release_text or "Coming" in release_text:
                continue

            release_date = try_parse_date(release_text)
            if release_date and release_date.year in year_counts:
                year_counts[release_date.year] += 1

        time.sleep(1)

    return year_counts

# 전체 실행
def run_all():
    year_range = list(range(2010, 2026))
    result_rows = []

    header = ["Genre"] + year_range
    result_rows.append(header)

    for genre_name, genre_id in GENRE_TAGS.items():
        print(f"\n▶ {genre_name} 장르 처리 중...")
        counts = count_games_by_year(TAG_INDY, genre_id, year_range)
        row = [genre_name] + [counts[y] for y in year_range]
        result_rows.append(row)

    with open("IndieGenreYearlyCount.csv", "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(result_rows)

    print("\nIndieGenreYearlyCount.csv 저장 완료!")

# 실행
run_all()
