import aiohttp
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

HOLIDAY_CACHE_FILE = "usr/holidays.json"

try:
    BUDAPEST_TZ = ZoneInfo("Europe/Budapest")
except ZoneInfoNotFoundError:
    raise RuntimeError(
        "Missing timezone data for Europe/Budapest. "
        "On Windows/PyCharm, install it with: pip install tzdata"
    )


def ensure_cache_dir():
    os.makedirs(os.path.dirname(HOLIDAY_CACHE_FILE), exist_ok=True)


async def get_holidays(year=None):
    """
    Returns the full list of Hungarian public holiday objects for the given year.
    Caches the API response locally.
    """
    if year is None:
        year = datetime.now(BUDAPEST_TZ).year

    year_str = str(year)
    cache_data = {}

    ensure_cache_dir()

    if os.path.exists(HOLIDAY_CACHE_FILE):
        try:
            with open(HOLIDAY_CACHE_FILE, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            cache_data = {}

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

    try:
        with open(HOLIDAY_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=4, ensure_ascii=False)
    except OSError as e:
        print(f"baj van cache mentés közben: {e}")

    return holidays


async def get_holiday_dates(year=None):
    """Returns holiday dates as date objects."""
    holidays = await get_holidays(year)
    return [datetime.strptime(h["date"], "%Y-%m-%d").date() for h in holidays]


async def get_last_workday(base_date=None):
    """
    Returns the last workday of the week containing base_date.
    Usually Friday, but moves backward for weekday holidays.
    """
    if base_date is None:
        today = datetime.now(BUDAPEST_TZ).date()
    else:
        today = base_date

    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)

    years = {monday.year, friday.year}
    holiday_dates = []
    for year in years:
        holiday_dates.extend(await get_holiday_dates(year))

    last_workday = friday
    while last_workday in holiday_dates or last_workday.weekday() > 4:
        last_workday -= timedelta(days=1)

    return last_workday


async def get_next_holiday():
    """Returns the next upcoming weekday holiday, or None."""
    today = datetime.now(BUDAPEST_TZ).date()

    holidays = await get_holidays(today.year)
    holidays += await get_holidays(today.year + 1)

    future_holidays = []
    for h in holidays:
        holiday_date = datetime.strptime(h["date"], "%Y-%m-%d").date()
        if holiday_date >= today and holiday_date.weekday() < 5:
            future_holidays.append({
                "date": holiday_date,
                "localName": h["localName"],
                "name": h["name"],
                "days_until": (holiday_date - today).days,
            })

    return min(future_holidays, key=lambda x: x["date"]) if future_holidays else None


async def get_week_holidays():
    """Returns weekday holidays for the current week."""
    today = datetime.now(BUDAPEST_TZ).date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    years = {monday.year, sunday.year}
    holidays = []
    for year in years:
        holidays.extend(await get_holidays(year))

    week_holidays = []
    for h in holidays:
        holiday_date = datetime.strptime(h["date"], "%Y-%m-%d").date()
        if monday <= holiday_date <= sunday and holiday_date.weekday() < 5:
            week_holidays.append({
                "date": holiday_date,
                "localName": h["localName"],
                "days_until": (holiday_date - today).days,
            })

    week_holidays.sort(key=lambda x: x["date"])
    return week_holidays


async def get_non_workday_block_length(start_date):
    """
    Returns the length of the full continuous non-workday block containing start_date.
    Non-workdays are:
    - weekends
    - Hungarian public holidays
    """
    years = {start_date.year - 1, start_date.year, start_date.year + 1}
    holiday_dates = set()

    for year in years:
        holiday_dates.update(await get_holiday_dates(year))

    def is_non_workday(d):
        return d.weekday() >= 5 or d in holiday_dates

    if not is_non_workday(start_date):
        return 0

    count = 1

    prev_day = start_date - timedelta(days=1)
    while is_non_workday(prev_day):
        count += 1
        prev_day -= timedelta(days=1)

    next_day = start_date + timedelta(days=1)
    while is_non_workday(next_day):
        count += 1
        next_day += timedelta(days=1)

    return count


async def get_non_workday_block_label(start_date):
    """
    Returns a human-readable label for the continuous non-workday block.
    Examples:
    - None for a single isolated weekday holiday
    - '2 napos munkaszünet'
    - '4 napos hosszúhétvége'
    """
    years = {start_date.year - 1, start_date.year, start_date.year + 1}
    holiday_dates = set()

    for year in years:
        holiday_dates.update(await get_holiday_dates(year))

    def is_non_workday(d):
        return d.weekday() >= 5 or d in holiday_dates

    if not is_non_workday(start_date):
        return None

    block_days = [start_date]

    prev_day = start_date - timedelta(days=1)
    while is_non_workday(prev_day):
        block_days.append(prev_day)
        prev_day -= timedelta(days=1)

    next_day = start_date + timedelta(days=1)
    while is_non_workday(next_day):
        block_days.append(next_day)
        next_day += timedelta(days=1)

    block_length = len(block_days)
    includes_weekend = any(d.weekday() >= 5 for d in block_days)

    # single isolated weekday holiday -> no extra label
    if block_length == 1 and start_date.weekday() < 5:
        return None

    if includes_weekend:
        return f"{block_length} napos hosszúhétvége"

    return f"{block_length} napos munkaszünet"
