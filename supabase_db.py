import os
import json
import logging
import asyncio
import aiohttp

logger = logging.getLogger("supabase_db")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://sucvajncnkgkrocwsdhe.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InN1Y3Zham5jbmtna3JvY3dzZGhlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODc1NjA0MjksImV4cCI6MjEwMzEzNjQyOX0.UyzS7XI64_UhhrKHxvo5ZPmZaA22dQql4wxHWYyQgNg")

_IS_CONNECTED = None
_sb_session = None

def get_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation"
    }

async def get_sb_session() -> aiohttp.ClientSession:
    global _sb_session
    if _sb_session is None or _sb_session.closed:
        connector = aiohttp.TCPConnector(limit=50, limit_per_host=25, keepalive_timeout=60, ttl_dns_cache=300)
        _sb_session = aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=5))
    return _sb_session

async def supabase_get(key: str, default=None):
    """Fetch JSON data from Supabase bot_store table by key with keep-alive pooling."""
    global _IS_CONNECTED
    if not SUPABASE_URL or not SUPABASE_KEY or _IS_CONNECTED is False:
        return default
    url = f"{SUPABASE_URL}/rest/v1/bot_store?key=eq.{key}&select=data"
    try:
        session = await get_sb_session()
        async with session.get(url, headers=get_headers()) as resp:
            if resp.status == 200:
                _IS_CONNECTED = True
                rows = await resp.json()
                if rows and len(rows) > 0:
                    return rows[0].get("data", default)
            elif resp.status == 404:
                _IS_CONNECTED = False
    except Exception as ex:
        logger.error(f"[supabase_get] Error fetching '{key}': {ex}")
    return default

async def supabase_set(key: str, data) -> bool:
    """Save JSON data to Supabase bot_store table with keep-alive pooling."""
    global _IS_CONNECTED
    if not SUPABASE_URL or not SUPABASE_KEY or _IS_CONNECTED is False:
        return False
    url = f"{SUPABASE_URL}/rest/v1/bot_store"
    payload = {
        "key": key,
        "data": data
    }
    try:
        session = await get_sb_session()
        async with session.post(url, json=payload, headers=get_headers()) as resp:
            if resp.status in (200, 201):
                _IS_CONNECTED = True
                return True
            elif resp.status == 404:
                _IS_CONNECTED = False
    except Exception as ex:
        logger.error(f"[supabase_set] Error saving '{key}': {ex}")
    return False

def sync_supabase_in_background(key: str, data):
    """Non-blocking helper to fire-and-forget sync to Supabase."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(supabase_set(key, data))
        else:
            loop.run_until_complete(supabase_set(key, data))
    except Exception:
        pass

async def supabase_sync_all_from_local():
    """Upload all local JSON database files to Supabase bot_store."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    files = {
        "users": "users.json",
        "categories": "categories.json",
        "orders": "orders.json",
        "stock": "stock.json",
        "giveaways": "giveaways.json",
        "custom_responses": "custom_responses.json",
        "used_references": "used_references.json"
    }
    results = {}
    for key, fname in files.items():
        fpath = os.path.join(base_dir, fname)
        if os.path.exists(fpath):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                ok = await supabase_set(key, data)
                results[key] = "Uploaded ✅" if ok else "Failed ❌"
            except Exception as ex:
                results[key] = f"Error: {ex}"
        else:
            results[key] = "Not found"
    return results

async def supabase_sync_all_to_local():
    """Download all datasets from Supabase bot_store to local JSON files."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    keys = ["users", "categories", "orders", "stock", "giveaways", "custom_responses", "used_references"]
    for key in keys:
        data = await supabase_get(key)
        if data is not None:
            fpath = os.path.join(base_dir, f"{key}.json")
            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as ex:
                logger.error(f"[supabase_sync_all_to_local] Failed to write {key}.json: {ex}")
