import os
import asyncio
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")

KEYWORDS = [
    "software engineer intern",
    "software engineering graduate",
    "graduate software engineer",
    "graduate data engineer",
]

PROVINCE_MAP = {
    "western cape": "Western Cape", "cape town": "Western Cape",
    "stellenbosch": "Western Cape", "paarl": "Western Cape", "george": "Western Cape",
    "gauteng": "Gauteng", "johannesburg": "Gauteng", "joburg": "Gauteng",
    "sandton": "Gauteng", "midrand": "Gauteng", "centurion": "Gauteng",
    "pretoria": "Gauteng", "tshwane": "Gauteng", "randburg": "Gauteng",
    "roodepoort": "Gauteng",
    "kwazulu": "KwaZulu-Natal", "kwazulu-natal": "KwaZulu-Natal",
    "durban": "KwaZulu-Natal", "pietermaritzburg": "KwaZulu-Natal",
    "eastern cape": "Eastern Cape", "port elizabeth": "Eastern Cape",
    "gqeberha": "Eastern Cape", "nelson mandela": "Eastern Cape",
    "east london": "Eastern Cape",
    "free state": "Free State", "bloemfontein": "Free State",
    "limpopo": "Limpopo", "polokwane": "Limpopo",
    "mpumalanga": "Mpumalanga", "nelspruit": "Mpumalanga", "mbombela": "Mpumalanga",
    "north west": "North West", "rustenburg": "North West",
    "northern cape": "Northern Cape", "kimberley": "Northern Cape",
    "remote": "Remote",
}

# --- In-memory RemoteOK cache ---
_remoteok_cache: list[dict] = []
_remoteok_cached_at: datetime | None = None
_REMOTEOK_TTL = timedelta(minutes=10)


def _detect_province(location: str) -> str:
    loc = location.lower()
    for keyword, province in PROVINCE_MAP.items():
        if keyword in loc:
            return province
    return "Other"


def _detect_type(title: str) -> str:
    t = title.lower()
    if any(w in t for w in ["intern", "internship", "placement", "co-op", "coop"]):
        return "Internship"
    return "Graduate"


def _cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(weeks=2)


def _within_2_weeks_iso(iso_str: str) -> bool:
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00")) >= _cutoff()
    except Exception:
        return True


def _within_2_weeks_epoch(epoch: int) -> bool:
    try:
        return datetime.fromtimestamp(epoch, tz=timezone.utc) >= _cutoff()
    except Exception:
        return True


def _within_2_weeks_date(date_str: str) -> bool:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) >= _cutoff()
    except Exception:
        return True


async def fetch_adzuna(keyword: str, page: int = 1) -> list[dict]:
    if not ADZUNA_APP_ID or ADZUNA_APP_ID == "your_app_id_here":
        return []
    url = (
        f"https://api.adzuna.com/v1/api/jobs/za/search/{page}"
        f"?app_id={ADZUNA_APP_ID}&app_key={ADZUNA_APP_KEY}"
        f"&results_per_page=10&what={keyword.replace(' ', '%20')}"
        f"&where=south+africa&content-type=application/json"
    )
    async with httpx.AsyncClient(timeout=8) as client:
        try:
            r = await client.get(url)
            r.raise_for_status()
            # Explicitly ensure the response content is treated as UTF-8
            r.encoding = 'utf-8'
            results = []
            for j in r.json().get("results", []):
                created = j.get("created", "")
                if not _within_2_weeks_iso(created):
                    continue
                loc = j.get("location", {}).get("display_name", "")
                results.append({
                    "source": "Adzuna", "title": j.get("title", ""),
                    "company": j.get("company", {}).get("display_name", "Unknown"),
                    "location": loc, "description": j.get("description", "")[:400],
                    "url": j.get("redirect_url", ""), "type": _detect_type(j.get("title", "")),
                    "posted_at": created[:10], "province": _detect_province(loc),
                })
            return results
        except Exception:
            return []


async def fetch_linkedin(keyword: str, page: int = 1) -> list[dict]:
    start = (page - 1) * 10
    url = (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        f"?keywords={keyword.replace(' ', '%20')}&location=South%20Africa"
        f"&start={start}&f_TPR=r1209600"
    )
    async with httpx.AsyncClient(timeout=8, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}) as client:
        try:
            r = await client.get(url, follow_redirects=True)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            results = []
            for card in soup.find_all("li"):
                title_el    = card.find("h3", class_="base-search-card__title")
                company_el  = card.find("h4", class_="base-search-card__subtitle")
                location_el = card.find("span", class_="job-search-card__location")
                link_el     = card.find("a", class_="base-card__full-link")
                time_el     = card.find("time")
                if not title_el or not link_el:
                    continue
                posted_at = ""
                if time_el and time_el.get("datetime"):
                    posted_at = time_el["datetime"]
                    if not _within_2_weeks_date(posted_at):
                        continue
                loc = location_el.get_text(strip=True) if location_el else "South Africa"
                results.append({
                    "source": "LinkedIn", "title": title_el.get_text(strip=True),
                    "company": company_el.get_text(strip=True) if company_el else "Unknown",
                    "location": loc, "description": "",
                    "url": link_el["href"].split("?")[0],
                    "type": _detect_type(title_el.get_text(strip=True)),
                    "posted_at": posted_at, "province": _detect_province(loc),
                })
            return results
        except Exception:
            return []


async def _get_remoteok_raw() -> list[dict]:
    """Fetch RemoteOK once and cache for 10 minutes."""
    global _remoteok_cache, _remoteok_cached_at
    now = datetime.now(timezone.utc)
    if _remoteok_cached_at and (now - _remoteok_cached_at) < _REMOTEOK_TTL:
        return _remoteok_cache
    async with httpx.AsyncClient(timeout=8, headers={"User-Agent": "AppTracker/1.0"}) as client:
        try:
            r = await client.get("https://remoteok.com/api")
            r.raise_for_status()
            # Explicitly ensure the response content is treated as UTF-8
            r.encoding = 'utf-8'
            _remoteok_cache = [j for j in r.json() if isinstance(j, dict) and "position" in j]
            _remoteok_cached_at = now
        except Exception:
            pass
    return _remoteok_cache


async def fetch_remoteok(keyword: str, page: int = 1) -> list[dict]:
    page_size = 10
    offset = (page - 1) * page_size
    all_jobs = await _get_remoteok_raw()
    kw = keyword.lower()
    results, matched = [], 0
    for j in all_jobs:
        if not _within_2_weeks_epoch(j.get("epoch", 0)):
            continue
        title = j.get("position", "")
        tags = " ".join(j.get("tags", [])).lower()
        if not any(w in title.lower() or w in tags for w in kw.split()):
            continue
        matched += 1
        if matched <= offset:
            continue
        results.append({
            "source": "RemoteOK", "title": title,
            "company": j.get("company", "Unknown"), "location": "Remote",
            "description": j.get("description", "")[:400],
            "url": j.get("url", ""), "type": _detect_type(title),
            "posted_at": j.get("date", "")[:10], "province": "Remote",
        })
        if len(results) >= page_size:
            break
    return results


async def search_jobs(keyword: str, page: int = 1) -> list[dict]:
    adzuna, linkedin, remoteok = await asyncio.gather(
        fetch_adzuna(keyword, page),
        fetch_linkedin(keyword, page),
        fetch_remoteok(keyword, page),
    )
    seen, results = set(), []
    for job in adzuna + linkedin + remoteok:
        key = (job["title"].lower(), job["company"].lower())
        if key not in seen:
            seen.add(key)
            results.append(job)
    return results


async def search_all_keywords() -> list[dict]:
    all_results = await asyncio.gather(*[search_jobs(kw) for kw in KEYWORDS])
    seen, merged = set(), []
    for batch in all_results:
        for job in batch:
            key = (job["title"].lower(), job["company"].lower())
            if key not in seen:
                seen.add(key)
                merged.append(job)
    return merged


async def stream_search_jobs(keyword: str, page: int = 1):
    """Yield results from each source as soon as it completes."""
    tasks = {
        asyncio.ensure_future(fetch_adzuna(keyword, page)): "Adzuna",
        asyncio.ensure_future(fetch_linkedin(keyword, page)): "LinkedIn",
        asyncio.ensure_future(fetch_remoteok(keyword, page)): "RemoteOK",
    }
    seen = set()
    pending = set(tasks.keys())
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            jobs = task.result()
            fresh = []
            for job in jobs:
                key = (job["title"].lower(), job["company"].lower())
                if key not in seen:
                    seen.add(key)
                    fresh.append(job)
            if fresh:
                yield fresh
