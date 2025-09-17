import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
import csv
import re

# ===== 설정 =====
TAG_INDY = 492  # Indie
# 로케일 고정: 영어/미국
LOCALE_QS = "l=english&cc=US"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.8",
}

SEARCH_URL_TMPL = "https://store.steampowered.com/search/?category1=998&tags={tag}&page={page}&" + LOCALE_QS
APP_URL_TMPL    = "https://store.steampowered.com/app/{appid}/?" + LOCALE_QS
APPREVIEWS_TMPL = "https://store.steampowered.com/appreviews/{appid}?json=1&filter=all&language=all&review_type=all&purchase_type=all"
STEAMSPY_URL    = "https://steamspy.com/api.php?request=appdetails&appid={appid}"

# 세션(헤더/쿠키)
session = requests.Session()
session.headers.update(HEADERS)
session.cookies.set("Steam_Language", "english", domain=".steampowered.com")
session.cookies.set("wants_mature_content", "1", domain=".steampowered.com")
session.cookies.set("birthtime", "568022401", domain=".steampowered.com")  # 성인 통과용

# ===== 유틸 =====
def try_parse_date(text):
    for fmt in ["%Y년 %m월 %d일", "%d %b, %Y", "%b %d, %Y"]:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None

def extract_year_fallback(text):
    m = re.search(r'\b(19|20)\d{2}\b', text or "")
    return int(m.group(0)) if m else ""

def fetch_total_reviews_from_steamspy(appid):
    try:
        r = session.get(STEAMSPY_URL.format(appid=appid), timeout=10)
        data = r.json()
        return data.get("positive", 0) + data.get("negative", 0)
    except:
        return 0

def _largest_int_in(text: str):
    nums = re.findall(r'[\d,]+', text or "")
    if not nums:
        return None
    return max(int(n.replace(",", "")) for n in nums)

# === 모든 언어(All languages) 총 리뷰 수 ===
def fetch_total_reviews_from_store_alllangs(appid):
    # 1) 공식 JSON(API) 우선
    try:
        r = session.get(APPREVIEWS_TMPL.format(appid=appid), timeout=10)
        j = r.json()
        total = j.get("query_summary", {}).get("total_reviews", 0)
        if isinstance(total, int) and total > 0:
            return total
    except Exception as e:
        print(f"[appreviews API 실패] appid={appid}: {e}")

    # 2) 폴백: 상세 페이지 두 번째 요약행(= All Reviews)에서 추출
    try:
        res = session.get(APP_URL_TMPL.format(appid=appid), timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        rows = soup.select("a.user_reviews_summary_row")
        if not rows:
            return 0
        target = rows[1] if len(rows) >= 2 else rows[0]

        # (a) schema.org 메타
        meta = target.select_one('meta[itemprop="ratingCount"], meta[itemprop="reviewCount"]')
        if meta and meta.get("content"):
            return int(meta["content"].replace(",", ""))

        # (b) 툴팁/텍스트의 숫자들 중 가장 큰 값
        tooltip = target.get("data-tooltip-html", "") or ""
        val = _largest_int_in(tooltip)
        if val is not None:
            return val
        txt = target.get_text(" ", strip=True)
        val = _largest_int_in(txt)
        if val is not None:
            return val
    except Exception as e:
        print(f"[HTML 리뷰 파싱 오류] appid={appid}: {e}")

    return 0

def clean_price(text):
    if not text:
        return "Unknown"
    return text.strip().replace("\n", "").replace("\r", "")

# 통화/숫자 파싱 (₩/$/€/£ 지원) + 무료 판정
def parse_price(price_text):
    if not price_text:
        return None, None
    low = price_text.lower()
    if "free to play" in low or "free" in low or "무료" in low:
        return 0, None  # 무료
    m = re.search(r'([$\£€₩])\s*([0-9][0-9,]*(?:\.[0-9]+)?)', price_text)
    if not m:
        return None, None
    symbol = m.group(1)
    num = float(m.group(2).replace(",", "")) if "." in m.group(2) else int(m.group(2).replace(",", ""))
    return num, symbol

# 통화 무관 할인율 계산
def extract_discount_percent(item):
    try:
        orig = item.select_one(".discount_original_price")
        disc = item.select_one(".discount_final_price")
        if orig and disc:
            def _num(s):
                m = re.search(r'([0-9][0-9,]*(?:\.[0-9]+)?)', s or "")
                return float(m.group(1).replace(",", "")) if (m and "." in m.group(1)) else (int(m.group(1).replace(",", "")) if m else None)
            o = _num(orig.text)
            d = _num(disc.text)
            if o and d and d < o:
                return f"{int((1 - d / o) * 100)}%"
    except:
        pass
    return "0%"

def estimate_revenue(total_reviews, price_value):
    if not price_value or total_reviews <= 0:
        return 0
    return total_reviews * 50 * price_value

def fmt_money(amount, symbol):
    if symbol == "₩":
        return f"₩{int(round(amount)):,}"
    if symbol in ("$", "€", "£"):
        return f"{symbol}{amount:,.2f}"
    return str(amount)

# ===== 수집: Indie 태그 단일 =====
def collect_game_data():
    results = []
    page = 1
    seen_appids = set()

    print("\nIndie 태그 전체 수집 중...")
    while True:
        url = SEARCH_URL_TMPL.format(tag=TAG_INDY, page=page)
        print(f"[페이지 {page}] 요청 중: {url}")
        try:
            res = session.get(url, timeout=10)
        except Exception as e:
            print(f"요청 실패: {e}")
            break

        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.select(".search_result_row")
        if not items:
            print("마지막 페이지 도달.")
            break

        for item in items:
            try:
                # AppID 추출 (우선 data-ds-appid, 폴백 href)
                appid = item.get("data-ds-appid")
                if not appid:
                    href = item.get("href", "")
                    m = re.search(r"/app/(\d+)", href)
                    if not m:
                        continue
                    appid = m.group(1)

                if appid in seen_appids:
                    continue
                seen_appids.add(appid)

                title = item.select_one(".title").text.strip() if item.select_one(".title") else ""

                release_text = item.select_one(".search_released").get_text(strip=True) if item.select_one(".search_released") else ""
                dt = try_parse_date(release_text)
                year = dt.year if dt else extract_year_fallback(release_text)

                price_tag = item.select_one(".discount_final_price") or item.select_one(".search_price")
                price_str = clean_price(price_tag.text if price_tag else "")
                price_value, currency = parse_price(price_str)

                # 무료 게임 제외
                if price_value == 0:
                    print(f"{title} - Free (excluded)")
                    continue

                discount_percent = extract_discount_percent(item)

                total_ss = fetch_total_reviews_from_steamspy(appid)
                total_all = fetch_total_reviews_from_store_alllangs(appid)  # 모든 언어 총합

                revenue_ss = estimate_revenue(total_ss, price_value) if currency else 0
                revenue_all = estimate_revenue(total_all, price_value) if currency else 0

                rev_ss_str = fmt_money(revenue_ss, currency) if currency else "0"
                rev_all_str = fmt_money(revenue_all, currency) if currency else "0"

                print(f"{title} - 리뷰(SS) {total_ss} / 리뷰(ALL) {total_all} - 수익(SS) {rev_ss_str}, 수익(ALL) {rev_all_str}")

                results.append([
                    appid, title, year, "Indie",        # 장르는 고정
                    price_str, discount_percent,
                    total_ss, rev_ss_str,
                    total_all, rev_all_str
                ])
                time.sleep(0.5)
            except Exception as e:
                print(f"게임 처리 오류: {e}")
                continue

        page += 1
        time.sleep(1)

    return results

# ===== 실행 & 저장 =====
if __name__ == "__main__":
    data = collect_game_data()
    header = [
        "AppID", "Name", "ReleaseYear", "Genre",
        "Price", "DiscountPercent",
        "TotalReviews_SteamSpy", "EstimatedRevenue_SteamSpy",
        "TotalReviews_AllLanguages", "EstimatedRevenue_AllLanguages"
    ]
    with open("IndieGameDetailList_AllIndie.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(data)
    print("IndieGameDetailList_AllIndie.csv 저장 완료.")
