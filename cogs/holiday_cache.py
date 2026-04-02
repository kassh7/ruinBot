import aiohttp
import json
import os
from datetime import datetime, timedelta

HOLIDAY_CACHE_FILE = "holidays.json"

async def get_holidays(year=None):
    """
    Returns the full list of holiday objects for the given year.
    Caches the full API response so we have names, dates, everything.
    """
    if year is None:
        year = datetime.now().year

    year_str = str(year)
    cache_data = {}

    if os.path.exists(HOLIDAY_CACHE_FILE):
        with open(HOLIDAY_CACHE_FILE, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

    if year_str in cache_data:
        return cache_data[year_str]

    print(f"🌸 Ünnepnapok lekérése {year}-re az API-ból...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://date.nager.at/api/v3/PublicHolidays/{year}/HU") as resp:
                if resp.status != 200:
                    print(f"baj van: API returned status {resp.status}")
                    return []
                holidays = await resp.json()
    except Exception as e:
        print(f"baj van: {e}")
        return []

    cache_data[year_str] = holidays

    with open(HOLIDAY_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, indent=4, ensure_ascii=False)

    return holidays


async def get_holiday_dates(year=None):
    """Returns just the dates as date objects (for teletal workday calculation)."""
    holidays = await get_holidays(year)
    return [datetime.strptime(h['date'], "%Y-%m-%d").date() for h in holidays]


async def get_last_workday():
    """Kiszámolja a hét utolsó munkanapját."""
    today = datetime.now()
    holiday_dates = await get_holiday_dates(today.year)

    days_to_friday = 4 - today.weekday()
    last_workday = today.date() + timedelta(days=days_to_friday)

    while last_workday in holiday_dates or last_workday.weekday() > 4:
        last_workday -= timedelta(days=1)

    return last_workday


async def get_next_holiday():
    """Returns the next upcoming workday holiday, or None."""
    today = datetime.now().date()
    holidays = await get_holidays(today.year)

    for h in holidays:
        date = datetime.strptime(h['date'], "%Y-%m-%d").date()
        if date >= today and date.weekday() < 5:
            days_until = (date - today).days
            return {
                "date": date,
                "localName": h['localName'],
                "name": h['name'],
                "days_until": days_until
            }
    return None


async def get_week_holidays():
    """Returns any holidays that fall on a workday THIS week."""
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    holidays = await get_holidays(today.year)
    week_holidays = []

    for h in holidays:
        date = datetime.strptime(h['date'], "%Y-%m-%d").date()
        if monday <= date <= sunday and date.weekday() < 5:
            week_holidays.append({
                "date": date,
                "localName": h['localName'],
                "days_until": (date - today).days
            })

    return week_holidays
