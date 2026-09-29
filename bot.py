
# ─── STORE DEPARTMENTS / CATEGORIES ──────────────────────────
STORE_DEPARTMENTS = {
    "ai": {
        "title": "🤖 AI & Intelligence",
        "desc": "Gemini Advanced, Claude Pro, ChatGPT Plus, and AI models.",
        "icon": "🤖",
        "keywords": ["gemini", "chatgpt", "claude", "google ai", "higgsfield", "openai"]
    },
    "dev": {
        "title": "💻 Developer & Cloud",
        "desc": "Cursor Pro, Replit, Supabase, Railway, Lovable, n8n, Linear.",
        "icon": "💻",
        "keywords": ["cursor", "replit", "railway", "supabase", "lovable", "n8n", "linear", "warp", "jam", "magic"]
    },
    "design": {
        "title": "🎨 Design & Creative",
        "desc": "Canva Pro, Figma Edu, Framer, Gamma, Notion, CapCut, Runway.",
        "icon": "🎨",
        "keywords": ["canva", "figma", "framer", "gamma", "notion", "capcut", "runway", "adobe"]
    },
    "streaming": {
        "title": "🍿 Streaming & Media",
        "desc": "YouTube Premium, Netflix Ultra HD 4K Admin accounts.",
        "icon": "🍿",
        "keywords": ["youtube", "netflix"]
    },
    "vpn": {
        "title": "🛡️ VPN & Privacy",
        "desc": "Surfshark VPN accounts and high-speed privacy coupons.",
        "icon": "🛡️",
        "keywords": ["surfshark", "vpn", "nord"]
    },
    "career": {
        "title": "💼 Business & Career",
        "desc": "LinkedIn Business/Career/Sales, Coursera Premium, QuillBot.",
        "icon": "💼",
        "keywords": ["linkedin", "coursera", "quillbot"]
    },
    "audio": {
        "title": "🎙️ Voice & Audio AI",
        "desc": "ElevenLabs Creator voice generation, Whisper Flow transcription.",
        "icon": "🎙️",
        "keywords": ["elevenlabs", "whisper", "wisper"]
    }
}

def get_product_department(cat: dict) -> str:
    """Classify a product into a store department based on name/slug."""
    name = (cat.get("name", "") + " " + cat.get("id", "")).lower()
    for dept_id, info in STORE_DEPARTMENTS.items():
        if any(k in name for k in info["keywords"]):
            return dept_id
    return "ai"

"""
ET Market Bot
Custom emoji via entities array (not HTML tg-emoji tags)
icon_custom_emoji_id for buttons
Python 3.14 compatible — raw aiohttp, no python-telegram-bot

FIX NOTES (ENTITY_TEXT_INVALID):
- Telegram rejects the WHOLE message if any custom_emoji_id in the
  entities array is not a real, existing custom emoji sticker id.
- Since we can't verify IDs without hitting the API, send_msg/edit_msg
  now automatically retry WITHOUT entities if the first attempt fails
  with an entity-related error, so the bot never just dies on a bad id.
- Also normalized custom_emoji_id to str() and guarded against
  zero-length entity content.
"""

import asyncio
import logging
from logging.handlers import RotatingFileHandler
import aiohttp
import json
import math
import os
import re
import shutil
import sys
import time
import uuid
from datetime import datetime, timedelta
import supabase_db

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ─── PRODUCTION LOGGING SETUP ─────────────────────────────────
log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] [%(name)s] %(message)s')
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(console_handler)

LOG_FILE = os.path.join(os.path.dirname(__file__), "production.log")
try:
    log_handler = RotatingFileHandler(LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
    log_handler.setFormatter(log_formatter)
    root_logger.addHandler(log_handler)
except Exception:
    pass  # Serverless / read-only filesystem fallback to console logging

logger = logging.getLogger("et01marketbot")

# ─── ATOMIC PERSISTENCE & BACKUP SYSTEM ──────────────────────
BACKUP_DIR = os.path.join(os.path.dirname(__file__), "backups")

def atomic_save_json(file_path: str, data: dict):
    """Atomically write JSON to disk using temporary file replacement."""
    temp_path = f"{file_path}.tmp.{uuid.uuid4().hex[:8]}"
    try:
        dir_name = os.path.dirname(file_path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, file_path)
    except (PermissionError, OSError) as ex:
        logger.warning(f"[atomic_save] Disk read-only ({ex}), rely on Supabase cloud database.")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
    except Exception as ex:
        logger.error(f"[atomic_save] Failed to save {file_path}: {ex}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

def create_database_backup():
    """Create timestamped snapshot of JSON databases."""
    try:
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_dir = os.path.join(BACKUP_DIR, f"backup_{timestamp}")
        os.makedirs(target_dir, exist_ok=True)

        for filename in ("users.json", "categories.json", "stock.json", "orders.json", ".env"):
            src = os.path.join(os.path.dirname(__file__), filename)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(target_dir, filename))

        all_backups = sorted(
            [os.path.join(BACKUP_DIR, d) for d in os.listdir(BACKUP_DIR) if os.path.isdir(os.path.join(BACKUP_DIR, d))]
        )
        if len(all_backups) > 30:
            for old in all_backups[:-30]:
                shutil.rmtree(old, ignore_errors=True)
        logger.info(f"[Backup] Database backup completed: {target_dir}")
    except (PermissionError, OSError) as ex:
        logger.debug(f"[Backup] Read-only filesystem, skipping local disk backup: {ex}")
    except Exception as ex:
        logger.error(f"[Backup] Failed to create backup: {ex}")

async def backup_scheduler_loop():
    """Periodic database backup loop (every 6 hours)."""
    while True:
        try:
            await asyncio.sleep(6 * 3600)
            create_database_backup()
        except asyncio.CancelledError:
            break
        except Exception as ex:
            logger.error(f"[BackupLoop] Error: {ex}")
            await asyncio.sleep(60)

# ─── ANTI-FLOOD / RATE LIMITER ────────────────────────────────
class UserThrottler:
    """Sliding-window rate limiter to prevent bot abuse."""
    def __init__(self, max_requests=8, window_seconds=2.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.user_timestamps = {}

    def is_throttled(self, user_id: int) -> bool:
        now = time.time()
        timestamps = self.user_timestamps.get(user_id, [])
        valid = [t for t in timestamps if now - t < self.window_seconds]
        if len(valid) >= self.max_requests:
            self.user_timestamps[user_id] = valid
            return True
        valid.append(now)
        self.user_timestamps[user_id] = valid
        return False

throttler = UserThrottler()

# ─── CONFIG & .ENV MANAGER ────────────────────────────────────
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")

def _read_env_dict() -> dict:
    """Read all key-values from .env file."""
    env_vars = {}
    if os.path.exists(ENV_PATH):
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env_vars[k.strip()] = v.strip()
        except Exception as ex:
            logger.error(f"Error reading .env: {ex}")
    return env_vars

def set_env_setting(key: str, value: str):
    """Update setting in runtime globals, os.environ, and write to .env file."""
    global BOT_TOKEN, API, VERIFY_ET_API_KEY, LOG_CHANNEL_ID, LOG_CHANNEL_LINK
    global FORCE_JOIN_CHANNEL_ID, FORCE_JOIN_CHANNEL_NAME, FORCE_JOIN_CHANNEL_LINK
    global PAYMENT_NAME, PAYMENT_ACCOUNT, CBE_NAME, CBE_ACCOUNT, CBEBIRR_NAME, CBEBIRR_ACCOUNT, ADMINS
    global SAFWAN_API_KEY, SAFWAN_API_URL
    
    val_str = str(value).strip()
    os.environ[key] = val_str
    
    if key == "BOT_TOKEN":
        BOT_TOKEN = val_str
        API = f"https://api.telegram.org/bot{BOT_TOKEN}"
    elif key == "VERIFY_ET_API_KEY":
        VERIFY_ET_API_KEY = val_str
    elif key == "SAFWAN_API_KEY":
        SAFWAN_API_KEY = val_str
    elif key == "SAFWAN_API_URL":
        SAFWAN_API_URL = val_str
    elif key == "LOG_CHANNEL_ID":
        try:
            LOG_CHANNEL_ID = int(val_str)
        except ValueError:
            LOG_CHANNEL_ID = val_str
    elif key == "LOG_CHANNEL_LINK":
        LOG_CHANNEL_LINK = val_str
    elif key == "FORCE_JOIN_CHANNEL_ID":
        try:
            FORCE_JOIN_CHANNEL_ID = int(val_str)
        except ValueError:
            FORCE_JOIN_CHANNEL_ID = val_str
    elif key == "FORCE_JOIN_CHANNEL_NAME":
        FORCE_JOIN_CHANNEL_NAME = val_str
    elif key == "FORCE_JOIN_CHANNEL_LINK":
        FORCE_JOIN_CHANNEL_LINK = val_str
    elif key == "PAYMENT_NAME":
        PAYMENT_NAME = val_str
    elif key == "PAYMENT_ACCOUNT":
        PAYMENT_ACCOUNT = val_str
    elif key == "CBE_NAME":
        CBE_NAME = val_str
    elif key == "CBE_ACCOUNT":
        CBE_ACCOUNT = val_str
    elif key == "CBEBIRR_NAME":
        CBEBIRR_NAME = val_str
    elif key == "CBEBIRR_ACCOUNT":
        CBEBIRR_ACCOUNT = val_str
    elif key == "ADMINS":
        ADMINS = [int(x.strip()) for x in val_str.split(",") if x.strip().isdigit()]

    current_env = _read_env_dict()
    current_env[key] = val_str
    
    try:
        lines = [f"{k}={v}\n" for k, v in current_env.items()]
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception as ex:
        logger.error(f"Error saving to .env: {ex}")

_env = _read_env_dict()
BOT_TOKEN  = _env.get("BOT_TOKEN", os.environ.get("BOT_TOKEN", "8941788772:AAEcB0_55-aBBEYP_vHDOG0TnOq-3ozRWks"))
API        = f"https://api.telegram.org/bot{BOT_TOKEN}"
DB_PATH      = os.path.join(os.path.dirname(__file__), "users.json")
CAT_PATH     = os.path.join(os.path.dirname(__file__), "categories.json")
STOCK_PATH   = os.path.join(os.path.dirname(__file__), "stock.json")
GIVEAWAYS_PATH = os.path.join(os.path.dirname(__file__), "giveaways.json")
_gw_lock = asyncio.Lock()

# ─── ULTRA-FAST IN-MEMORY CACHE LAYER ─────────────────────────
_CACHE: dict[str, dict] = {
    "users": None,
    "categories": None,
    "stock": None,
    "orders": None,
    "giveaways": None,
    "custom_responses": None,
    "used_references": None,
}

def _load_giveaways() -> dict:
    if _CACHE["giveaways"] is not None:
        return _CACHE["giveaways"]
    if not os.path.exists(GIVEAWAYS_PATH):
        _CACHE["giveaways"] = {}
        return {}
    try:
        with open(GIVEAWAYS_PATH, "r", encoding="utf-8-sig") as f:
            _CACHE["giveaways"] = json.load(f)
            return _CACHE["giveaways"]
    except Exception:
        _CACHE["giveaways"] = {}
        return {}

def _save_giveaways(data: dict):
    _CACHE["giveaways"] = data
    atomic_save_json(GIVEAWAYS_PATH, data)
    supabase_db.sync_supabase_in_background("giveaways", data)

async def giveaway_create(cat_id: str, created_by: int) -> dict:
    """Create a new pending giveaway for a product."""
    cats = _load_categories()
    cat = cats.get(cat_id, {})
    gw_id = "gw_" + uuid.uuid4().hex[:8]
    
    gw = {
        "id": gw_id,
        "cat_id": cat_id,
        "cat_name": cat.get("name", "Exclusive Subscription"),
        "cat_type": cat.get("cat_type", "id_pass"),
        "safwan_product_id": cat.get("safwan_product_id"),
        "created_by": str(created_by),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "pending",
        "winner_id": None,
        "winner_username": None,
        "claimed_at": None,
        "channel_msg_id": None,
        "channel_id": None,
    }
    
    async with _gw_lock:
        data = _load_giveaways()
        data[gw_id] = gw
        _save_giveaways(data)
        
    return gw

async def giveaway_get(gw_id: str) -> dict | None:
    async with _gw_lock:
        data = _load_giveaways()
        return data.get(gw_id)

async def giveaway_claim_atomic(gw_id: str, user: dict) -> tuple[bool, dict]:
    """
    Atomically claim a giveaway.
    Strictly ONE winner is guaranteed under massive concurrency.
    Returns (is_winner, giveaway_data).
    """
    uid = str(user.get("id"))
    uname = f"@{user['username']}" if user.get("username") else (str(user.get("first_name", "")).strip() or f"User #{uid}")
    
    async with _gw_lock:
        data = _load_giveaways()
        gw = data.get(gw_id)
        if not gw:
            return False, {"error": "Giveaway not found"}
            
        if gw.get("status") == "active":
            # Claim atomically
            gw["status"] = "claimed"
            gw["winner_id"] = uid
            gw["winner_username"] = uname
            gw["claimed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data[gw_id] = gw
            _save_giveaways(data)
            return True, gw
        else:
            return False, gw

ORDERS_PATH  = os.path.join(os.path.dirname(__file__), "orders.json")
USED_REFS_PATH = os.path.join(os.path.dirname(__file__), "used_references.json")
_refs_lock = asyncio.Lock()

def _load_used_references() -> dict:
    if _CACHE["used_references"] is not None:
        return _CACHE["used_references"]
    if not os.path.exists(USED_REFS_PATH):
        _CACHE["used_references"] = {}
        return {}
    try:
        with open(USED_REFS_PATH, "r", encoding="utf-8-sig") as f:
            _CACHE["used_references"] = json.load(f)
            return _CACHE["used_references"]
    except Exception:
        _CACHE["used_references"] = {}
        return {}

def _save_used_references(data: dict):
    _CACHE["used_references"] = data
    atomic_save_json(USED_REFS_PATH, data)
    supabase_db.sync_supabase_in_background("used_references", data)

# ─── CUSTOM RESPONSES ENGINE ──────────────────────────────────
CUSTOM_RESPONSES_PATH = os.path.join(os.path.dirname(__file__), "custom_responses.json")
_responses_lock = asyncio.Lock()

def _load_custom_responses() -> dict:
    if _CACHE["custom_responses"] is not None:
        return _CACHE["custom_responses"]
    if not os.path.exists(CUSTOM_RESPONSES_PATH):
        _CACHE["custom_responses"] = {}
        return {}
    try:
        with open(CUSTOM_RESPONSES_PATH, "r", encoding="utf-8-sig") as f:
            _CACHE["custom_responses"] = json.load(f)
            return _CACHE["custom_responses"]
    except Exception:
        _CACHE["custom_responses"] = {}
        return {}

def _save_custom_responses(data: dict):
    _CACHE["custom_responses"] = data
    atomic_save_json(CUSTOM_RESPONSES_PATH, data)
    supabase_db.sync_supabase_in_background("custom_responses", data)

async def get_custom_response(key: str) -> dict | None:
    async with _responses_lock:
        data = _load_custom_responses()
        return data.get(key)

async def set_custom_response(key: str, text: str, entities: list = None):
    async with _responses_lock:
        data = _load_custom_responses()
        data[key] = {
            "text": text,
            "entities": entities or [],
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        _save_custom_responses(data)

async def reset_custom_response(key: str):
    async with _responses_lock:
        data = _load_custom_responses()
        if key in data:
            del data[key]
            _save_custom_responses(data)

async def res_all_custom_responses():
    async with _responses_lock:
        _save_custom_responses({})

RESPONSE_TEMPLATES = {
    "welcome": {
        "name": "🏠 Welcome Message",
        "desc": "Main screen shown on /start and main menu",
        "placeholders": ["{user}", "{username}", "{id}", "{balance}", "{channel_name}"],
    },
    "terms": {
        "name": "📃 Terms & Conditions",
        "desc": "Terms shown on onboarding or /help",
        "placeholders": ["{user}", "{support_link}"],
    },
    "join_prompt": {
        "name": "🔒 Channel Join Prompt",
        "desc": "Force-join channel lock screen",
        "placeholders": ["{channel_name}", "{channel_link}"],
    },
    "support": {
        "name": "🎧 Support Screen",
        "desc": "Customer service & support message",
        "placeholders": ["{support_link}", "{channel_link}"],
    },
    "referral": {
        "name": "👥 Referral Screen",
        "desc": "Referral program & rewards screen",
        "placeholders": ["{user}", "{id}", "{channel_link}"],
    },
    "help": {
        "name": "❓ Help & Commands",
        "desc": "Help command guide",
        "placeholders": ["{support_link}", "{channel_name}"],
    },
    "topup_prompt": {
        "name": "💳 Top-Up Prompt",
        "desc": "Wallet deposit amount prompt",
        "placeholders": ["{balance}", "{user}"],
    },
    "telebirr_instructions": {
        "name": "💙 Telebirr Payment Text",
        "desc": "Payment instructions for Telebirr transfers",
        "placeholders": ["{amount}", "{name}", "{account}", "{expiry}"],
    },
    "cbe_instructions": {
        "name": "🏛 CBE Bank Payment Text",
        "desc": "Payment instructions for Commercial Bank of Ethiopia transfers",
        "placeholders": ["{amount}", "{name}", "{account}", "{expiry}"],
    },
    "cbebirr_instructions": {
        "name": "🏦 CBE Birr Payment Text",
        "desc": "Payment instructions for CBE Birr mobile money transfers",
        "placeholders": ["{amount}", "{name}", "{account}", "{expiry}"],
    },
    "dev_info": {
        "name": "👨‍💻 Developer Info",
        "desc": "Developer credit screen",
        "placeholders": ["{dev_link}"],
    },
    "bot_logs": {
        "name": "📊 Bot Logs Screen",
        "desc": "Live order logs and status tracker screen",
        "placeholders": ["{total_orders}", "{completed_orders}", "{pending_orders}", "{cancelled_orders}", "{total_volume}", "{channel_link}"],
    },
}

def render_text_template(raw_text: str, entities: list, context: dict) -> tuple[str, list]:
    """
    Interpolate {variables} in raw_text and accurately shift entity offsets (supporting custom emojis).
    """
    if not raw_text:
        return "", []
    
    text = raw_text
    adjusted_entities = [dict(e) for e in (entities or [])]
    
    if not context:
        return text, adjusted_entities

    for key, val in context.items():
        placeholder = f"{{{key}}}"
        val_str = str(val) if val is not None else ""
        while placeholder in text:
            pos = text.find(placeholder)
            if pos == -1:
                break
            diff = u16(val_str) - u16(placeholder)
            u16_pos = u16(text[:pos])
            u16_placeholder_len = u16(placeholder)
            
            # Replace text
            text = text[:pos] + val_str + text[pos + len(placeholder):]
            
            # Adjust entities
            for ent in adjusted_entities:
                ent_offset = ent.get("offset", 0)
                if ent_offset >= u16_pos + u16_placeholder_len:
                    ent["offset"] = ent_offset + diff
                elif ent_offset >= u16_pos:
                    ent["offset"] = u16_pos

    return text, adjusted_entities

def is_reference_used(ref: str) -> bool:
    """Check if a transaction reference has already been used/approved."""
    if not ref:
        return False
    clean_ref = ref.strip().upper()
    used_data = _load_used_references()
    if clean_ref in used_data:
        return True
    orders = _load_orders()
    for o in orders.values():
        if o.get("status") == "approved":
            if o.get("transaction_ref") == clean_ref:
                return True
            s_id = str(o.get("screenshot_file_id") or "").upper()
            if clean_ref in s_id:
                return True
    return False

async def mark_reference_used(ref: str, order_id: str, user_id: str, amount: float):
    """Mark a transaction reference as permanently used and save to persistent storage."""
    if not ref:
        return
    clean_ref = ref.strip().upper()
    async with _refs_lock:
        used_data = _load_used_references()
        used_data[clean_ref] = {
            "order_id": order_id,
            "user_id": str(user_id),
            "amount": amount,
            "used_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        _save_used_references(used_data)
        
    async with _ord_lock:
        orders = _load_orders()
        if order_id in orders:
            orders[order_id]["transaction_ref"] = clean_ref
            _save_orders(orders)

# Verify.ET Automated Verification API Config
VERIFY_ET_API_KEY = _env.get("VERIFY_ET_API_KEY", os.environ.get("VERIFY_ET_API_KEY", ""))
VERIFY_ET_URL     = "https://verify.et/api/verify"

# SafwanTiger Reseller API Config (Auto-delivery)
SAFWAN_API_KEY = _env.get("SAFWAN_API_KEY", os.environ.get("SAFWAN_API_KEY", "stapi_67ea316bf7110d628416ed5d87def368a516e62a27988b7c8136aa3763681a02"))
SAFWAN_API_URL = _env.get("SAFWAN_API_URL", os.environ.get("SAFWAN_API_URL", "https://safwantigershopbot-production.up.railway.app/api"))

# Payment details — Telebirr
PAYMENT_IMAGE   = os.path.join(os.path.dirname(__file__), "image.jpg")
PAYMENT_NAME    = _env.get("PAYMENT_NAME", "Gelana WoldaYesus")
PAYMENT_ACCOUNT = _env.get("PAYMENT_ACCOUNT", "0967979014")
ORDER_EXPIRY_MINUTES = 30

# Payment details — CBE Bank
CBE_IMAGE   = os.path.join(os.path.dirname(__file__), "cbe.jpg")
CBE_NAME    = _env.get("CBE_NAME", "Naol Meseret Fransua")
CBE_ACCOUNT = _env.get("CBE_ACCOUNT", "1000424161075")

# Payment details — CBE Birr
CBEBIRR_IMAGE   = os.path.join(os.path.dirname(__file__), "cbe.jpg")
CBEBIRR_NAME    = _env.get("CBEBIRR_NAME", "Naol Meseret")
CBEBIRR_ACCOUNT = _env.get("CBEBIRR_ACCOUNT", "0967979014")

# Sales log group
_log_ch = _env.get("LOG_CHANNEL_ID", "-1003806764959")
try:
    LOG_CHANNEL_ID = int(_log_ch)
except ValueError:
    LOG_CHANNEL_ID = _log_ch
LOG_CHANNEL_LINK = _env.get("LOG_CHANNEL_LINK", "https://t.me/+2RORZ17pHqNiYzM0")

# Admin user IDs
_admins_str = _env.get("ADMINS", "1675909278")
ADMINS = [int(x.strip()) for x in _admins_str.split(",") if x.strip().isdigit()]

# Force Join
_fj_ch = _env.get("FORCE_JOIN_CHANNEL_ID", "-1003806764959")
try:
    FORCE_JOIN_CHANNEL_ID = int(_fj_ch)
except ValueError:
    FORCE_JOIN_CHANNEL_ID = _fj_ch
FORCE_JOIN_CHANNEL_LINK = _env.get("FORCE_JOIN_CHANNEL_LINK", "https://t.me/et_market_place")
FORCE_JOIN_CHANNEL_NAME = _env.get("FORCE_JOIN_CHANNEL_NAME", "ET MARKET")
SUPPORT_LINK = _env.get("SUPPORT_LINK", "https://t.me/mrdef4fult")
DEVELOPER_LINK = _env.get("DEVELOPER_LINK", "https://t.me/kidanewold777")


# ─── TERMS & CONDITIONS ───────────────────────────────────────
TERMS_TEXT = """📃 Terms & Conditions

Welcome to ET Market. By using our bot and services, you agree to the following terms:

1️⃣ Order Confirmation
Please check the product name, duration, price, and requirements before placing an order.

2️⃣ Payment
All payments must be completed using the payment methods shown in the bot. After payment, you must tap I've Paid or send payment proof/transaction ID.

3️⃣ Delivery Time
Delivery time depends on the product. Some products are instant, while others may take time for activation.

4️⃣ Correct Information
Customers must provide correct email, username, phone number, or account details when required. We are not responsible for delays or issues caused by incorrect information.

5️⃣ Warranty
Warranty depends on the product. Some products include full warranty, some include activation warranty only, and some have no warranty after activation. Please read the product details before buying.

6️⃣ Refund Policy
Refunds are only available if the product cannot be delivered or activated. Refunds are not available after successful delivery/activation unless the product has warranty.

7️⃣ Account Safety
Do not change passwords, emails, or account details during activation unless support tells you to do so.

8️⃣ Support
If you face any issue, contact support with your order proof, payment proof, and problem details.

9️⃣ Stock Availability
Products may go out of stock at any time. If a product is unavailable, you can wait for restock or choose another product.

💰 By placing an order, you confirm that you have read and accepted these terms."""

# ─── PREMIUM EMOJIS ───────────────────────────────────────────
# IMPORTANT: These custom_emoji_ids must correspond to REAL Telegram
# Premium custom emoji stickers, or Telegram will reject the message
# with ENTITY_TEXT_INVALID. To get real ids: send/forward a message
# containing the premium emoji to @RawDataBot or @userinfobot and
# read the "custom_emoji_id" field from the returned entities JSON.
PREMIUM_EMOJIS = {
    # Core navigation & system
    "wave":         "6041921818896372382",
    "bot":          "6030400221232501136",
    "shop":         "5447387942995655277",
    "profile":      "5445174334031166029",
    "menu":         "5445260044398524944",
    "wallet":       "5447453226498552490",
    "referral":     "6037175527846975726",
    "down":         "5893057118545646106",
    "back":         "5352759161945867747",
    "home":         "5352759161945867747",
    "forward":      "5435955998479102657",
    
    # Store, products & actions
    "balance":      "6233367447789899509",
    "check":        "5206607081334906820",
    "cart":         "5226656353744862682",
    "bag":          "5226656353744862682",
    "key":          "5278573677900752088",
    "box":          "5355193051193059834",
    "pop":          "5208541126583136130",
    "clock":        "5465248203718794436",
    "timer":        "5222175229681343920",
    "camera":       "5235837920081887219",
    "thunder":      "5258203794772085854",
    "fire":         "5258203794772085854",
    "arrow":        "5435955998479102657",
    "clipboard":    "5197269100878907942",
    "cross":        "5210952531676504517",
    "checkmark":    "5206607081334906820",
    "star":         "5208541126583136130",
    "sparkles":     "5208541126583136130",
    "gift":         "6037175527846975726",
    "diamond":      "5447453226498552490",
    "add":          "5226656353744862682",
    "share":        "6037175527846975726",
    "soon":         "5222175229681343920",
    "earn":         "5447453226498552490",
    "id":           "5278573677900752088",
    "status":       "5206607081334906820",
    "ping":         "5258203794772085854",
    "cmd":          "5197269100878907942",
    "other":        "5278573677900752088",
    "link":         "5891243564309942507",
    "lock":         "5278573677900752088",
    "unlock":       "5206607081334906820",
    "shield":       "5206607081334906820",
    "crown":        "5208541126583136130",
    "search":       "5197269100878907942",
    
    # Numbers & steps
    "number1":      "5269520668524821648",
    "number2":      "5269293426100157176",
    "number3":      "5269412160471053597",
    "number4":      "5269624830071686015",
    
    # Contact, payment & accounts
    "user":         "6174508000489768736",
    "mobile":       "6177059060739741318",
    "instructions": "5458801848649532015",
    "bank":         "5332455502917949981",
    "cbe":          "5961054379350955385",
    "telebirr":     "5960632377339285724",
    "channel":      "5891243564309942507",
    "support":      "5922612721244704425",
    "document":     "5456163794017028654",
    "paywallet":    "5769403330761593044",
}

# Unicode fallback chars for each emoji key
EMOJI_CHAR = {
    "wave":         "👋",
    "bot":          "🤖",
    "shop":         "🛒",
    "profile":      "👤",
    "menu":         "📋",
    "wallet":       "💰",
    "referral":     "🎁",
    "down":         "⬇️",
    "back":         "⬅️",
    "home":         "🏠",
    "forward":      "➡️",
    "add":          "➕",
    "share":        "📤",
    "star":         "⭐",
    "bag":          "🛍️",
    "fire":         "🔥",
    "check":        "✅",
    "soon":         "🔜",
    "support":      "💬",
    "earn":         "💸",
    "id":           "🪪",
    "balance":      "💳",
    "status":       "🟢",
    "ping":         "📡",
    "cmd":          "📋",
    "other":        "🔧",
    "link":         "🔗",
    "cart":         "🛒",
    "key":          "🔑",
    "box":          "📦",
    "pop":          "🎉",
    "clock":        "🕐",
    "timer":        "⏳",
    "camera":       "📸",
    "thunder":      "⚡",
    "arrow":        "▶",
    "clipboard":    "📋",
    "cross":        "❌",
    "checkmark":    "✔️",
    "sparkles":     "✨",
    "gift":         "🎁",
    "diamond":      "💎",
    "lock":         "🔒",
    "unlock":       "🔓",
    "shield":       "🛡️",
    "crown":        "👑",
    "search":       "🔍",
    "number1":      "1️⃣",
    "number2":      "2️⃣",
    "number3":      "3️⃣",
    "number4":      "4️⃣",
    "user":         "👤",
    "mobile":       "📱",
    "instructions": "📝",
    "bank":         "🏦",
    "cbe":          "🏦",
    "telebirr":     "💙",
    "channel":      "📢",
    "document":     "📃",
    "paywallet":    "💳",
}

# ─── UTF-16 HELPER ────────────────────────────────────────────
def u16(s: str) -> int:
    """UTF-16-LE length (Telegram uses this for entity offsets)."""
    return len(s.encode("utf-16-le")) // 2

def merge_with_prefix(prefix_text: str, body_text: str, body_entities: list = None) -> tuple[str, list]:
    """Combine prefix_text and body_text while accurately shifting body_entities offsets."""
    if not body_entities:
        return f"{prefix_text}{body_text}", []
    p_len = u16(prefix_text)
    shifted = [dict(e, offset=e["offset"] + p_len) for e in body_entities]
    return f"{prefix_text}{body_text}", shifted

# ─── GLOBAL UNICODE TO CUSTOM EMOJI MAPPER ────────────────────
UNICODE_TO_CUSTOM_EMOJI = {
    # Core icons
    "👋": PREMIUM_EMOJIS["wave"],
    "🤖": PREMIUM_EMOJIS["bot"],
    "🛒": PREMIUM_EMOJIS["shop"],
    "🛍️": PREMIUM_EMOJIS["shop"],
    "🛍": PREMIUM_EMOJIS["shop"],
    "👤": PREMIUM_EMOJIS["user"],
    "👥": PREMIUM_EMOJIS["user"],
    "💰": PREMIUM_EMOJIS["wallet"],
    "💳": PREMIUM_EMOJIS["balance"],
    "🎁": PREMIUM_EMOJIS["gift"],
    "✅": PREMIUM_EMOJIS["check"],
    "✔️": PREMIUM_EMOJIS["check"],
    "❌": PREMIUM_EMOJIS["cross"],
    "⚡": PREMIUM_EMOJIS["thunder"],
    "🔥": PREMIUM_EMOJIS["thunder"],
    "⭐": PREMIUM_EMOJIS["star"],
    "✨": PREMIUM_EMOJIS["sparkles"],
    "🎉": PREMIUM_EMOJIS["pop"],
    "🔑": PREMIUM_EMOJIS["key"],
    "🔒": PREMIUM_EMOJIS["lock"],
    "🔓": PREMIUM_EMOJIS["unlock"],
    "📦": PREMIUM_EMOJIS["box"],
    "⏳": PREMIUM_EMOJIS["timer"],
    "🕐": PREMIUM_EMOJIS["clock"],
    "📸": PREMIUM_EMOJIS["camera"],
    "📋": PREMIUM_EMOJIS["clipboard"],
    "📝": PREMIUM_EMOJIS["instructions"],
    "📃": PREMIUM_EMOJIS["document"],
    "📱": PREMIUM_EMOJIS["mobile"],
    "🏦": PREMIUM_EMOJIS["bank"],
    "💙": PREMIUM_EMOJIS["telebirr"],
    "📢": PREMIUM_EMOJIS["channel"],
    "🔗": PREMIUM_EMOJIS["link"],
    "💎": PREMIUM_EMOJIS["diamond"],
    "👑": PREMIUM_EMOJIS["crown"],
    "🛡️": PREMIUM_EMOJIS["shield"],
    "🛡": PREMIUM_EMOJIS["shield"],
    "🔍": PREMIUM_EMOJIS["search"],
    "🔎": PREMIUM_EMOJIS["search"],
    "1️⃣": PREMIUM_EMOJIS["number1"],
    "2️⃣": PREMIUM_EMOJIS["number2"],
    "3️⃣": PREMIUM_EMOJIS["number3"],
    "4️⃣": PREMIUM_EMOJIS["number4"],
    "💬": PREMIUM_EMOJIS["support"],
    "🎧": PREMIUM_EMOJIS["support"],
    "🔧": PREMIUM_EMOJIS["other"],
    "⚙️": PREMIUM_EMOJIS["other"],
    "⚙": PREMIUM_EMOJIS["other"],
    "➕": PREMIUM_EMOJIS["add"],
    "➖": PREMIUM_EMOJIS["back"],
    "➡️": PREMIUM_EMOJIS["forward"],
    "➡": PREMIUM_EMOJIS["forward"],
    "⬅️": PREMIUM_EMOJIS["back"],
    "⬅": PREMIUM_EMOJIS["back"],
    "▶": PREMIUM_EMOJIS["forward"],
    "⬇️": PREMIUM_EMOJIS["down"],
    "⬇": PREMIUM_EMOJIS["down"],
    "🚀": PREMIUM_EMOJIS["thunder"],
    "💡": PREMIUM_EMOJIS["star"],
    "🟢": PREMIUM_EMOJIS["check"],
    "🔴": PREMIUM_EMOJIS["cross"],
    "⚪": PREMIUM_EMOJIS["other"],
    "✏️": PREMIUM_EMOJIS["instructions"],
    "✏": PREMIUM_EMOJIS["instructions"],
    "🔄": PREMIUM_EMOJIS["other"],
    "🗑️": PREMIUM_EMOJIS["cross"],
    "🗑": PREMIUM_EMOJIS["cross"],
    "🏛": PREMIUM_EMOJIS["cbe"],
    "🏛️": PREMIUM_EMOJIS["cbe"],
    "ℹ️": PREMIUM_EMOJIS["clipboard"],
    "ℹ": PREMIUM_EMOJIS["clipboard"],
    "🔔": PREMIUM_EMOJIS["star"],
    "📡": PREMIUM_EMOJIS["thunder"],
    "💸": PREMIUM_EMOJIS["wallet"],
    "🏠": PREMIUM_EMOJIS["home"],
}

_SORTED_EMOJIS = sorted(UNICODE_TO_CUSTOM_EMOJI.keys(), key=lambda x: -len(x))
_GLOBAL_EMOJI_PATTERN = re.compile("|".join(re.escape(k) for k in _SORTED_EMOJIS))

def enrich_custom_emojis(text: str, entities: list = None) -> tuple[str, list]:
    """Scan text and upgrade all standard unicode emojis to Telegram Premium custom emoji entities."""
    if not text:
        return text, entities or []
    
    # Fast path: skip parsing if text contains no matched emoji
    if not _GLOBAL_EMOJI_PATTERN.search(text):
        return text, entities or []
    
    new_entities = list(entities or [])
    
    # Collect all existing custom_emoji offsets to prevent double tagging
    existing_ranges = set()
    for e in new_entities:
        if e.get("type") == "custom_emoji":
            off = e.get("offset", 0)
            ln = e.get("length", 0)
            for x in range(off, off + ln):
                existing_ranges.add(x)
                
    utf16_pos = 0
    char_pos = 0
    
    for match in _GLOBAL_EMOJI_PATTERN.finditer(text):
        m_start = match.start()
        m_str = match.group(0)
        
        prefix = text[char_pos:m_start]
        utf16_pos += u16(prefix)
        char_pos = m_start
        
        m_u16_len = u16(m_str)
        covered = any((utf16_pos + k) in existing_ranges for k in range(m_u16_len))
        if not covered:
            eid = UNICODE_TO_CUSTOM_EMOJI.get(m_str)
            if eid:
                new_entities.append({
                    "type": "custom_emoji",
                    "offset": utf16_pos,
                    "length": m_u16_len,
                    "custom_emoji_id": str(eid),
                })
                for k in range(m_u16_len):
                    existing_ranges.add(utf16_pos + k)
                    
        utf16_pos += m_u16_len
        char_pos += len(m_str)
        
    return text, new_entities

# ─── MESSAGE BUILDER ──────────────────────────────────────────
class Msg:
    """
    Build a message with premium emoji entities.

    Usage:
        m = Msg()
        m.emoji("wave")
        m.text("  Welcome to ")
        m.bold("ET Market")
        m.text("\\n\\n")
        text, entities = m.build()
    """
    def __init__(self):
        self._parts   = []   # list of (kind, content, eid, key)
        self._current = ""

    def _flush(self):
        if self._current:
            self._parts.append(("text", self._current, None, None))
            self._current = ""

    def text(self, s: str):
        self._current += s
        return self

    def italic(self, s: str):
        self._flush()
        self._parts.append(("italic", s, None, None))
        return self

    def underline(self, s: str):
        self._flush()
        self._parts.append(("underline", s, None, None))
        return self

    def strike(self, s: str):
        self._flush()
        self._parts.append(("strike", s, None, None))
        return self

    def bold(self, s: str):
        self._flush()
        self._parts.append(("bold", s, None, None))
        return self

    def code(self, s: str):
        self._flush()
        self._parts.append(("code", s, None, None))
        return self

    def custom_emoji(self, char: str, custom_emoji_id: str):
        self._flush()
        if custom_emoji_id:
            self._parts.append(("custom_emoji", char or "⭐", str(custom_emoji_id), None))
        else:
            self._current += (char or "⭐")
        return self

    def raw_with_entities(self, text_segment: str, entities: list = None):
        self._flush()
        if not text_segment:
            return self
        if not entities:
            self._parts.append(("text", text_segment, None, None))
            return self
        self._parts.append(("raw_with_entities", text_segment, entities, None))
        return self

    def emoji(self, key: str):
        self._flush()
        char = EMOJI_CHAR.get(key, "⭐")
        eid  = PREMIUM_EMOJIS.get(key)
        self._parts.append(("emoji", char, eid, key))
        return self

    def nl(self, n: int = 1):
        self._current += "\n" * n
        return self

    def build(self):
        self._flush()
        full_text = ""
        entities  = []
        offset    = 0

        for kind, content, eid, key in self._parts:
            if kind == "raw_with_entities":
                ext_entities = eid or []
                for ent in ext_entities:
                    adjusted = dict(ent)
                    adjusted["offset"] = ent.get("offset", 0) + offset
                    entities.append(adjusted)
                length = u16(content)
                full_text += content
                offset += length
                continue

            length = u16(content)
            if length > 0:
                if (kind == "emoji" and eid) or (kind == "custom_emoji" and eid):
                    entities.append({
                        "type":            "custom_emoji",
                        "offset":          offset,
                        "length":          length,
                        "custom_emoji_id": str(eid),
                    })
                elif kind == "bold":
                    entities.append({
                        "type":   "bold",
                        "offset": offset,
                        "length": length,
                    })
                elif kind == "italic":
                    entities.append({
                        "type":   "italic",
                        "offset": offset,
                        "length": length,
                    })
                elif kind == "underline":
                    entities.append({
                        "type":   "underline",
                        "offset": offset,
                        "length": length,
                    })
                elif kind == "strike":
                    entities.append({
                        "type":   "strikethrough",
                        "offset": offset,
                        "length": length,
                    })
                elif kind == "code":
                    entities.append({
                        "type":   "code",
                        "offset": offset,
                        "length": length,
                    })
            full_text += content
            offset    += length

        # Automatically enrich any unicode emojis into Telegram custom emojis
        full_text, entities = enrich_custom_emojis(full_text, entities)
        return full_text, entities

# ─── BUTTON HELPERS ───────────────────────────────────────────
_LEADING_EMOJI_RE = re.compile(
    r"^[\U00010000-\U0010ffff\u2600-\u27ff\u2300-\u23ff\u2b00-\u2bff\u2190-\u21ff\u25a0-\u25ff\u200d\ufe00-\ufe0f\s]+"
)

def btn(text: str, callback_data: str = None, url: str = None,
        emoji_key: str = None, style: str = None, custom_emoji_id: str = None) -> dict:
    clean_text = text
    custom_icon_id = custom_emoji_id
    
    if not custom_icon_id and emoji_key and PREMIUM_EMOJIS.get(emoji_key):
        custom_icon_id = PREMIUM_EMOJIS[emoji_key]
    
    # If no emoji_key or custom_emoji_id provided, automatically detect if text starts with an emoji in our map
    if not custom_icon_id:
        for emo, cid in sorted(UNICODE_TO_CUSTOM_EMOJI.items(), key=lambda x: -len(x[0])):
            if text.startswith(emo):
                custom_icon_id = cid
                break
                
    if custom_icon_id:
        stripped = _LEADING_EMOJI_RE.sub("", text).strip()
        if stripped:
            clean_text = stripped

    b: dict = {"text": clean_text}
    if callback_data:
        b["callback_data"] = callback_data
    elif url:
        b["url"] = url
    else:
        b["callback_data"] = "noop"
        
    if custom_icon_id:
        b["icon_custom_emoji_id"] = str(custom_icon_id)
    if style in ("success", "danger"):
        b["style"] = style
    return b

def build_keyboard(rows: list) -> dict:
    return {"inline_keyboard": rows}

# ─── HTTP SESSION ─────────────────────────────────────────────
_session: aiohttp.ClientSession | None = None

async def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        connector = aiohttp.TCPConnector(
            limit=150,
            limit_per_host=75,
            ttl_dns_cache=600,
            keepalive_timeout=75,
            enable_cleanup_closed=True
        )
        _session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=45, sock_read=30, sock_connect=10)
        )
    return _session

async def close_session():
    global _session
    if _session and not _session.closed:
        await _session.close()

# ─── RAW API ──────────────────────────────────────────────────
async def api_call(method: str, payload: dict):
    session = await get_session()
    try:
        async with session.post(f"{API}/{method}", json=payload) as r:
            data = await r.json()
            if not data.get("ok"):
                logger.error(f"[{method}] {data.get('description','?')}")
            return data
    except Exception as ex:
        logger.error(f"[{method}] {ex}")
        return {"ok": False}

def _is_entity_error(data: dict) -> bool:
    desc = (data.get("description") or "").upper()
    return any(k in desc for k in ("ENTITY", "CUSTOM_EMOJI", "EMOJI", "PARSE_MODE", "OFFSET", "LENGTH", "CAN'T USE"))

async def send_msg(chat_id, text: str, entities: list = None,
                   keyboard: dict = None):
    # Automatically enrich any unicode emojis in the text into custom premium emojis
    text, entities = enrich_custom_emojis(text, entities)
    payload: dict = {
        "chat_id":                  chat_id,
        "text":                     text,
        "disable_web_page_preview": True,
    }
    if entities:
        payload["entities"] = entities
    if keyboard:
        payload["reply_markup"] = keyboard

    data = await api_call("sendMessage", payload)

    # Fallback: if entities caused the failure (e.g. bad custom_emoji_id),
    # retry once with plain text so the user still gets a reply.
    if not data.get("ok") and entities and _is_entity_error(data):
        logger.warning("Retrying sendMessage without entities (entity error).")
        logger.warning(f"Failing entities were: {entities}")
        logger.warning(f"Text was: {repr(text)}")
        payload.pop("entities", None)
        data = await api_call("sendMessage", payload)

    return data

async def send_photo(chat_id, photo_url: str, caption: str = "",
                     entities: list = None, keyboard: dict = None):
    if caption:
        caption, entities = enrich_custom_emojis(caption, entities)
    payload: dict = {
        "chat_id": chat_id,
        "photo":   photo_url,
    }
    if caption:
        payload["caption"] = caption
    if entities:
        payload["caption_entities"] = entities
    if keyboard:
        payload["reply_markup"] = keyboard

    data = await api_call("sendPhoto", payload)

    # Fallback: if entities caused the failure
    if not data.get("ok") and entities and _is_entity_error(data):
        logger.warning("Retrying sendPhoto without entities.")
        payload.pop("caption_entities", None)
        data = await api_call("sendPhoto", payload)

    return data

async def send_local_photo(chat_id, file_path: str, caption: str = "",
                            keyboard: dict = None, caption_entities: list = None):
    """Upload a local image file as a photo with optional caption and entities."""
    if caption:
        caption, caption_entities = enrich_custom_emojis(caption, caption_entities)
    session = await get_session()
    try:
        with open(file_path, "rb") as f:
            form = aiohttp.FormData()
            form.add_field("chat_id", str(chat_id))
            if caption:
                form.add_field("caption", caption)
            if caption_entities:
                form.add_field("caption_entities", json.dumps(caption_entities))
            if keyboard:
                form.add_field("reply_markup", json.dumps(keyboard))
            form.add_field(
                "photo", f,
                filename=os.path.basename(file_path),
                content_type="image/jpeg"
            )
            async with session.post(f"{API}/sendPhoto", data=form) as r:
                data = await r.json()
                if not data.get("ok"):
                    logger.error(f"[send_local_photo] {data.get('description','?')}")
                    if caption_entities and _is_entity_error(data):
                        # Retry without caption entities
                        return await send_local_photo(chat_id, file_path, caption, keyboard, None)
                return data
    except Exception as ex:
        logger.error(f"[send_local_photo] {ex}")
        return {"ok": False}

async def get_user_profile_photos(user_id):
    """Get user profile photos. Returns list of photo objects."""
    data = await api_call("getUserProfilePhotos", {
        "user_id": user_id,
        "limit":   1,
    })
    if data.get("ok"):
        photos = data.get("result", {}).get("photos", [])
        return photos
    return []

async def edit_msg(chat_id, message_id: int, text: str,
                   entities: list = None, keyboard: dict = None):
    text, entities = enrich_custom_emojis(text, entities)
    payload: dict = {
        "chat_id":                  chat_id,
        "message_id":               message_id,
        "text":                     text,
        "disable_web_page_preview": True,
    }
    if entities:
        payload["entities"] = entities
    if keyboard:
        payload["reply_markup"] = keyboard

    data = await api_call("editMessageText", payload)

    if not data.get("ok") and entities and _is_entity_error(data):
        logger.warning("Retrying editMessageText without entities (entity error).")
        payload.pop("entities", None)
        data = await api_call("editMessageText", payload)

    return data

async def edit_caption(chat_id, message_id: int, caption: str,
                       entities: list = None, keyboard: dict = None):
    caption, entities = enrich_custom_emojis(caption, entities)
    payload: dict = {
        "chat_id":    chat_id,
        "message_id": message_id,
        "caption":    caption,
    }
    if entities:
        payload["caption_entities"] = entities
    if keyboard:
        payload["reply_markup"] = keyboard

    data = await api_call("editMessageCaption", payload)

    if not data.get("ok") and entities and _is_entity_error(data):
        logger.warning("Retrying editMessageCaption without entities (entity error).")
        payload.pop("caption_entities", None)
        data = await api_call("editMessageCaption", payload)

    return data

def build_profile(user: dict, db_data: dict) -> tuple:
    """Build user profile card showing name, ID, balance, total spent, orders, and joined date."""
    db_data = db_data or {}
    uid = str(user.get("id") or db_data.get("user_id", ""))
    uname = f"@{user['username']}" if user.get("username") else (str(user.get("first_name", "")).strip() or db_data.get("first_name", "Valued Customer"))
    
    balance = float(db_data.get("balance", 0.0) or 0.0)
    total_spent = float(db_data.get("total_spent", 0.0) or 0.0)
    products_bought = int(db_data.get("products_bought", 0) or 0)
    joined_at = db_data.get("joined_at", "Recently")
    ref_count = int(db_data.get("referrals_count", 0) or 0)
    
    m = Msg()
    m.emoji("profile").text(" ").bold("My Account Profile").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("user").text(" Name: ").bold(uname).nl()
    m.emoji("key").text(" User ID: ").code(uid).nl()
    m.emoji("timer").text(" Joined: ").italic(str(joined_at)[:10]).nl(2)
    
    m.emoji("wallet").text(" Wallet Balance: ").bold(f"Br {balance:,.2f}").nl()
    m.emoji("cart").text(" Total Spent: ").bold(f"Br {total_spent:,.2f}").nl()
    m.emoji("bag").text(" Products Bought: ").bold(f"{products_bought}").nl()
    m.emoji("referral").text(" Friends Invited: ").bold(f"{ref_count}").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("down").text(" Manage your wallet, order history, or referrals below:")
    return m.build()

async def send_profile(chat_id, user: dict, db_data: dict, keyboard: dict):
    """Send profile with photo if available, else plain text."""
    uid      = user.get("id")
    text, entities = build_profile(user, db_data)

    # Try to get profile photo
    photos = await get_user_profile_photos(uid)
    if photos:
        # Pick the largest size of the first photo
        best = max(photos[0], key=lambda s: s.get("width", 0))
        file_id = best.get("file_id")
        if file_id:
            # Send as photo with caption
            payload: dict = {
                "chat_id":          chat_id,
                "photo":            file_id,
                "caption":          text,
            }
            if entities:
                payload["caption_entities"] = entities
            if keyboard:
                payload["reply_markup"] = keyboard
            data = await api_call("sendPhoto", payload)
            if data.get("ok"):
                return
            # If sendPhoto fails with entity error, retry without entities
            if _is_entity_error(data):
                payload.pop("caption_entities", None)
                data = await api_call("sendPhoto", payload)
                if data.get("ok"):
                    return

    # Fallback: no photo or photo failed — send as plain text
    await send_msg(chat_id, text, entities, keyboard)


async def edit_profile(chat_id, message_id: int, user: dict,
                       db_data: dict, keyboard: dict):
    """Edit existing message — since we can't edit a photo back to text easily,
    just delete old and send fresh."""
    await api_call("deleteMessage", {
        "chat_id":    chat_id,
        "message_id": message_id,
    })
    await send_profile(chat_id, user, db_data, keyboard)

async def answer_cb(cq_id: str, text: str = "", alert: bool = False):
    return await api_call("answerCallbackQuery", {
        "callback_query_id": cq_id,
        "text":              text,
        "show_alert":        alert,
    })

_MEMBERSHIP_CACHE: dict[int, tuple[float, bool]] = {}

# ─── FORCE JOIN HELPER ────────────────────────────────────────
async def check_membership(user_id) -> bool:
    """
    Strictly returns True if user is a member/admin/creator/restricted of the channel.
    Uses 5-minute fast in-memory cache to eliminate redundant network latency.
    """
    if not user_id:
        return False
    if is_admin(user_id):
        return True

    now = time.time()
    cached = _MEMBERSHIP_CACHE.get(user_id)
    if cached and (now - cached[0] < 300) and cached[1] is True:
        return True

    target_chats = [FORCE_JOIN_CHANNEL_ID]
    if FORCE_JOIN_CHANNEL_LINK and "t.me/" in FORCE_JOIN_CHANNEL_LINK:
        ch_uname = "@" + FORCE_JOIN_CHANNEL_LINK.split("t.me/")[-1].strip("/")
        if ch_uname not in target_chats:
            target_chats.append(ch_uname)

    for ch in target_chats:
        data = await api_call("getChatMember", {
            "chat_id": ch,
            "user_id": user_id,
        })
        if data.get("ok"):
            status = data.get("result", {}).get("status", "")
            is_mem = status in ("member", "administrator", "creator", "restricted")
            _MEMBERSHIP_CACHE[user_id] = (now, is_mem)
            return is_mem
        else:
            desc = data.get("description", "")
            if "member list is inaccessible" in desc.lower() or "chat not found" in desc.lower():
                logger.warning(f"[force_join] Bot is not an Admin in channel {ch} ({desc}). Please ensure the bot is added as an Administrator to the channel!")
            elif "user not found" in desc.lower() or "participant_id_invalid" in desc.lower():
                _MEMBERSHIP_CACHE[user_id] = (now, False)
                return False

    return False

async def send_join_prompt(chat_id):
    """Send the force-join message asking user to join the channel."""
    custom = _load_custom_responses().get("join_prompt")
    if custom and custom.get("text"):
        ctx = {
            "channel_name": FORCE_JOIN_CHANNEL_NAME,
            "channel_link": FORCE_JOIN_CHANNEL_LINK,
        }
        join_text, join_ent = render_text_template(custom["text"], custom.get("entities"), ctx)
    else:
        m = Msg()
        m.emoji("lock").text(" ").bold("Channel Membership Required").nl()
        m.text("━━━━━━━━━━━━━━━━━━━━").nl()
        m.emoji("thunder").text(" To browse products and use ").bold("ET Market").text(", you must first join our official Telegram channel:").nl(2)
        m.emoji("channel").text(" Official Channel: ").bold(FORCE_JOIN_CHANNEL_NAME).nl()
        m.text("━━━━━━━━━━━━━━━━━━━━").nl()
        m.emoji("down").text(" Tap ").bold("Join Channel").text(" below, then tap ").bold("I've Joined").text(" to continue:")
        join_text, join_ent = m.build()
    
    await send_msg(
        chat_id,
        join_text,
        join_ent,
        keyboard=build_keyboard([
            [btn("📢 Join Channel", url=FORCE_JOIN_CHANNEL_LINK, emoji_key="channel", style="success")],
            [btn("✅ I've Joined — Verify", "check_join", emoji_key="check")],
        ])
    )

async def forward_photo_to_admins(file_id: str, order_id: str,
                                   order: dict, user: dict,
                                   ref_num: str = ""):
    """Forward payment screenshot or text details to all admins with approve/reject/verify buttons."""
    uname   = user.get("username", "")
    fname   = user.get("first_name", "User")
    uid     = user.get("id", "")
    uname_str = f"@{uname}" if uname else f"ID:{uid}"
    order_type_str = "💳 Wallet Top Up" if order.get("order_type") == "topup" else "🛒 Purchase"

    m = Msg()
    m.emoji("star").text(" ").bold(f"New Payment — Order #{order_id[:8].upper()}").nl(2)
    m.emoji("user").text(f" User: {fname} ({uname_str})\n")
    m.emoji("clipboard").text(f" Type: {order_type_str}\n")
    m.emoji("cart").text(f" Product: {order['cat_name']}\n")
    m.emoji("balance").text(f" Amount: Br {order['price']:.2f}\n")
    m.emoji("key").text(f" Ref: ").code(ref_num or 'N/A').nl()
    m.emoji("timer").text(f" Ordered: {order.get('created_at', 'N/A')}")
    caption, cap_entities = m.build()

    kb_rows = [
        [
            btn(f"✅ Approve", f"approve_{order_id}", emoji_key="check", style="success"),
            btn(f"❌ Reject",  f"reject_{order_id}", emoji_key="cross"),
        ]
    ]
    if ref_num:
        kb_rows.append([btn(f"⚡ Check Verify.ET ({ref_num[:12]})", f"vetcheck_{order_id}_{ref_num}", emoji_key="thunder", style="success")])
    else:
        kb_rows.append([btn("🔍 Enter Ref for Verify.ET", f"vetprompt_{order_id}", emoji_key="search")])

    kb = build_keyboard(kb_rows)
    for admin_id in ADMINS:
        try:
            if file_id:
                payload = {
                    "chat_id":      admin_id,
                    "photo":        file_id,
                    "caption":      caption,
                    "reply_markup": kb,
                }
                if cap_entities:
                    payload["caption_entities"] = cap_entities
                data = await api_call("sendPhoto", payload)
                if not data.get("ok") and cap_entities and _is_entity_error(data):
                    payload.pop("caption_entities", None)
                    await api_call("sendPhoto", payload)
            else:
                await send_msg(admin_id, caption, cap_entities, keyboard=kb)
        except Exception as ex:
            logger.warning(f"[forward_photo] Could not notify admin {admin_id}: {ex}")

# ─── TEXT / ENTITY BUILDERS ───────────────────────────────────

# ─── HIGHLY CAPABLE REGEX PRODUCT SEARCH ENGINE ──────────────
_awaiting_search: dict = {}  # { user_id: True }

def search_products(query: str, categories: dict) -> list:
    """
    Search products catalog using intelligent regex matching, keyword tokens, and scoring.
    """
    if not query or not query.strip():
        return []
    
    q = query.strip()
    results = []
    
    # 1. Try compiling as regex
    regex_compiled = None
    try:
        regex_compiled = re.compile(q, re.IGNORECASE)
    except re.error:
        pass
        
    q_lower = q.lower()
    q_tokens = [t for t in re.split(r'\s+', q_lower) if t]
    
    for cid, c in categories.items():
        if c.get("enabled", True) is False:
            continue
            
        name = c.get("name", "")
        desc = c.get("description", "")
        notes = c.get("notes", "")
        price = str(c.get("price", ""))
        combined_text = f"{name} {desc} {notes} {price} {cid}"
        
        score = 0
        matched = False
        
        # 1. Regex Match (High Priority)
        if regex_compiled:
            if regex_compiled.search(name):
                score += 100
                matched = True
            elif regex_compiled.search(desc) or regex_compiled.search(notes):
                score += 40
                matched = True
            elif regex_compiled.search(combined_text):
                score += 20
                matched = True
                
        # 2. Token / Substring Match (Fallback)
        if not matched:
            if q_lower in name.lower():
                score += 80
                matched = True
            elif all(token in combined_text.lower() for token in q_tokens):
                score += 50
                matched = True
            elif any(token in name.lower() for token in q_tokens if len(token) >= 3):
                score += 30
                matched = True
                
        if matched:
            results.append((score, c))
            
    # Sort by highest score first, then name
    results.sort(key=lambda x: (-x[0], x[1].get("name", "")))
    return [item[1] for item in results]

def build_search_prompt_screen():
    m = Msg()
    m.emoji("shop").text(" ").bold("Search Products Catalog").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.italic("Type any keyword, phrase, or regular expression (regex) to search across all products:").nl(2)
    m.bold("💡 Search Examples:").nl()
    m.text("• ").bold("Keywords: ").code("claude").text(", ").code("netflix").text(", ").code("vpn").text(", ").code("cursor").nl()
    m.text("• ").bold("Duration: ").code("12m").text(", ").code("1m").text(", ").code("30day").nl()
    m.text("• ").bold("Regex: ").code("gpt|gemini|claude").text(" or ").code("^c.*pro").nl(2)
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("down").text(" Send your search query below:")
    return m.build()

def build_search_results_screen(query: str, count: int):
    m = Msg()
    m.emoji("shop").text(" ").bold("Search Results").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.text("🔎 Query: ").code(query).nl()
    m.emoji("box").text(" Found: ").bold(f"{count} matching product{'s' if count != 1 else ''}").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("down").text(" Select a product below to view & buy:")
    return m.build()

def kb_search_results(products: list, stock_map: dict = None):
    stock_map = stock_map or {}
    rows = []
    for p in products[:15]:  # show top 15 matches
        cid = p["id"]
        stk = stock_map.get(cid, 0)
        c_emoji = p.get("emoji_char", "🛒")
        emoji_id = p.get("emoji_id")
        name = p["name"]
        
        if stk > 0:
            btn_text = f"{c_emoji} {name[:18]} — Br {p['price']:,.0f}"
            b_style = "success"
        else:
            btn_text = f"{c_emoji} {name[:16]} [Out of Stock]"
            b_style = None
            
        rows.append([btn(btn_text, f"cat_{cid}", style=b_style, custom_emoji_id=emoji_id)])
        
    rows.append([
        btn("🔍 Search Again", "shop_search"),
        btn("🛍️ All Products", "shop", emoji_key="shop")
    ])
    rows.append([btn("🏠 Main Menu", "back_main", emoji_key="back")])
    return build_keyboard(rows)


# ─── GIVEAWAY UI BUILDERS & SCREENS ───────────────────────────
def build_admin_giveaway_select(categories: dict):
    m = Msg()
    m.emoji("pop").text(" ").bold("Create Subscription Giveaway").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.italic("Select which subscription product you want to give away:").nl(2)
    m.emoji("down").text(" Choose a product from the list below:")
    return m.build()

def kb_admin_giveaway_select(categories: dict):
    rows = []
    for cid, c in categories.items():
        if c.get("enabled", True) is not False:
            c_emoji = c.get("emoji_char", "🛒")
            emoji_id = c.get("emoji_id")
            name = c.get("name", "")
            rows.append([btn(f"{c_emoji} {name[:22]} (Br {c['price']:,.0f})", f"admgw_sel_{cid}", custom_emoji_id=emoji_id)])
    rows.append([btn("Back to Admin Panel", "admin_panel", emoji_key="back")])
    return build_keyboard(rows)

def build_admin_giveaway_preview(cat: dict, gw_id: str):
    m = Msg()
    c_emoji = cat.get("emoji_char", "🎁")
    m.emoji("pop").text(" ").bold("Giveaway Setup & Preview").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.text("📦 ").bold("Prize: ").text(f"{c_emoji} {cat['name']}").nl()
    m.emoji("balance").text(" Value: ").bold(f"Br {cat['price']:,.2f}").nl()
    m.emoji("thunder").text(" Mode: ").bold("First-Come, First-Served (1 Winner)").nl()
    
    sp_id = cat.get("safwan_product_id")
    if sp_id:
        m.emoji("check").text(" Fulfillment: ").bold(f"Instant Auto-Delivery (Safwan #{sp_id})").nl()
    else:
        m.emoji("box").text(" Fulfillment: ").italic("Local Stock / Admin Delivery").nl()
        
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.italic("Choose where you want to launch and publish this giveaway:")
    return m.build()

def kb_admin_giveaway_preview(gw_id: str):
    return build_keyboard([
        [btn("🚀 Broadcast Giveaway to All Bot Users", f"admgw_broadcast_{gw_id}", emoji_key="share", style="success")],
        [btn("❌ Cancel", f"admgw_cancel_{gw_id}", emoji_key="cross")],
    ])

def build_giveaway_announcement(cat_name: str, emoji_icon: str = "🎁"):
    m = Msg()
    m.emoji("pop").text(" ").bold("FLASH SUBSCRIPTION GIVEAWAY!").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.text("📦 ").bold("Prize: ").text(f"{emoji_icon} {cat_name}").nl()
    m.emoji("thunder").text(" Mode: ").bold("First-Come, First-Served!").nl()
    m.emoji("star").text(" Winners: ").bold("Only 1 User Gets It").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("down").text(" Tap the claim button below as fast as you can:")
    return m.build()

def build_inbot_giveaway_announcement(cat_name: str, emoji_icon: str = "🎁"):
    return build_giveaway_announcement(cat_name, emoji_icon)

def kb_inbot_giveaway(gw_id: str):
    return build_keyboard([
        [btn("🎁 Claim Giveaway Now! ⚡", f"claim_gw_{gw_id}", emoji_key="pop", style="success")]
    ])

def build_welcome(user: dict = None, db_data: dict = None):
    # Resolve best display username / full name
    uname = ""
    if user:
        if user.get("username"):
            uname = f"@{user['username']}"
        elif user.get("first_name"):
            uname = str(user["first_name"]).strip()
            if user.get("last_name"):
                uname += f" {str(user['last_name']).strip()}"
                
    if not uname and db_data:
        if db_data.get("username"):
            uname = f"@{db_data['username']}"
        elif db_data.get("first_name"):
            uname = str(db_data["first_name"]).strip()

    if not uname and user and user.get("id"):
        uname = f"User #{user['id']}"
    elif not uname:
        uname = "Valued Customer"

    uid = str(user.get('id', '')) if user else ''
    raw_uname = user.get("username") if user else (db_data.get("username") if db_data else "")
    username_str = f"@{raw_uname}" if raw_uname else uname
    balance = float(db_data.get("balance", 0.0) if db_data else 0.0)
    
    custom = _load_custom_responses().get("welcome")
    if custom and custom.get("text"):
        ctx = {
            "user": uname,
            "name": uname,
            "username": username_str,
            "id": uid,
            "uid": uid,
            "balance": f"Br {balance:,.2f}",
            "channel_name": FORCE_JOIN_CHANNEL_NAME,
            "channel_link": FORCE_JOIN_CHANNEL_LINK,
        }
        return render_text_template(custom["text"], custom.get("entities"), ctx)

    m = Msg()
    m.emoji("wave").text(" ").bold("Welcome to ET Market!").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("bot").text(" Your trusted destination for ").bold("digital subscriptions").text(", ").bold("AI accounts").text(", and ").bold("cloud developer tools").text(".").nl(2)
    
    m.emoji("thunder").text("  • Instant 24/7 Automated Delivery").nl()
    m.emoji("telebirr").text("  • Instant Telebirr Automated Verification").nl(2)
    
    m.emoji("profile").text(" User: ").bold(uname)
    if uid:
        m.text(" ").code(f"({uid})")
    m.nl()
    m.emoji("balance").text(" Wallet Balance: ").bold(f"Br {balance:,.2f}").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("menu").text("  ").italic("Choose an option below to browse or manage:")
    return m.build()

def build_shop_paginated(total_products: int, page: int, total_pages: int):
    m = Msg()
    m.emoji("shop").text(" ").bold("ET Store — Products").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("thunder").text(" Instant 24/7 Automated Delivery").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("down").text(f" Select a product below (Page {page+1} of {total_pages}):")
    return m.build()

def kb_shop_paginated(cats: list | dict, counts: dict, page: int = 0, per_page: int = 8) -> tuple:
    """Build paginated keyboard for product catalog."""
    if isinstance(cats, dict):
        cat_list = list(cats.values())
    else:
        cat_list = list(cats)
    
    # Filter enabled
    cat_list = [c for c in cat_list if c.get("enabled", True)]
    
    total_items = len(cat_list)
    total_pages = max(1, math.ceil(total_items / per_page)) if total_items > 0 else 1
    page = max(0, min(page, total_pages - 1))
    
    start = page * per_page
    end = start + per_page
    page_items = cat_list[start:end]
    
    rows = []
    for cat in page_items:
        cid = cat["id"]
        cname = cat["name"]
        price = cat.get("price", 0.0)
        c_emoji = cat.get("emoji_char", "⚡")
        emoji_id = cat.get("emoji_id")
        stk = counts.get(cid, 0)
        stk_str = f" ({stk})" if stk > 0 else " (Out of Stock)"
        rows.append([btn(f"{c_emoji} {cname} — Br {price:,.0f}{stk_str}", f"cat_{cid}", custom_emoji_id=emoji_id)])
        
    # Navigation row
    nav_row = []
    if page > 0:
        nav_row.append(btn("Prev", f"shop_page_{page - 1}", emoji_key="back"))
    if page < total_pages - 1:
        nav_row.append(btn("Next", f"shop_page_{page + 1}", emoji_key="forward"))
    if nav_row:
        rows.append(nav_row)
        
    # Action row
    rows.append([
        btn("Wallet", "wallet", emoji_key="wallet"),
        btn("Home", "back_main", emoji_key="home"),
    ])
    
    return build_keyboard(rows), total_pages

def build_cat_detail(cat: dict, count: int, qty: int = 1) -> tuple:
    """Build product detail card with quantity and total price calculation."""
    description = cat.get("description", "").strip()
    desc_entities = cat.get("desc_entities", [])
    notes = cat.get("notes", "").strip()
    stock_status_text = f"{count} in Stock ✅" if count > 0 else "Out of Stock ❌"
    price = float(cat.get("price", 0.0))
    qty = max(1, min(qty, max(1, count)))
    total_price = price * qty

    m = Msg()
    cat_emoji = cat.get("emoji_char", "🛒")
    emoji_id = cat.get("emoji_id")
    if emoji_id:
        m.custom_emoji(cat_emoji, emoji_id).text(" ")
    else:
        m.text(f"{cat_emoji} ")
    m.bold(cat["name"]).nl(2)

    if description:
        m.emoji("clipboard").text(" ").bold("Description:").nl()
        if desc_entities:
            m.raw_with_entities(description, desc_entities).nl(2)
        else:
            m.text(description).nl(2)

    if notes:
        m.emoji("thunder").text(" ").bold("Warranty & Notes:").nl()
        m.text(notes).nl(2)

    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("balance").text(" Unit Price: ").bold(f"Br {price:,.2f}").nl()
    m.emoji("box").text(f" Stock: {stock_status_text}").nl()
    if count > 0:
        m.emoji("cart").text(" Selected Quantity: ").bold(f"{qty} unit{'s' if qty > 1 else ''}").nl()
        m.emoji("wallet").text(" Total Price: ").bold(f"Br {total_price:,.2f}").nl()
        m.text("━━━━━━━━━━━━━━━━━━━━").nl()
        m.emoji("down").text(" Adjust quantity or tap Checkout below:")
    else:
        m.text("━━━━━━━━━━━━━━━━━━━━").nl()
        m.emoji("timer").text(" Out of stock. Check back soon!")

    return m.build()

def kb_cat_detail(cat_id: str, count: int, qty: int = 1) -> dict:
    """Build keyboard with interactive quantity stepper, presets, custom input, and checkout."""
    if count <= 0:
        return build_keyboard([
            [btn("Out of Stock", "noop", emoji_key="cross")],
            [btn("Back to Products", "shop", emoji_key="back"),
             btn("Main Menu", "back_main", emoji_key="home")],
        ])
    
    qty = max(1, min(qty, count))
    cats = _load_categories()
    cat = cats.get(cat_id, {})
    price = float(cat.get("price", 0.0))
    total_price = price * qty
    
    rows = []
    # Stepper row: [ ➖ 1 ] [ 🔢 Qty: N ] [ ➕ 1 ]
    prev_qty = max(1, qty - 1)
    next_qty = min(count, qty + 1)
    stepper = [
        btn("➖ 1", f"qty_set_{cat_id}_{prev_qty}", emoji_key="back"),
        btn(f"🔢 Qty: {qty}", "noop"),
        btn("➕ 1", f"qty_set_{cat_id}_{next_qty}", emoji_key="forward"),
    ]
    rows.append(stepper)
    
    # Preset row: [ 1x ] [ 2x ] [ 3x ] [ 5x ] [ 10x ] (only show presets that <= count)
    preset_vals = [1, 2, 3, 5, 10]
    preset_row = []
    for p in preset_vals:
        if p <= count:
            label = f"[{p}x]" if p == qty else f"{p}x"
            preset_row.append(btn(label, f"qty_set_{cat_id}_{p}"))
    if preset_row:
        rows.append(preset_row)
        
    # Custom input button
    rows.append([btn("Enter Custom Quantity", f"qty_custom_{cat_id}", emoji_key="other")])
    
    # Checkout button
    rows.append([
        btn(f"Checkout {qty}x  —  Br {total_price:,.0f}", f"buy_{cat_id}_{qty}", emoji_key="cart", style="success")
    ])
    
    # Navigation
    rows.append([
        btn("Back to Products", "shop", emoji_key="back"),
        btn("Main Menu", "back_main", emoji_key="home"),
    ])
    
    return build_keyboard(rows)

async def send_welcome_screen(chat_id, user):
    """Send fresh welcome screen with live user balance and resolved username."""
    user_id = user.get("id") if isinstance(user, dict) else user
    db_data = await db_get_user(user_id) or {}
    merged_user = dict(db_data)
    if isinstance(user, dict):
        merged_user.update({k: v for k, v in user.items() if v is not None})
    
    balance = float(merged_user.get("balance", 0.0))
    t, ent = build_welcome(merged_user, merged_user)
    kb = kb_main(user_id, balance)
    await send_msg(chat_id, t, ent, kb)


def kb_main(user_id=None, balance: float = 0.0):
    bal_str = f"Br {balance:,.2f}"
    rows = [
        [btn("🛍️ Browse Products / Shop", "shop", emoji_key="shop", style="success")],
        [btn(f"💳 Wallet ({bal_str})", "wallet", emoji_key="wallet"),
         btn("👤 Profile", "profile", emoji_key="profile")],
        [btn("📜 Order History", "history", emoji_key="clipboard"),
         btn("📊 Bot Logs", url=LOG_CHANNEL_LINK, emoji_key="channel")],
        [btn("👥 Referral", "referral", emoji_key="referral"),
         btn("🎧 Support", url=SUPPORT_LINK, emoji_key="support")],
        [btn("📢 Channel", url=FORCE_JOIN_CHANNEL_LINK, emoji_key="channel")],
    ]
    if user_id and is_admin(user_id):
        rows.append([btn("👑 Admin Control Panel", "admin_panel", emoji_key="other", style="success")])
    else:
        rows.append([btn("👨‍💻 Developed By @kidanewold777", url=DEVELOPER_LINK, emoji_key="other")])
    return build_keyboard(rows)

def build_support_screen():
    custom = _load_custom_responses().get("support")
    if custom and custom.get("text"):
        ctx = {
            "support_link": SUPPORT_LINK,
            "channel_link": FORCE_JOIN_CHANNEL_LINK,
            "channel_name": FORCE_JOIN_CHANNEL_NAME,
        }
        return render_text_template(custom["text"], custom.get("entities"), ctx)

    m = Msg()
    m.emoji("support").text(" ").bold("Customer Support & Assistance").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("thunder").text(" Need assistance with an order, payment, or digital account?").nl(2)
    m.emoji("check").text(" Our support team is ready to assist you 24/7.").nl(2)
    m.emoji("user").text(" Official Support: ").bold("@et_market_place").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("down").text(" Tap the button below to message our support directly:")
    return m.build()

def build_referral_screen(user: dict = None, db_data: dict = None):
    custom = _load_custom_responses().get("referral")
    kb = build_keyboard([
        [btn("📢 Join Channel for Updates", url=FORCE_JOIN_CHANNEL_LINK, emoji_key="channel", style="success")],
        [btn("🏠 Main Menu", "back_main", emoji_key="back")],
    ])
    if custom and custom.get("text"):
        uid = str(user.get('id', '')) if user else (str(db_data.get('user_id', '')) if db_data else '')
        uname = user.get('first_name', '') if user else ''
        ctx = {
            "user": uname,
            "id": uid,
            "channel_link": FORCE_JOIN_CHANNEL_LINK,
            "channel_name": FORCE_JOIN_CHANNEL_NAME,
        }
        t, ent = render_text_template(custom["text"], custom.get("entities"), ctx)
        return (t, ent), kb

    m = Msg()
    m.emoji("referral").text(" ").bold("ET Referral & Rewards").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("timer").text(" ").bold("Coming Soon!").nl(2)
    m.text("Our automated referral & rewards program is currently under development.").nl(2)
    m.emoji("thunder").text(" Soon, you will be able to invite your friends and earn instant cash rewards, free account credits, and exclusive discounts on every purchase!").nl(2)
    m.emoji("star").text(" Stay tuned to our official channel for the launch announcement!").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━")
    return m.build(), kb

def build_terms():
    custom = _load_custom_responses().get("terms")
    if custom and custom.get("text"):
        ctx = {
            "support_link": SUPPORT_LINK,
            "channel_name": FORCE_JOIN_CHANNEL_NAME,
        }
        return render_text_template(custom["text"], custom.get("entities"), ctx)

    m = Msg()
    m.emoji("clipboard").text(" ").bold("Terms & Conditions").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.text("Welcome to ").bold("ET Market").text(". By using our bot and services, you agree to the following terms:").nl(2)
    m.emoji("check").text(" ").bold("1. Order Confirmation:").text(" Please check product details before ordering.").nl()
    m.emoji("telebirr").text(" ").bold("2. Payment:").text(" Pay only via displayed accounts & confirm with reference.").nl()
    m.emoji("thunder").text(" ").bold("3. Delivery:").text(" Instant auto-delivery for stocked items; manual activation when required.").nl()
    m.emoji("shield").text(" ").bold("4. Warranty & Refunds:").text(" Covered under product warranty terms; refunds available if item cannot be delivered.").nl()
    m.emoji("support").text(" ").bold("5. Support:").text(" 24/7 assistance available for any issues.").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("star").text(" Tap ").bold("I Agree").text(" below to continue using the bot:")
    return m.build()

def build_bot_logs(filter_type: str = "all", page: int = 0, per_page: int = 5, viewer_id=None):
    """Build live public order logs screen with real-time order statuses, summary metrics, and pagination."""
    all_orders = _load_orders()
    total_orders = len(all_orders)
    completed_count = sum(1 for o in all_orders.values() if o.get("status") in ("approved", "delivered"))
    pending_count = sum(1 for o in all_orders.values() if o.get("status") in ("pending_payment", "pending_approval", "awaiting_delivery"))
    cancelled_count = sum(1 for o in all_orders.values() if o.get("status") in ("cancelled", "rejected"))
    total_volume = sum(float(o.get("price", 0.0)) for o in all_orders.values() if o.get("status") in ("approved", "delivered"))

    counts_map = {
        "all": total_orders,
        "completed": completed_count,
        "pending": pending_count,
        "cancelled": cancelled_count,
    }

    # Filter selection
    if filter_type == "completed":
        filtered = [o for o in all_orders.values() if o.get("status") in ("approved", "delivered")]
    elif filter_type == "pending":
        filtered = [o for o in all_orders.values() if o.get("status") in ("pending_payment", "pending_approval", "awaiting_delivery")]
    elif filter_type == "cancelled":
        filtered = [o for o in all_orders.values() if o.get("status") in ("cancelled", "rejected")]
    else:
        filter_type = "all"
        filtered = list(all_orders.values())

    # Sort newest orders first
    filtered.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    total_filtered = len(filtered)
    total_pages = max(1, math.ceil(total_filtered / per_page)) if total_filtered > 0 else 1
    page = max(0, min(page, total_pages - 1))

    start = page * per_page
    end = start + per_page
    page_items = filtered[start:end]

    # Check custom template
    custom = _load_custom_responses().get("bot_logs")
    header_text = None
    header_ent = None
    if custom and custom.get("text"):
        ctx = {
            "total_orders": f"{total_orders:,}",
            "completed_orders": f"{completed_count:,}",
            "pending_orders": f"{pending_count:,}",
            "cancelled_orders": f"{cancelled_count:,}",
            "total_volume": f"Br {total_volume:,.2f}",
            "channel_link": FORCE_JOIN_CHANNEL_LINK,
        }
        header_text, header_ent = render_text_template(custom["text"], custom.get("entities"), ctx)

    m = Msg()
    if header_text:
        m.raw_with_entities(header_text, header_ent).nl(2)
    else:
        m.emoji("clipboard").text(" ").bold("ET Bot — Live Order Logs").nl()
        m.text("━━━━━━━━━━━━━━━━━━━━").nl()
        m.emoji("thunder").text(" Live transparent audit & real-time order status tracking:").nl(2)
        m.emoji("box").text(" Total Orders: ").bold(f"{total_orders:,}").text("  •  ")
        m.emoji("check").text(" Completed: ").bold(f"{completed_count:,}").nl()
        m.emoji("timer").text(" Pending: ").bold(f"{pending_count:,}").text("  •  ")
        m.emoji("cross").text(" Cancelled: ").bold(f"{cancelled_count:,}").nl()
        m.emoji("balance").text(" Total Volume: ").bold(f"Br {total_volume:,.2f} ETB").nl()
        m.emoji("channel").text(" Official Logs Group: ").bold("https://t.me/+2RORZ17pHqNiYzM0").nl()
        m.text("━━━━━━━━━━━━━━━━━━━━").nl()

    filter_title = {
        "all": "All Orders",
        "completed": "Completed & Delivered Orders",
        "pending": "Pending & In-Review Orders",
        "cancelled": "Cancelled Orders",
    }.get(filter_type, "All Orders")

    m.emoji("down").text(f" {filter_title} (Page {page + 1} of {total_pages}):").nl(2)

    if not page_items:
        m.emoji("box").text(" ").italic("No orders found in this category.").nl()
    else:
        for i, o in enumerate(page_items):
            status = o.get("status", "pending_payment")
            if status in ("approved", "delivered"):
                status_emoji = "check"
                status_label = "Completed / Delivered"
            elif status == "pending_approval":
                status_emoji = "timer"
                status_label = "Payment Under Review"
            elif status == "awaiting_delivery":
                status_emoji = "box"
                status_label = "Awaiting Delivery"
            elif status in ("cancelled", "rejected"):
                status_emoji = "cross"
                status_label = "Cancelled"
            else:
                status_emoji = "timer"
                status_label = "Awaiting Payment"

            oid = o.get("order_id", "")[:8].upper()
            cname = o.get("cat_name", "Product")
            price = float(o.get("price", 0.0))
            qty = o.get("quantity", 1)
            created = o.get("created_at", "")
            u_id = str(o.get("user_id", ""))

            # Anonymize user ID for security and privacy
            if viewer_id and str(viewer_id) == u_id:
                user_label = "You"
            elif len(u_id) > 4:
                user_label = f"User #***{u_id[-4:]}"
            elif u_id:
                user_label = f"User #{u_id}"
            else:
                user_label = "Customer"

            qty_str = f" (x{qty})" if qty and int(qty) > 1 else ""

            m.emoji(status_emoji).text(f" Order #{oid}  •  ").bold(status_label).nl()
            m.emoji("shop").text(f" {cname}{qty_str}").nl()
            m.emoji("balance").text(f" Br {price:,.2f}").text("  •  ").emoji("user").text(f" {user_label}").nl()
            if created:
                m.emoji("clock").text(f" {created}").nl()
            if i < len(page_items) - 1:
                m.nl()

    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.italic("💡 Order statuses update in real time with every transaction.")
    return m.build(), total_pages, counts_map


def kb_bot_logs(filter_type: str = "all", page: int = 0, total_pages: int = 1, counts_map: dict = None) -> dict:
    """Build interactive filter tabs and navigation buttons for Bot Logs."""
    if counts_map is None:
        all_orders = _load_orders()
        counts_map = {
            "all": len(all_orders),
            "completed": sum(1 for o in all_orders.values() if o.get("status") in ("approved", "delivered")),
            "pending": sum(1 for o in all_orders.values() if o.get("status") in ("pending_payment", "pending_approval", "awaiting_delivery")),
            "cancelled": sum(1 for o in all_orders.values() if o.get("status") in ("cancelled", "rejected")),
        }

    # Filter tab indicators
    all_label = f"{'🔘 ' if filter_type == 'all' else '⚪ '}All ({counts_map['all']})"
    comp_label = f"{'🔘 ' if filter_type == 'completed' else '🟢 '}Done ({counts_map['completed']})"
    pend_label = f"{'🔘 ' if filter_type == 'pending' else '⏳ '}Pending ({counts_map['pending']})"
    canc_label = f"{'🔘 ' if filter_type == 'cancelled' else '🔴 '}Cancelled ({counts_map['cancelled']})"

    rows = [
        [
            btn(all_label, f"botlogs_all_{page if filter_type == 'all' else 0}"),
            btn(comp_label, f"botlogs_completed_{page if filter_type == 'completed' else 0}"),
        ],
        [
            btn(pend_label, f"botlogs_pending_{page if filter_type == 'pending' else 0}"),
            btn(canc_label, f"botlogs_cancelled_{page if filter_type == 'cancelled' else 0}"),
        ]
    ]

    # Pagination navigation
    nav_row = []
    if page > 0:
        nav_row.append(btn("Prev", f"botlogs_{filter_type}_{page - 1}", emoji_key="back"))
    if total_pages > 1:
        nav_row.append(btn(f"{page + 1}/{total_pages}", f"botlogs_refresh_{filter_type}_{page}", emoji_key="document"))
    if page < total_pages - 1:
        nav_row.append(btn("Next", f"botlogs_{filter_type}_{page + 1}", emoji_key="forward"))
    if nav_row:
        rows.append(nav_row)

    # Action row
    action_row = [
        btn("Refresh Logs", f"botlogs_refresh_{filter_type}_{page}", emoji_key="other"),
    ]
    if LOG_CHANNEL_LINK:
        action_row.append(btn("Open Logs Group", url=LOG_CHANNEL_LINK, emoji_key="channel"))
    elif FORCE_JOIN_CHANNEL_LINK:
        action_row.append(btn("📢 Channel", url=FORCE_JOIN_CHANNEL_LINK, emoji_key="channel"))
    rows.append(action_row)

    # Return to home
    rows.append([btn("🏠 Main Menu", "back_main", emoji_key="back")])

    return build_keyboard(rows)


def build_dev_screen():
    """Build high-end, attractive developer portfolio and credit screen."""
    custom = _load_custom_responses().get("dev_info")
    if custom and custom.get("text"):
        ctx = {
            "dev_link": DEVELOPER_LINK,
            "channel_link": FORCE_JOIN_CHANNEL_LINK,
            "channel_name": FORCE_JOIN_CHANNEL_NAME,
        }
        return render_text_template(custom["text"], custom.get("entities"), ctx)

    m = Msg()
    m.emoji("diamond").text(" ").bold("Developer & Engineering Profile").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("star").text(" Lead Architect: ").bold("@kidanewold777").nl()
    m.emoji("thunder").text(" System: ").bold("ET Market Engine 2.0").nl()
    m.emoji("check").text(" Status: ").bold("Verified Official Bot Developer ✅").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("bot").text(" ").bold("Core Engineering & Innovations:").nl()
    m.emoji("thunder").text(" • ").bold("Instant 24/7 Automated Delivery System").nl()
    m.emoji("telebirr").text(" • ").bold("Verify.ET Automated Banking & Mobile Money").nl()
    m.emoji("box").text(" • ").bold("Real-time Live Stock Sync & Multi-Store APIs").nl()
    m.emoji("sparkles").text(" • ").bold("Custom Telegram Premium Animated UI Engine").nl(2)
    m.emoji("shield").text(" ").bold("Custom Development & Inquiries:").nl()
    m.text("Need a custom Telegram bot, automated e-commerce store, payment gateway integration, or AI assistant? Get in touch directly!").nl(2)
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("support").text(" Tap the button below to message ").bold("@kidanewold777").text(":")
    return m.build()


def build_menu():
    m = Msg()
    m.emoji("menu").text(" ").bold("Main Menu").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.text("Select an option below to browse products, manage wallet, or view your orders:")
    return m.build()

def build_ping():
    m = Msg()
    m.emoji("thunder").text(" ").bold("Pong!").nl()
    m.emoji("check").text(" ET Market Bot is online and running smoothly.")
    return m.build()

def build_help():
    custom = _load_custom_responses().get("help")
    if custom and custom.get("text"):
        ctx = {
            "support_link": SUPPORT_LINK,
            "channel_name": FORCE_JOIN_CHANNEL_NAME,
            "channel_link": FORCE_JOIN_CHANNEL_LINK,
        }
        return render_text_template(custom["text"], custom.get("entities"), ctx)

    m = Msg()
    m.emoji("support").text(" ").bold("Help & Bot Commands").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("bot").text(" Here are the commands you can use in ").bold("ET Market").text(":").nl(2)
    m.emoji("shop").text(" • ").bold("/start").text(" — Open main menu / shop\n")
    m.emoji("cart").text(" • ").bold("/shop").text(" — Browse available digital products\n")
    m.emoji("wallet").text(" • ").bold("/wallet").text(" — Check balance & deposit funds\n")
    m.emoji("clipboard").text(" • ").bold("/history").text(" — View your recent orders\n")
    m.emoji("document").text(" • ").bold("/logs").text(" — Live bot order logs & status\n")
    m.emoji("referral").text(" • ").bold("/referral").text(" — Referral & rewards program\n")
    m.emoji("support").text(" • ").bold("/support").text(" — Contact customer support\n")
    m.emoji("channel").text(" • ").bold("/channel").text(" — Official updates channel\n\n")
    m.emoji("star").text(" Need help with an active order? Message ").bold("@et_market_place")
    return m.build()

def build_test():
    m = Msg()
    m.emoji("wave").text(" ").bold("System Operational Test").nl()
    m.emoji("check").text(" All systems normal.")
    return m.build()

def build_admin_custom_texts_menu():
    m = Msg()
    m.emoji("other").text(" ").bold("Customize Bot Messages & Screens").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.text("Select any message below to customize its text, formatting, and premium emojis.\n\n")
    
    customs = _load_custom_responses()
    for key, info in RESPONSE_TEMPLATES.items():
        status = "🟢 Custom" if key in customs else "⚪ Default"
        m.text(f"• {info['name']}: {status}\n")
    m.nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.italic("💡 Tap any response button below to edit or reset:")
    return m.build()

def kb_admin_custom_texts():
    rows = []
    customs = _load_custom_responses()
    items = list(RESPONSE_TEMPLATES.items())
    for i in range(0, len(items), 2):
        pair = items[i:i+2]
        row = []
        for key, info in pair:
            is_custom = key in customs
            badge = "✏️ " if is_custom else "➕ "
            row.append(btn(f"{badge}{info['name']}", f"admtxt_edit_{key}"))
        rows.append(row)
    
    if customs:
        rows.append([btn("🔄 Reset All to Defaults", "admtxt_reset_all", emoji_key="cross", style="danger")])
    rows.append([btn("Back to Admin Panel", "admin_panel", emoji_key="back")])
    return build_keyboard(rows)

def build_admin_edit_template_prompt(key: str):
    info = RESPONSE_TEMPLATES.get(key, {"name": key, "placeholders": []})
    custom = _load_custom_responses().get(key)
    is_custom = bool(custom)
    
    m = Msg()
    m.emoji("other").text(" ").bold(f"Edit: {info.get('name', key)}").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.text(f"Description: {info.get('desc', '')}\n\n")
    
    tags_str = ", ".join(f"`{p}`" for p in info.get("placeholders", []))
    m.emoji("thunder").text(f" Available Placeholders: {tags_str}\n\n")
    
    if is_custom:
        m.text("Current Status: ").bold("🟢 Customized").nl(2)
        m.bold("Current Custom Text:").nl()
        m.text(custom["text"][:300] + ("..." if len(custom["text"]) > 300 else "")).nl(2)
    else:
        m.text("Current Status: ").bold("⚪ Default Built-in").nl(2)
        
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.italic("📝 Send your new message in this chat (supports bold, italics, links, and premium emojis).\n\nOr click a button below:")
    
    kb_rows = []
    if is_custom:
        kb_rows.append([btn("🔄 Reset to Default", f"admtxt_reset_{key}", emoji_key="back")])
    kb_rows.append([btn("Back to Messages Menu", "admin_custom_texts", emoji_key="back")])
    
    return m.build(), build_keyboard(kb_rows)

async def build_admin_dashboard():
    users = _load_db()
    total_users = len(users)
    orders = _load_orders()
    total_sales = sum(1 for o in orders.values() if o.get("status") in ("delivered", "approved"))
    total_revenue = sum(float(o.get("price", 0)) for o in orders.values() if o.get("status") in ("delivered", "approved"))
    pending_orders = sum(1 for o in orders.values() if o.get("status") in ("pending_approval", "pending_payment", "awaiting_delivery"))
    cats = _load_categories()
    total_products = len(cats)
    
    m = Msg()
    m.emoji("bot").text(" ").bold("Admin Control Panel").nl(2)
    m.emoji("balance").text(" ").bold("Store Overview & Statistics:").nl()
    m.emoji("user").text("  • Customers: ").bold(f"{total_users}").nl()
    m.emoji("wallet").text("  • Total Revenue: ").bold(f"Br {total_revenue:,.2f}").nl()
    m.emoji("cart").text("  • Products Sold: ").bold(f"{total_sales}").nl()
    m.emoji("box").text("  • Active Products: ").bold(f"{total_products}").nl()
    m.emoji("timer").text("  • Pending Approvals: ").bold(f"{pending_orders}").nl(2)
    m.italic("Choose an option below to manage the store:")
    return m.build()

async def build_admin_panel():
    return await build_admin_dashboard()

def kb_admin_panel():
    return build_keyboard([
        [btn("📦 Manage Products", "admin_products", emoji_key="shop", style="success"),
         btn("➕ Add Product", "admin_addcat", emoji_key="cart")],
        [btn("🔄 Sync Safwan Stock", "admin_sync_safwan", emoji_key="thunder"),
         btn("🎁 Create Giveaway", "admin_giveaways", emoji_key="pop", style="success")],
        [btn("✏️ Edit Bot Messages", "admin_custom_texts", emoji_key="other", style="success"),
         btn("📢 Broadcast Message", "admin_broadcast", emoji_key="channel")],
        [btn("👥 User Management", "admin_users", emoji_key="profile"),
         btn("⏳ Pending Orders", "admin_pending", emoji_key="timer")],
        [btn("⚙️ Bot Settings", "admin_settings", emoji_key="other")],
        [btn("🏠 Main Menu", "back_main", emoji_key="back")],
    ])

async def build_admin_settings_screen():
    m = Msg()
    m.emoji("other").text(" ").bold("Bot Configuration & Settings").nl(2)
    
    vet_status = f"`{VERIFY_ET_API_KEY[:6]}...{VERIFY_ET_API_KEY[-4:]}` 🟢" if VERIFY_ET_API_KEY else "❌ Not Set (Manual Review)"
    m.emoji("key").text(f"• Verify.ET API Key: {vet_status}\n")

    # Query SafwanTiger balance
    try:
        st_bal = await safwan_get_balance()
        if isinstance(st_bal, dict) and st_bal.get("ok"):
            st_status = f"${st_bal.get('balance', 0.0):.2f} {st_bal.get('currency', 'USDT')} 🟢"
        elif isinstance(st_bal, (int, float)):
            st_status = f"${st_bal:.2f} USDT 🟢"
        elif isinstance(st_bal, dict):
            st_status = f"❌ Error: {st_bal.get('error', 'Not connected')}"
        else:
            st_status = "❌ Not connected"
    except Exception as ex:
        st_status = f"❌ Error: {ex}"
    m.emoji("thunder").text(f"• SafwanTiger Auto-Delivery: {st_status}\n")

    m.emoji("channel").text(f"• Sales Log Channel: `{LOG_CHANNEL_ID}`\n")
    m.emoji("channel").text(f"• Force Join Channel ID: `{FORCE_JOIN_CHANNEL_ID}`\n")
    m.emoji("link").text(f"• Force Join Link: {FORCE_JOIN_CHANNEL_LINK}\n\n")
    
    m.emoji("telebirr").text(f"• Telebirr: {PAYMENT_NAME} (`{PAYMENT_ACCOUNT}`)\n")
    m.emoji("cbe").text(f"• CBE Birr: {CBEBIRR_NAME} (`{CBEBIRR_ACCOUNT}`)\n")
    m.emoji("cbe").text(f"• CBE Bank: {CBE_NAME} (`{CBE_ACCOUNT}`)\n\n")
    
    admins_str = ", ".join(f"`{a}`" for a in ADMINS)
    m.emoji("user").text(f"• Admin User IDs: {admins_str}\n\n")
    m.italic("Tap any button below to edit its value and save to .env:")
    return m.build()

def kb_admin_settings():
    return build_keyboard([
        [btn("🔑 Edit Verify.ET Key", "admset_vet_key"),
         btn("⚡ Edit Safwan API Key", "admset_safwan_key")],
        [btn("📢 Edit Log Channel",  "admset_log_ch"),
         btn("🔒 Edit Force Join ID", "admset_fj_id")],
        [btn("🔗 Edit Force Join Link", "admset_fj_link"),
         btn("👥 Add/Edit Admins",    "admset_admins")],
        [btn("💙 Edit Telebirr Info", "admset_telebirr"),
         btn("🏦 Edit CBE Birr Info", "admset_cbebirr")],
        [btn("🏛 Edit CBE Bank Info", "admset_cbe")],
        [btn("Back to Admin Panel", "admin_panel", emoji_key="back")],
    ])

def kb_admin_products(cats: dict, counts: dict) -> dict:
    """Build keyboard for product management list."""
    rows = []
    for cid, cat in cats.items():
        name = cat.get("name", cid)
        price = float(cat.get("price", 0.0))
        enabled = cat.get("enabled", True) is not False
        status_icon = "🟢" if enabled else "🔴"
        cnt = counts.get(cid, 0)
        c_emoji = cat.get("emoji_char", "📦")
        emoji_id = cat.get("emoji_id")
        label = f"{status_icon} {c_emoji} {name} (Br {price:,.0f} | Stk: {cnt})"
        rows.append([btn(label, f"admin_manage_cat_{cid}", custom_emoji_id=emoji_id)])
    
    rows.append([
        btn("➕ Add Product", "admin_addcat", emoji_key="cart", style="success"),
        btn("🔄 Sync Safwan", "admin_sync_safwan", emoji_key="thunder"),
    ])
    rows.append([btn("Back to Admin Panel", "admin_panel", emoji_key="back")])
    return build_keyboard(rows)

def build_admin_product_card(cat: dict, count: int) -> tuple:
    """Build product detail card for admin."""
    cid = cat.get("id", "")
    name = cat.get("name", "Unnamed Product")
    price = float(cat.get("price", 0.0))
    enabled = cat.get("enabled", True) is not False
    cat_type = cat.get("cat_type", "id_pass")
    safwan_id = cat.get("safwan_product_id")
    desc = cat.get("description", "No description set.")
    desc_entities = cat.get("desc_entities", [])
    notes = cat.get("notes", "None")
    cat_emoji = cat.get("emoji_char", "📦")
    emoji_id = cat.get("emoji_id")

    m = Msg()
    if emoji_id:
        m.custom_emoji(cat_emoji, emoji_id).text(" ")
    else:
        m.text(f"{cat_emoji} ")
    m.bold(f"Product Details: {name}").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("key").text(" • ID: ").code(cid).nl()
    m.emoji("check" if enabled else "cross").text(" • Status: ").bold("Active in Store" if enabled else "Hidden from Store").nl()
    m.emoji("balance").text(" • Price: ").bold(f"Br {price:,.2f}").nl()
    m.emoji("box").text(" • Stock Available: ").bold(f"{count} units").nl()
    m.emoji("link" if cat_type == "link" else "key").text(" • Delivery Type: ").italic(cat_type).nl()
    if emoji_id:
        m.emoji("star").text(" • Custom Emoji ID: ").code(str(emoji_id)).nl()
    if safwan_id:
        m.emoji("thunder").text(" • Supplier ID: ").code(str(safwan_id)).text(" (Automated)").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("clipboard").text(" ").bold("Description:").nl()
    if desc_entities:
        m.raw_with_entities(desc, desc_entities).nl(2)
    else:
        m.italic(desc[:300]).nl(2)
    m.bold("Warranty / Notes:").nl()
    m.italic(notes[:200]).nl()
    return m.build()

def kb_admin_product_detail(cid: str, cat: dict = None) -> dict:
    """Build action keyboard for single product management."""
    return build_keyboard([
        [btn("🔄 Toggle ON/OFF", f"admin_toggle_{cid}", emoji_key="other")],
        [btn("✏️ Edit Name", f"admin_editname_{cid}", emoji_key="other"),
         btn("🎨 Edit Emoji / Icon", f"admin_editemoji_{cid}", emoji_key="star")],
        [btn("💰 Edit Price", f"admin_editprice_{cid}", emoji_key="wallet"),
         btn("📦 Edit Stock", f"admin_editstock_{cid}", emoji_key="cart")],
        [btn("🗑 Delete Product", f"admin_delete_{cid}", emoji_key="cross")],
        [btn("Back to Products", "admin_products", emoji_key="back")],
    ])

async def build_admin_payment_info():
    return await build_admin_settings_screen()

def build_admin_pending_orders():
    orders = _load_orders()
    pending = [o for o in orders.values() if o.get("status") in ("pending_payment", "pending_approval", "awaiting_delivery")]
    m = Msg()
    m.emoji("timer").text(" ").bold("Pending Orders & Deliveries").nl(2)
    if not pending:
        m.emoji("pop").text(" ").bold("No pending orders!").text(" All deliveries and payments are up to date.")
    else:
        m.text(f"Found {len(pending)} pending order(s):\n\n")
        for o in pending[:8]:
            if o.get("status") == "awaiting_delivery":
                st = "Awaiting Link Delivery"
            elif o.get("status") == "pending_approval":
                st = "Awaiting Review"
            else:
                st = "Awaiting Payment"
            m.emoji("cart").text(f" • Order #{o['order_id'][:8].upper()} — ").bold(o['cat_name']).nl()
            m.emoji("balance").text(f"   Price: Br {o['price']:.2f} | User: ").code(str(o['user_id'])).nl()
            m.emoji("status").text(f"   Status: {st}\n\n")
    return m.build(), pending

# ─── VERIFY.ET AUTOMATED PAYMENT ENGINE ───────────────────────
def extract_cbe_reference(text: str) -> str | None:
    """Extract CBE transaction reference number (e.g. FT240819XXXX) from SMS or input."""
    if not text:
        return None
    match = re.search(r'\b(FT[0-9A-Za-z]{8,14})\b', text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    cleaned = text.strip()
    if 8 <= len(cleaned) <= 22 and cleaned.isalnum():
        return cleaned.upper()
    return None

def extract_cbebirr_reference(text: str) -> str | None:
    """Extract CBE Birr transaction ID or receipt number from input or SMS."""
    if not text:
        return None
    # 1. Keywords: Transaction/Receipt/Ref/ደረሰኝ/ቁጥር/Trans ID
    m = re.search(r'(?:transaction|txn|ref(?:erence)?|receipt|trans(?:\.?\s*id)?|ደረሰኝ|ቁጥር)\s*(?:no\.?|id|number)?\s*[:=\s]\s*([A-Za-z0-9]{4,30})', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # 2. REC... or CB... or TRA... or FT...
    m = re.search(r'\b((?:REC|CB|TRA|FT)[0-9A-Za-z]{4,25})\b', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # 3. 6-25 digit numeric or alphanumeric transaction codes
    m = re.search(r'\b([A-Z0-9]{6,25})\b', text)
    if m:
        return m.group(1).upper()
    # 4. Fallback if user just entered raw code
    cleaned = re.sub(r'[^A-Za-z0-9]', '', text.strip())
    if 4 <= len(cleaned) <= 30:
        return cleaned.upper()
    return None

def extract_telebirr_reference(text: str) -> str | None:
    """Extract Telebirr transaction ID from input or SMS."""
    if not text:
        return None
    # 1. Look for explicit keywords: Transaction No/ID/Ref/Number/Receipt/ደረሰኝ/ቁጥር
    m = re.search(r'(?:transaction|txn|ref(?:erence)?|receipt|ደረሰኝ|ቁጥር)\s*(?:no\.?|id|number)?\s*[:=\s]\s*([A-Za-z0-9]{4,30})', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # 2. Look for TRA... code
    m = re.search(r'\b(TRA[0-9A-Za-z]{4,25})\b', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # 3. Look for 6-25 digit numeric or alphanumeric transaction codes
    m = re.search(r'\b([A-Z0-9]{6,25})\b', text)
    if m:
        return m.group(1).upper()
    # 4. Fallback if user just entered raw code
    cleaned = re.sub(r'[^A-Za-z0-9]', '', text.strip())
    if 4 <= len(cleaned) <= 30:
        return cleaned.upper()
    return None

async def vet_verify(bank: str, reference_number: str, account_suffix: str = "") -> dict:
    """
    Call Verify.ET API to verify a Telebirr, CBE Birr, or CBE transaction in real time.
    """
    if not VERIFY_ET_API_KEY:
        return {"success": False, "verified": False, "error": "VERIFY_ET_API_KEY not configured"}

    headers = {
        "Content-Type": "application/json",
        "x-api-key": VERIFY_ET_API_KEY,
        "Authorization": f"Bearer {VERIFY_ET_API_KEY}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Idempotency-Key": str(uuid.uuid4()),
    }
    
    bank_clean = bank.lower().strip()
    ref_clean = reference_number.strip()
    
    payload = {
        "bank": bank_clean,
        "referenceNumber": ref_clean,
        "reference": ref_clean,
    }
    
    if bank_clean == "telebirr":
        payload["transactionNumber"] = ref_clean
        
    elif bank_clean in ("cbebirr", "cbe_birr"):
        payload["bank"] = "cbebirr"
        payload["receiptNumber"] = ref_clean
        payload["transactionNumber"] = ref_clean
        phone = CBEBIRR_ACCOUNT.replace("+", "").replace(" ", "").strip()
        if phone.startswith("09"):
            phone = "251" + phone[1:]
        elif phone.startswith("9"):
            phone = "251" + phone
        payload["phoneNumber"] = phone

    elif bank_clean == "cbe":
        if account_suffix and len(account_suffix.strip()) == 8:
            payload["accountSuffix"] = account_suffix.strip()

    try:
        session = await get_session()
        async with session.post(f"{VERIFY_ET_URL}?waitMs=5000", json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=18)) as resp:
            data = await resp.json()
            logger.info(f"[Verify.ET] Bank: {bank_clean}, Ref: {ref_clean}, Status: {resp.status}, Response: {data}")
            
            if resp.status == 200:
                raw_data = data.get("data", data)
                if isinstance(raw_data, list) and len(raw_data) > 0:
                    item = raw_data[0]
                elif isinstance(raw_data, dict):
                    item = raw_data
                else:
                    item = {}

                is_ver = bool(item.get("verified", False)) or (data.get("success") is True and item.get("status") in ("completed", "success", "verified"))
                
                if is_ver:
                    amount = float(item.get("amount", 0.0) or 0.0)
                    sender = item.get("senderName", "") or item.get("sender", "")
                    receiver = item.get("receiverAccount", "") or item.get("receiver", "")
                    tx_time = item.get("transactionTime", "") or item.get("time", "")
                    return {
                        "success": True,
                        "verified": True,
                        "amount": amount,
                        "sender": sender,
                        "receiver": receiver,
                        "time": tx_time,
                        "raw": data
                    }
                else:
                    err_msg = item.get("reason") or data.get("message") or "Transaction not found or not settled yet with bank"
                    return {
                        "success": False,
                        "verified": False,
                        "error": str(err_msg),
                        "raw": data
                    }
            elif resp.status == 202:
                return {
                    "success": False,
                    "verified": False,
                    "error": "Transaction is pending verification at bank",
                    "raw": data
                }
            else:
                err_msg = data.get("message") or data.get("error", {}).get("message") if isinstance(data.get("error"), dict) else str(data.get("error") or f"Bank error (HTTP {resp.status})")
                return {
                    "success": False,
                    "verified": False,
                    "error": str(err_msg),
                    "raw": data
                }
    except asyncio.TimeoutError:
        logger.error(f"[Verify.ET] Timeout verifying {bank_clean} ref {ref_clean}")
        return {"success": False, "verified": False, "error": "Bank network timeout. Please retry in 15 seconds."}
    except Exception as ex:
        logger.error(f"[Verify.ET] Exception verifying {bank_clean} ref {ref_clean}: {ex}")
        return {"success": False, "verified": False, "error": f"Verification error: {ex}"}

def build_payment_caption(title: str, amount: float, product_name: str = None) -> tuple:
    """Build payment instruction caption for Telebirr with code entities."""
    custom = _load_custom_responses().get("telebirr_instructions")
    if custom and custom.get("text"):
        ctx = {
            "title": title,
            "amount": f"{amount:,.2f}",
            "product_name": product_name or title,
            "name": PAYMENT_NAME,
            "account": PAYMENT_ACCOUNT,
            "expiry": str(ORDER_EXPIRY_MINUTES),
        }
        return render_text_template(custom["text"], custom.get("entities"), ctx)

    m = Msg()
    if product_name:
        m.emoji("check").text(" ").bold(title).nl(2)
        m.emoji("cart").text(" Product: ").bold(product_name).nl()
        m.emoji("balance").text(" Amount: ").bold(f"{amount:.0f}").text(" ETB").nl()
    else:
        m.emoji("balance").text(" ").bold(title).nl(2)
        m.emoji("balance").text(" Amount: ").bold(f"{amount:.0f}").text(" ETB").nl()
    m.emoji("bank").text(" Bank: ").bold("Telebirr").nl(2)
    m.emoji("thunder").text(" Please send exactly ").bold(f"{amount:.0f}").text(" ETB to:").nl()
    m.emoji("user").text(" Name: ").code(PAYMENT_NAME).nl()
    m.emoji("mobile").text(" Account: ").code(PAYMENT_ACCOUNT).nl(2)
    m.emoji("instructions").text(" ").bold("Payment Instructions:").nl()
    m.emoji("number1").text(" ").italic("ከላይ ወደ ተቀመጠው የ Telebirr አካውንት ትክክለኛውን ሂሳብ ያስገቡ።").nl()
    m.emoji("number2").text(" ").italic("ክፍያውን እንደፈጸሙ ከ Telebirr (127) የደረሰዎትን የ Transaction ID / Reference ቁጥር ይመልከቱ።").nl()
    m.emoji("number3").text(" ").bold("ማሳሰቢያ፡ ").italic("የተላከሎትን የ Transaction Reference Number (ወይም ሙሉውን የ SMS መልእክት) ኮፒ ያድርጉ።").nl()
    m.emoji("number4").text(" ").italic("ኮፒ ያደረጉትን የ Transaction ID እዚህ በመላክ በሰከንዶች ውስጥ በራስ-ሰር (Auto-Verify) ያረጋግጡ!").nl(2)
    m.emoji("timer").text(f" ").italic(f"This order will expire in {ORDER_EXPIRY_MINUTES} minutes")
    return m.build()

def build_cbebirr_payment_caption(title: str, amount: float, product_name: str = None) -> tuple:
    """Build payment instruction caption for CBE Birr with code entities."""
    custom = _load_custom_responses().get("cbebirr_instructions")
    if custom and custom.get("text"):
        ctx = {
            "title": title,
            "amount": f"{amount:,.2f}",
            "product_name": product_name or title,
            "name": CBEBIRR_NAME,
            "account": CBEBIRR_ACCOUNT,
            "expiry": str(ORDER_EXPIRY_MINUTES),
        }
        return render_text_template(custom["text"], custom.get("entities"), ctx)

    m = Msg()
    if product_name:
        m.emoji("check").text(" ").bold(title).nl(2)
        m.emoji("cart").text(" Product: ").bold(product_name).nl()
        m.emoji("balance").text(" Amount: ").bold(f"{amount:.0f}").text(" ETB").nl()
    else:
        m.emoji("balance").text(" ").bold(title).nl(2)
        m.emoji("balance").text(" Amount: ").bold(f"{amount:.0f}").text(" ETB").nl()
    m.emoji("cbe").text(" Bank: ").bold("CBE Birr (Commercial Bank of Ethiopia)").nl(2)
    m.emoji("thunder").text(" Please send exactly ").bold(f"{amount:.0f}").text(" ETB to:").nl()
    m.emoji("user").text(" Name: ").code(CBEBIRR_NAME).nl()
    m.emoji("mobile").text(" Phone / Account: ").code(CBEBIRR_ACCOUNT).nl(2)
    m.emoji("instructions").text(" ").bold("Payment Instructions:").nl()
    m.emoji("number1").text(" ").italic("ከላይ ወደ ተቀመጠው የ CBE Birr አካውንት ትክክለኛውን ሂሳብ ያስገቡ።").nl()
    m.emoji("number2").text(" ").italic("ክፍያውን እንደፈጸሙ ከ CBE Birr (889) የደረሰዎትን የ Transaction ID / Receipt ቁጥር ይመልከቱ።").nl()
    m.emoji("number3").text(" ").bold("ማሳሰቢያ፡ ").italic("የተላከሎትን የ Transaction Reference Number (ወይም ሙሉውን የ SMS መልእክት) ኮፒ ያድርጉ።").nl()
    m.emoji("number4").text(" ").italic("ኮፒ ያደረጉትን የ Transaction ID እዚህ በመላክ በሰከንዶች ውስጥ በራስ-ሰር (Auto-Verify) ያረጋግጡ!").nl(2)
    m.emoji("timer").text(f" ").italic(f"This order will expire in {ORDER_EXPIRY_MINUTES} minutes")
    return m.build()

def build_cbe_payment_caption(title: str, amount: float, product_name: str = None) -> tuple:
    custom = _load_custom_responses().get("cbe_instructions")
    if custom and custom.get("text"):
        ctx = {
            "title": title,
            "amount": f"{amount:,.2f}",
            "product_name": product_name or title,
            "name": CBE_NAME,
            "account": CBE_ACCOUNT,
            "expiry": str(ORDER_EXPIRY_MINUTES),
        }
        return render_text_template(custom["text"], custom.get("entities"), ctx)

    m = Msg()
    if product_name:
        m.emoji("check").text(" ").bold("Your Order Summary").nl(2)
        m.emoji("cart").text(" Product: ").bold(product_name).nl()
        m.emoji("balance").text(" Price: ").bold(f"{amount:.0f}").text(" ETB").nl()
    else:
        m.emoji("balance").text(" ").bold(title).nl(2)
        m.emoji("balance").text(" Amount: ").bold(f"{amount:.0f}").text(" ETB").nl()
    m.emoji("bank").text(" Bank: ").bold("Commercial Bank of Ethiopia").nl(2)
    m.emoji("thunder").text(" Please send exactly ").bold(f"{amount:.0f}").text(" ETB to:").nl()
    m.emoji("user").text(" Name: ").code(CBE_NAME).nl()
    m.emoji("mobile").text(" Account: ").code(CBE_ACCOUNT).nl(2)
    m.emoji("timer").text(f" ").italic(f"This order will expire in {ORDER_EXPIRY_MINUTES} minutes")
    return m.build()

def build_wallet(balance: float):
    m = Msg()
    m.emoji("wallet").text(" ").bold("My Wallet").nl(2)
    m.emoji("balance").text(" Current Balance: ").bold(f"Br {balance:,.2f}").nl()
    m.emoji("thunder").text(" Use your wallet balance for instant, 1-click purchases.").nl(2)
    m.italic("Tap Top Up Wallet below to add funds instantly with Telebirr:")
    return m.build()

def build_topup_prompt(balance: float):
    custom = _load_custom_responses().get("topup_prompt")
    if custom and custom.get("text"):
        ctx = {
            "balance": f"Br {balance:,.2f}",
        }
        return render_text_template(custom["text"], custom.get("entities"), ctx)

    m = Msg()
    m.emoji("wallet").text(" ").bold("Top Up Wallet").nl(2)
    m.emoji("balance").text(" Current Balance: ").bold(f"Br {balance:,.2f}").nl()
    m.emoji("thunder").text(" Select an amount below or ").bold("type any custom amount").text(" (min Br 1.00) in this chat:").nl(2)
    m.italic("Instant automated verification with Telebirr & Verify.ET")
    return m.build()

# ─── KEYBOARDS ────────────────────────────────────────────────
def kb_back():
    return build_keyboard([
        [btn("Back", "back_main", emoji_key="back")]
    ])

def kb_wallet():
    return build_keyboard([
        [btn("Top Up Wallet", "topup_wallet", emoji_key="wallet", style="success")],
        [btn("Shop", "shop", emoji_key="shop"), btn("Home", "back_main", emoji_key="home")],
    ])

def kb_topup_prompt():
    return build_keyboard([
        [btn("100 ETB", "topup_amt_100"), btn("250 ETB", "topup_amt_250"), btn("500 ETB", "topup_amt_500")],
        [btn("1,000 ETB", "topup_amt_1000"), btn("2,500 ETB", "topup_amt_2500"), btn("5,000 ETB", "topup_amt_5000")],
        [btn("Cancel", "wallet", emoji_key="cross")],
    ])

def kb_menu():
    return build_keyboard([
        [btn("Shop",    "shop",    emoji_key="shop"),
         btn("Profile", "profile", emoji_key="profile")],
        [btn("Wallet",   "wallet",   emoji_key="wallet"),
         btn("History",  "history",  emoji_key="clipboard")],
        [btn("Bot Logs", url=LOG_CHANNEL_LINK, emoji_key="channel"),
         btn("Back", "back_main", emoji_key="back")],
    ])

def kb_profile():
    return build_keyboard([
        [btn("My Wallet",  "wallet",    emoji_key="wallet"),
         btn("Order History", "history", emoji_key="clipboard")],
        [btn("Bot Logs", url=LOG_CHANNEL_LINK, emoji_key="channel"),
         btn("Referral", "referral", emoji_key="referral")],
        [btn("Support", url=SUPPORT_LINK, emoji_key="support")],
        [btn("Main Menu", "back_main", emoji_key="home")],
    ])

def kb_home():
    return build_keyboard([
        [btn("Home", "back_main", emoji_key="back")]
    ])

def reply_kb_main(user_id=None) -> dict:
    """Build persistent bottom rectangle reply keyboard."""
    rows = [
        [{"text": "🛍️ Browse Products / Shop"}],
        [{"text": "💳 My Wallet"}, {"text": "👤 Profile"}],
        [{"text": "📜 Order History"}, {"text": "📊 Bot Logs"}],
        [{"text": "👥 Referral"}, {"text": "🎧 Support"}],
        [{"text": "📢 Channel"}],
    ]
    if user_id and is_admin(user_id):
        rows.append([{"text": "👑 Admin Control Panel"}])
    else:
        rows.append([{"text": "👨‍💻 Developed By @kidanewold777"}])
    return {
        "keyboard": rows,
        "resize_keyboard": True,
        "is_persistent": True
    }

# ─── ADMIN STATE (in-memory conversation state) ───────────────
# State keys: "addcat_step", "addcat_data", "addstock_step", "addstock_data"
_admin_state: dict = {}   # { user_id: { "step": ..., "data": {...} } }

# ─── USER PAYMENT STATE ───────────────────────────────────────
# Tracks users waiting to send a payment screenshot (Telebirr)
# { user_id: order_id }
_awaiting_screenshot: dict = {}

# Tracks users waiting to paste their CBE SMS text
# { user_id: order_id }
_awaiting_cbe_sms: dict = {}

# Tracks users who are entering a top-up amount
# { user_id: True }
_awaiting_topup_amount: dict = {}

# Tracks users who are entering a custom product purchase quantity
# { user_id: {"cat_id": str, "mid": int} }
_awaiting_qty_input: dict = {}

def is_admin(user_id) -> bool:
    if not user_id:
        return False
    try:
        return int(user_id) in ADMINS
    except (ValueError, TypeError):
        return False

# ─── BOT USERNAME CACHE ───────────────────────────────────────
_bot_username: str | None = None

async def get_bot_username() -> str:
    global _bot_username
    if not _bot_username:
        try:
            data = await api_call("getMe", {})
            _bot_username = data.get("result", {}).get("username") or "et_market_place"
        except Exception:
            _bot_username = "et_market_place"
    return _bot_username or "et_market_place"

# ─── DATABASE ─────────────────────────────────────────────────
# ─── DATABASE (JSON) ──────────────────────────────────────────
_db_lock  = asyncio.Lock()
_cat_lock = asyncio.Lock()
_stk_lock = asyncio.Lock()

def _load_db() -> dict:
    """Load users.json from memory cache or disk."""
    if _CACHE["users"] is not None:
        return _CACHE["users"]
    if not os.path.exists(DB_PATH):
        _CACHE["users"] = {}
        return {}
    try:
        with open(DB_PATH, "r", encoding="utf-8-sig") as f:
            _CACHE["users"] = json.load(f)
            return _CACHE["users"]
    except Exception:
        _CACHE["users"] = {}
        return {}

def _load_users() -> dict:
    """Alias for _load_db() to load users.json."""
    return _load_db()

def _save_db(data: dict):
    """Write users.json to cache, disk atomically, and sync to Supabase."""
    _CACHE["users"] = data
    atomic_save_json(DB_PATH, data)
    supabase_db.sync_supabase_in_background("users", data)

def _load_categories() -> dict:
    if _CACHE["categories"] is not None:
        return _CACHE["categories"]
    if not os.path.exists(CAT_PATH):
        _CACHE["categories"] = {}
        return {}
    try:
        with open(CAT_PATH, "r", encoding="utf-8-sig") as f:
            _CACHE["categories"] = json.load(f)
            return _CACHE["categories"]
    except Exception:
        _CACHE["categories"] = {}
        return {}

def _save_categories(data: dict):
    """Write categories.json to cache, disk atomically, and sync to Supabase."""
    _CACHE["categories"] = data
    atomic_save_json(CAT_PATH, data)
    supabase_db.sync_supabase_in_background("categories", data)

def _load_stock() -> dict:
    if _CACHE["stock"] is not None:
        return _CACHE["stock"]
    if not os.path.exists(STOCK_PATH):
        _CACHE["stock"] = {}
        return {}
    try:
        with open(STOCK_PATH, "r", encoding="utf-8-sig") as f:
            _CACHE["stock"] = json.load(f)
            return _CACHE["stock"]
    except Exception:
        _CACHE["stock"] = {}
        return {}

def _save_stock(data: dict):
    """Write stock.json to cache, disk atomically, and sync to Supabase."""
    _CACHE["stock"] = data
    atomic_save_json(STOCK_PATH, data)
    supabase_db.sync_supabase_in_background("stock", data)

async def db_init():
    """Create JSON files if they don't exist, synchronize with Supabase, and warm memory caches."""
    for path, default in [(DB_PATH, {}), (CAT_PATH, {}), (STOCK_PATH, {}), (ORDERS_PATH, {})]:
        if not os.path.exists(path):
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(default, f, indent=2)
            except Exception:
                pass
    # Pull latest data from Supabase if running in serverless / startup
    try:
        await supabase_db.supabase_sync_all_to_local()
    except Exception:
        pass

    # Warm in-memory cache for instant zero-IO performance
    _load_db()
    _load_categories()
    _load_stock()
    _load_orders()
    _load_giveaways()
    _load_custom_responses()
    _load_used_references()

    # Sanitize any negative balances in users.json
    try:
        async with _db_lock:
            data = _load_db()
            changed = False
            for uid, u in data.items():
                if isinstance(u, dict) and u.get("balance", 0.0) < 0:
                    u["balance"] = 0.0
                    changed = True
            if changed:
                _save_db(data)
    except Exception:
        pass
    logger.info("Databases ready.")

async def db_upsert_user(user: dict):
    """Insert new user or update username/first_name and last_seen."""
    uid   = str(user.get("id"))
    uname = user.get("username") or ""
    fname = user.get("first_name") or ""
    now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with _db_lock:
        data = _load_db()
        if uid not in data:
            data[uid] = {
                "user_id":         uid,
                "username":        uname,
                "first_name":      fname,
                "balance":         0.0,
                "total_spent":     0.0,
                "products_bought": 0,
                "joined_at":       now,
                "last_seen":       now,
                "terms_accepted":  False,
            }
        else:
            data[uid]["username"]   = uname
            data[uid]["first_name"] = fname
            data[uid]["last_seen"]  = now
        _save_db(data)

async def db_get_user(user_id) -> dict | None:
    """Fetch a user dict, or None if not found."""
    async with _db_lock:
        data = _load_db()
        return data.get(str(user_id))

async def db_accept_terms(user_id):
    """Mark user as having accepted terms."""
    uid = str(user_id)
    async with _db_lock:
        data = _load_db()
        if uid in data:
            data[uid]["terms_accepted"] = True
            _save_db(data)

async def db_add_balance(user_id, amount: float):
    """Add amount to user balance."""
    async with _db_lock:
        data = _load_db()
        uid  = str(user_id)
        if uid in data:
            data[uid]["balance"] = round(data[uid].get("balance", 0.0) + amount, 2)
            _save_db(data)

async def db_deduct_balance(user_id, amount: float):
    """Deduct amount from user balance safely without going below 0."""
    async with _db_lock:
        data = _load_db()
        uid  = str(user_id)
        if uid in data:
            data[uid]["balance"] = round(max(0.0, data[uid].get("balance", 0.0) - abs(amount)), 2)
            _save_db(data)

async def db_record_purchase(user_id, amount: float):
    """Record a product purchase — add to spent & count."""
    async with _db_lock:
        data = _load_db()
        uid  = str(user_id)
        if uid in data:
            data[uid]["total_spent"]     = round(data[uid].get("total_spent", 0.0) + amount, 2)
            data[uid]["products_bought"] = data[uid].get("products_bought", 0) + 1
            _save_db(data)

# ─── CATEGORY & STOCK DB HELPERS ──────────────────────────────
async def cat_get_all(include_disabled: bool = False) -> dict:
    """Return products dictionary. If include_disabled=False, returns only enabled products."""
    async with _cat_lock:
        all_cats = _load_categories()
        if include_disabled:
            return all_cats
        return {k: v for k, v in all_cats.items() if v.get("enabled", True) is not False}

async def cat_get_all_admin() -> dict:
    """Return all products including disabled ones for admin panel."""
    return await cat_get_all(include_disabled=True)

async def cat_toggle_enabled(cat_id: str) -> bool:
    """Toggle product ON/OFF. Returns new enabled status."""
    async with _cat_lock:
        data = _load_categories()
        if cat_id in data:
            current = data[cat_id].get("enabled", True)
            data[cat_id]["enabled"] = not current
            _save_categories(data)
            return data[cat_id]["enabled"]
        return False

async def cat_update_price(cat_id: str, new_price: float) -> bool:
    """Update product price in ETB."""
    async with _cat_lock:
        data = _load_categories()
        if cat_id in data:
            data[cat_id]["price"] = max(0.0, float(new_price))
            _save_categories(data)
            return True
        return False

def clean_api_text(text: str) -> str:
    """Strip custom emoji wrappers and HTML tags from API text."""
    if not text:
        return ""
    text = re.sub(r'\{\{ce:\d+\|([^}]+)\}\}', r'\1', text)
    text = re.sub(r'</?[a-zA-Z0-9]+[^>]*>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

# ─── SAFWAN TIGER RESELLER API CLIENT ─────────────────────────
async def safwan_api_call(endpoint: str, payload: dict = None, method: str = "POST") -> dict:
    """Call SafwanTiger Reseller API."""
    if not SAFWAN_API_KEY:
        return {"ok": False, "error": "SAFWAN_API_KEY not configured"}
    
    url = f"{SAFWAN_API_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = {
        "x-api-key": SAFWAN_API_KEY,
        "Authorization": f"Bearer {SAFWAN_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    }
    
    try:
        session = await get_session()
        if method.upper() == "GET":
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"ok": False, "error": f"HTTP {resp.status}"}
        else:
            async with session.post(url, json=payload or {}, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"ok": False, "error": f"HTTP {resp.status}"}
    except Exception as ex:
        logger.error(f"[SafwanAPI] Error calling {endpoint}: {ex}")
        return {"ok": False, "error": str(ex)}

_safwan_catalog_cache = None  # { "data": list, "time": float }

async def safwan_get_products() -> list:
    """Fetch live product catalog and stock from SafwanTiger API with global caching."""
    global _safwan_catalog_cache, _safwan_stock_cache
    now = time.time()
    if _safwan_catalog_cache and (now - _safwan_catalog_cache["time"] < 60):
        return _safwan_catalog_cache["data"]
    
    if not SAFWAN_API_KEY:
        return []

    res = await safwan_api_call("products", method="GET")
    prods = []
    if isinstance(res, list):
        prods = res
    elif isinstance(res, dict):
        prods = res.get("products", res.get("data", []))
    
    _safwan_catalog_cache = {"data": prods, "time": now}
    for p in prods:
        pid = p.get("id")
        if pid is not None:
            _safwan_stock_cache[pid] = (int(p.get("stock", 0) or 0), now)
            
    return prods

async def safwan_get_balance() -> dict:
    """Fetch current reseller account balance from Safwan API."""
    res = await safwan_api_call("balance", method="GET")
    if isinstance(res, dict):
        if "balance" in res:
            return {"ok": True, "balance": float(res.get("balance", 0.0) or 0.0), "currency": res.get("currency", "USDT")}
        elif "data" in res and isinstance(res["data"], dict) and "balance" in res["data"]:
            return {"ok": True, "balance": float(res["data"].get("balance", 0.0) or 0.0), "currency": res["data"].get("currency", "USDT")}
        return res
    return {"ok": False, "error": "Invalid response"}

async def safwan_order(product_id: int, quantity: int = 1, custom_fields: dict = None) -> dict:
    """Place an auto-fulfillment order with SafwanTiger API."""
    payload = {
        "product_id": product_id,
        "quantity": quantity,
    }
    if custom_fields:
        payload.update(custom_fields)
    return await safwan_api_call("order", payload=payload, method="POST")

async def safwan_sync_products_to_json() -> dict:
    """Fetch products from Safwan API and store/update in categories.json with description & notes."""
    safwan_data = await safwan_get_products()
    prods = safwan_data if isinstance(safwan_data, list) else safwan_data.get("products", [])
    if not prods:
        return {"ok": False, "error": "No products returned from API"}

    new_count = 0
    updated_count = 0
    
    async with _cat_lock:
        categories = _load_categories()
        existing_safwan_map = {v.get("safwan_product_id"): k for k, v in categories.items() if v.get("safwan_product_id")}
        
        for p in prods:
            pid = p.get("id")
            p_name = p.get("name", "")
            p_usd = p.get("price", 0.0) or 0.0
            p_stock = p.get("stock", 0) or 0
            p_desc = clean_api_text(p.get("description", ""))
            p_notes = clean_api_text(p.get("warranty", ""))
            
            if pid in existing_safwan_map:
                cid = existing_safwan_map[pid]
                categories[cid]["supplier_price_usd"] = p_usd
                categories[cid]["supplier_stock"] = p_stock
                if p_desc:
                    categories[cid]["description"] = p_desc
                if p_notes:
                    categories[cid]["notes"] = p_notes
                updated_count += 1
            else:
                clean_name = re.sub(r'[^a-zA-Z0-9]+', '_', p_name.lower()).strip('_')[:25]
                cid = f"api_{pid}_{clean_name}"
                suggested_etb = max(500.0, round((p_usd * 220) / 50) * 50)
                is_link = "link" in p_name.lower() or "redeem" in p_name.lower() or "gemini" in p_name.lower()
                cat_type = "link" if is_link else "id_pass"
                
                categories[cid] = {
                    "id": cid,
                    "name": p_name,
                    "price": float(suggested_etb),
                    "cat_type": cat_type,
                    "emoji_char": "⚡",
                    "description": p_desc or f"⚡ {p_name}\n• Automated Delivery via Supplier API",
                    "notes": p_notes or "Full Warranty",
                    "safwan_product_id": pid,
                    "supplier_price_usd": p_usd,
                    "supplier_stock": p_stock,
                    "enabled": True
                }
                new_count += 1
        
        _save_categories(categories)
        
    return {"ok": True, "total": len(categories), "new": new_count, "updated": updated_count}

async def cat_save(cat_id: str, name: str, price: float,
                   emoji_char: str, emoji_id: str, cat_type: str = "id_pass",
                   description: str = "", desc_entities: list = None):
    async with _cat_lock:
        data = _load_categories()
        data[cat_id] = {
            "id":          cat_id,
            "name":        name,
            "price":       price,
            "emoji_char":  emoji_char,
            "emoji_id":    emoji_id,
            "cat_type":    cat_type,   # "link" or "id_pass"
            "description": description,
            "desc_entities": desc_entities or [],  # Store premium emoji entities
            "created_at":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        _save_categories(data)

async def stock_get(cat_id: str) -> list:
    async with _stk_lock:
        data = _load_stock()
        return data.get(cat_id, [])

async def stock_get_count(cat_id: str) -> int:
    """Get stock count — automatically checks live API stock or stock.json."""
    return await stock_count(cat_id)

# ─── REAL-TIME RESTOCK NOTIFICATION ENGINE ────────────────────
_last_known_stock_counts: dict[str, int] = {}
_stock_tracker_initialized: bool = False
_restock_lock = asyncio.Lock()

async def broadcast_stock_restock(cat_id: str, cat: dict, old_count: int, new_count: int, is_safwan: bool = False):
    """
    Broadcast a rich announcement when new stock is added (either via Safwan API or Local Admin).
    Delivers to Log Channel, Main Channel, and Admins.
    """
    if new_count <= old_count:
        return
    added_qty = new_count - old_count
    cat_name = cat.get("name", "Product")
    price = float(cat.get("price", 0.0) or 0.0)
    emoji_icon = cat.get("emoji_char", "📦")
    
    bot_username = await get_bot_username()
    buy_url = f"https://t.me/{bot_username}?start=cat_{cat_id}" if bot_username else None
    
    m = Msg()
    m.emoji("box").text(" ").bold("🚨 RESTOCK ALERT — NEW STOCK ADDED!").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("cart").text(f" Product: ").bold(f"{emoji_icon} {cat_name}").nl()
    m.emoji("sparkles").text(f" Stock Available: ").bold(f"{new_count} units ").italic(f"(+{added_qty} new)").nl()
    m.emoji("balance").text(f" Price: ").bold(f"Br {price:,.2f}").nl()
    if is_safwan:
        m.emoji("thunder").text(" Delivery: ").bold("Instant Automated Delivery (24/7 API)").nl()
    else:
        m.emoji("thunder").text(" Delivery: ").bold("Instant Local Delivery").nl()
    m.text("━━━━━━━━━━━━━━━━━━━━").nl()
    m.emoji("shop").text(" Tap the button below to buy before it sells out!")
    t, ent = m.build()
    
    kb_rows = []
    if buy_url:
        kb_rows.append([btn("🛒 Buy Now in Bot", url=buy_url, emoji_key="shop", style="success")])
    keyboard = build_keyboard(kb_rows) if kb_rows else None
    
    # 1. Post to Log Channel
    if LOG_CHANNEL_ID:
        try:
            await send_msg(LOG_CHANNEL_ID, t, ent, keyboard)
        except Exception as ex:
            logger.warning(f"[broadcast_stock_restock] Failed to post to log channel: {ex}")
            
    # 2. Post to Force Join / Announcement Channel (if configured and distinct)
    if FORCE_JOIN_CHANNEL_ID and str(FORCE_JOIN_CHANNEL_ID) != str(LOG_CHANNEL_ID):
        try:
            await send_msg(FORCE_JOIN_CHANNEL_ID, t, ent, keyboard)
        except Exception as ex:
            logger.warning(f"[broadcast_stock_restock] Could not post to main channel: {ex}")
            
    # 3. Notify Admins
    for adm in ADMINS:
        try:
            adm_m = Msg()
            adm_m.emoji("box").text(" ").bold("📢 Restock Notification Broadcasted").nl()
            adm_m.emoji("cart").text(f" Product: {cat_name}\n")
            adm_m.emoji("sparkles").text(f" Stock: {new_count} units (+{added_qty})\n")
            adm_m.emoji("thunder").text(f" Source: {'SafwanTiger API' if is_safwan else 'Local Stock'}")
            at, ae = adm_m.build()
            await send_msg(adm, at, ae)
        except Exception:
            pass

async def check_and_notify_stock_changes(cats: dict, new_counts: dict):
    """Compare real-time stock counts against last known counts and trigger restock broadcasts."""
    global _last_known_stock_counts, _stock_tracker_initialized
    async with _restock_lock:
        if _stock_tracker_initialized:
            for cid, current_stock in new_counts.items():
                cat = cats.get(cid)
                if not cat:
                    continue
                old_stock = _last_known_stock_counts.get(cid, 0)
                if current_stock > old_stock:
                    is_safwan = bool(cat.get("safwan_product_id"))
                    asyncio.create_task(broadcast_stock_restock(cid, cat, old_stock, current_stock, is_safwan=is_safwan))
        
        # Update last known counts
        for cid, current_stock in new_counts.items():
            _last_known_stock_counts[cid] = current_stock
        _stock_tracker_initialized = True

async def stock_set_count(cat_id: str, count: int):
    """Set stock count directly for local products and broadcast restock if increased."""
    old_count = 0
    async with _stk_lock:
        data = _load_stock()
        val = data.get(cat_id, 0)
        old_count = len(val) if isinstance(val, list) else int(val or 0)
        data[cat_id] = max(0, int(count))
        _save_stock(data)
        
    cats = _load_categories()
    cat = cats.get(cat_id)
    if cat and int(count) > old_count:
        await broadcast_stock_restock(cat_id, cat, old_count, int(count), is_safwan=False)

async def stock_decrement(cat_id: str) -> bool:
    """Decrement stock by 1 for local products."""
    async with _stk_lock:
        data = _load_stock()
        val = data.get(cat_id, 0)
        count = len(val) if isinstance(val, list) else int(val)
        if count <= 0:
            return False
        data[cat_id] = max(0, count - 1)
        _save_stock(data)
        return True

async def stock_add(cat_id: str, items: list):
    """Add a list of {'email':..,'password':..} dicts to a category's stock and broadcast restock."""
    old_count = 0
    new_count = 0
    async with _stk_lock:
        data = _load_stock()
        if cat_id not in data:
            data[cat_id] = []
        old_count = len(data[cat_id])
        data[cat_id].extend(items)
        new_count = len(data[cat_id])
        _save_stock(data)
    
    cats = _load_categories()
    cat = cats.get(cat_id)
    if cat:
        await broadcast_stock_restock(cat_id, cat, old_count, new_count, is_safwan=False)

async def cat_delete(cat_id: str):
    async with _cat_lock:
        data = _load_categories()
        if cat_id in data:
            del data[cat_id]
            _save_categories(data)
    # Also remove its stock
    async with _stk_lock:
        data = _load_stock()
        if cat_id in data:
            del data[cat_id]
            _save_stock(data)

# ─── SAFWAN LIVE STOCK CACHE ──────────────────────────────────
_safwan_stock_cache = {}  # { pid: (stock_count, timestamp) }
_SAFWAN_CACHE_TTL = 30  # seconds

def invalidate_safwan_stock_cache(pid: int = None):
    global _safwan_stock_cache
    if pid is not None:
        _safwan_stock_cache.pop(pid, None)
    else:
        _safwan_stock_cache.clear()

async def get_live_safwan_stock(safwan_product_id: int) -> int:
    """Query live product stock from SafwanTiger Reseller API with cache."""
    now = time.time()
    if safwan_product_id in _safwan_stock_cache:
        cached_stk, cached_time = _safwan_stock_cache[safwan_product_id]
        if now - cached_time < _SAFWAN_CACHE_TTL:
            return cached_stk

    products = await safwan_get_products()
    if isinstance(products, list):
        for p in products:
            if p.get("id") == safwan_product_id:
                stk = int(p.get("stock", 0) or 0)
                _safwan_stock_cache[safwan_product_id] = (stk, now)
                return stk
    _safwan_stock_cache[safwan_product_id] = (0, now)
    return 0

async def stock_count(cat_id: str) -> int:
    """
    Get real-time live stock count.
    - If mapped to Safwan Supplier API: queries live API stock.
    - If local product: queries stock.json.
    """
    cats = _load_categories()
    cat = cats.get(cat_id)
    if not cat:
        return 0

    # If linked to Safwan API, check live supplier stock
    sp_id = cat.get("safwan_product_id")
    if sp_id:
        return await get_live_safwan_stock(sp_id)

    # Otherwise check local stock.json
    async with _stk_lock:
        data = _load_stock()
        val = data.get(cat_id, 0)
        if isinstance(val, list):
            return len(val)
        try:
            return max(0, int(val))
        except (ValueError, TypeError):
            return 0

async def get_all_stock_counts(cats: dict | list) -> dict:
    """
    Ultra-fast batch stock lookup for entire catalog in sub-milliseconds.
    Reads local stock once and uses cached Safwan API stock.
    Automatically checks and broadcasts real-time restocks if new stock is detected.
    """
    if isinstance(cats, dict):
        cat_dict = cats
    else:
        cat_dict = {c["id"]: c for c in cats}
        
    counts = {}
    has_safwan = any(bool(c.get("safwan_product_id")) for c in cat_dict.values())
    safwan_stock_map = {}
    
    if has_safwan and SAFWAN_API_KEY:
        try:
            prods = await safwan_get_products()
            for p in prods:
                pid = p.get("id")
                if pid is not None:
                    safwan_stock_map[pid] = int(p.get("stock", 0) or 0)
        except Exception:
            pass
            
    async with _stk_lock:
        local_stock = _load_stock()
        
    for cid, cat in cat_dict.items():
        sp_id = cat.get("safwan_product_id")
        if sp_id:
            counts[cid] = safwan_stock_map.get(sp_id, int(cat.get("supplier_stock", 0) or 0))
        else:
            val = local_stock.get(cid, 0)
            if isinstance(val, list):
                counts[cid] = len(val)
            else:
                try:
                    counts[cid] = max(0, int(val))
                except (ValueError, TypeError):
                    counts[cid] = 0
                    
    # Check for live stock increases and notify
    await check_and_notify_stock_changes(cat_dict, counts)
    return counts

# ─── ORDERS DB ────────────────────────────────────────────────
_ord_lock = asyncio.Lock()

def _load_orders() -> dict:
    if _CACHE["orders"] is not None:
        return _CACHE["orders"]
    if not os.path.exists(ORDERS_PATH):
        _CACHE["orders"] = {}
        return {}
    try:
        with open(ORDERS_PATH, "r", encoding="utf-8-sig") as f:
            _CACHE["orders"] = json.load(f)
            return _CACHE["orders"]
    except Exception:
        _CACHE["orders"] = {}
        return {}

def _save_orders(data: dict):
    """Write orders.json to cache, disk atomically, and sync to Supabase."""
    _CACHE["orders"] = data
    atomic_save_json(ORDERS_PATH, data)
    supabase_db.sync_supabase_in_background("orders", data)

async def post_new_order_log(order_id: str, cat_name: str, price: float,
                             quantity: int = 1, user_id=None, order_type: str = "purchase"):
    """Send real-time new order notification to the logs channel."""
    if not LOG_CHANNEL_ID:
        return
    try:
        bot_username = await get_bot_username()
        u_str = str(user_id) if user_id else ""
        if len(u_str) > 4:
            user_mask = f"User #***{u_str[-4:]}"
        elif u_str:
            user_mask = f"User #{u_str}"
        else:
            user_mask = "Customer"

        short_id = order_id[:8].upper() if order_id else "N/A"
        qty_str = f" (x{quantity})" if quantity and int(quantity) > 1 else ""

        m = Msg()
        if order_type == "topup":
            m.emoji("wallet").text(" ").bold("New Wallet Top-Up Initiated!").nl()
            m.text("━━━━━━━━━━━━━━━━━━━━").nl()
            m.emoji("box").text(" Order ID: ").code(f"#{short_id}").nl()
            m.emoji("balance").text(" Deposit Amount: ").bold(f"Br {price:,.2f} ETB").nl()
            m.emoji("user").text(" Customer: ").bold(user_mask).nl()
            m.emoji("timer").text(" Status: ").bold("Pending Payment Verification").nl()
            m.text("━━━━━━━━━━━━━━━━━━━━").nl()
            if bot_username:
                m.emoji("bot").text(" Shop Bot: ").bold(f"@{bot_username}")
        else:
            m.emoji("shop").text(" ").bold("New Product Order Placed!").nl()
            m.text("━━━━━━━━━━━━━━━━━━━━").nl()
            m.emoji("box").text(" Order ID: ").code(f"#{short_id}").nl()
            m.emoji("cart").text(" Product: ").bold(f"{cat_name}{qty_str}").nl()
            m.emoji("balance").text(" Total Price: ").bold(f"Br {price:,.2f} ETB").nl()
            m.emoji("user").text(" Customer: ").bold(user_mask).nl()
            m.emoji("timer").text(" Status: ").bold("Processing / Awaiting Payment").nl()
            m.text("━━━━━━━━━━━━━━━━━━━━").nl()
            if bot_username:
                m.emoji("bot").text(" Shop Bot: ").bold(f"@{bot_username}")

        t, ent = m.build()
        kb = build_keyboard([[btn("🛒 Start Shopping", url=f"https://t.me/{bot_username}", emoji_key="shop", style="success")]]) if bot_username else None
        await send_msg(LOG_CHANNEL_ID, t, ent, keyboard=kb)
    except Exception as ex:
        logger.warning(f"[post_new_order_log] Failed to post log: {ex}")

async def post_sale_log(cat_name: str, price: float, order_type: str = "purchase",
                        order_id: str = None, user_id=None):
    """Send completed sale / delivery notification to the logs channel."""
    if not LOG_CHANNEL_ID:
        return
    try:
        bot_username = await get_bot_username()
        u_str = str(user_id) if user_id else ""
        if len(u_str) > 4:
            user_mask = f"User #***{u_str[-4:]}"
        elif u_str:
            user_mask = f"User #{u_str}"
        else:
            user_mask = "Customer"

        short_id = order_id[:8].upper() if order_id else None

        m = Msg()
        if order_type == "topup":
            m.emoji("check").text(" ").bold("Wallet Deposit Completed!").nl()
            m.text("━━━━━━━━━━━━━━━━━━━━").nl()
            if short_id:
                m.emoji("box").text(" Order ID: ").code(f"#{short_id}").nl()
            m.emoji("balance").text(" Amount Credited: ").bold(f"Br {price:,.2f} ETB").nl()
            m.emoji("user").text(" Customer: ").bold(user_mask).nl()
            m.emoji("check").text(" Status: ").bold("Approved & Credited to Balance").nl()
            m.text("━━━━━━━━━━━━━━━━━━━━").nl()
            if bot_username:
                m.emoji("bot").text(" Shop Bot: ").bold(f"@{bot_username}")
        else:
            m.emoji("check").text(" ").bold("Purchase Completed & Delivered!").nl()
            m.text("━━━━━━━━━━━━━━━━━━━━").nl()
            if short_id:
                m.emoji("box").text(" Order ID: ").code(f"#{short_id}").nl()
            m.emoji("cart").text(" Item: ").bold(cat_name).nl()
            m.emoji("balance").text(" Total Paid: ").bold(f"Br {price:,.2f} ETB").nl()
            m.emoji("user").text(" Customer: ").bold(user_mask).nl()
            m.emoji("check").text(" Status: ").bold("Completed & Delivered ✅").nl()
            m.text("━━━━━━━━━━━━━━━━━━━━").nl()
            if bot_username:
                m.emoji("bot").text(" Shop Bot: ").bold(f"@{bot_username}")

        t, ent = m.build()
        kb = build_keyboard([[btn("🛒 Start Shopping", url=f"https://t.me/{bot_username}", emoji_key="shop", style="success")]]) if bot_username else None
        await send_msg(LOG_CHANNEL_ID, t, ent, keyboard=kb)
    except Exception as ex:
        logger.warning(f"[post_sale_log] Failed to post log: {ex}")

async def order_create(user_id, cat_id: str, cat_name: str, price: float,
                       quantity: int = 1, unit_price: float = None,
                       order_type: str = "purchase") -> str:
    """Create a new pending order with quantity support. Returns order_id."""
    order_id = str(uuid.uuid4())
    now = datetime.now()
    u_price = float(unit_price if unit_price is not None else price)
    qty = max(1, int(quantity))
    total_price = float(price) if unit_price is None else float(u_price * qty)
    async with _ord_lock:
        data = _load_orders()
        data[order_id] = {
            "order_id":           order_id,
            "user_id":            str(user_id),
            "cat_id":             cat_id,
            "cat_name":           cat_name,
            "quantity":           qty,
            "unit_price":         u_price,
            "price":              total_price,
            "order_type":         order_type,   # "purchase" or "topup"
            "status":             "pending_payment",
            "created_at":         now.strftime("%Y-%m-%d %H:%M:%S"),
            "expires_at":         (now + timedelta(minutes=ORDER_EXPIRY_MINUTES)).strftime("%Y-%m-%d %H:%M:%S"),
            "screenshot_file_id": None,
        }
        _save_orders(data)

    # Automatically post new order to bot logs channel
    try:
        await post_new_order_log(
            order_id=order_id,
            cat_name=cat_name,
            price=total_price,
            quantity=qty,
            user_id=user_id,
            order_type=order_type
        )
    except Exception as ex:
        logger.warning(f"[order_create] Failed to post new order log: {ex}")

    return order_id

async def order_get(order_id: str) -> dict | None:
    async with _ord_lock:
        data = _load_orders()
        return data.get(order_id)

async def order_set_status(order_id: str, status: str):
    async with _ord_lock:
        data = _load_orders()
        if order_id in data:
            data[order_id]["status"] = status
            _save_orders(data)

async def order_set_screenshot(order_id: str, file_id: str):
    async with _ord_lock:
        data = _load_orders()
        if order_id in data:
            data[order_id]["screenshot_file_id"] = file_id
            data[order_id]["status"] = "pending_approval"
            _save_orders(data)

async def order_get_pending_by_user(user_id) -> dict | None:
    """Get the latest pending_payment order for a user."""
    async with _ord_lock:
        data = _load_orders()
        for oid, order in reversed(list(data.items())):
            if (order["user_id"] == str(user_id) and
                    order["status"] == "pending_payment"):
                return order
        return None

async def start_topup_order(chat_id: int, user_id: int | str, amount: float, edit_mid: int = None):
    """Create a top-up order and let user select payment method (Telebirr or CBE Birr)."""
    order_id = await order_create(
        user_id, "wallet_topup", f"Wallet Top Up — Br {amount:,.2f}", amount, order_type="topup"
    )
    
    m = Msg()
    m.emoji("wallet").text(" ").bold("Wallet Top-Up Order").nl(2)
    m.emoji("balance").text(" Deposit Amount: ").bold(f"Br {amount:,.2f} ETB").nl(2)
    m.emoji("bank").text(" Choose your payment method below:").nl()
    m.text("• Instant automated 24/7 verification with Verify.ET")
    t, ent = m.build()

    kb = build_keyboard([
        [btn("💙 Pay via Telebirr", f"topup_telebirr_{order_id}", emoji_key="telebirr", style="success")],
        [btn("🏦 Pay via CBE Birr", f"topup_cbebirr_{order_id}", emoji_key="cbe", style="success")],
        [btn("❌ Cancel", f"cancel_{order_id}", emoji_key="cross")],
    ])
    
    if edit_mid:
        try:
            await api_call("deleteMessage", {"chat_id": chat_id, "message_id": edit_mid})
        except Exception:
            pass
            
    await send_msg(chat_id, t, ent, kb)

async def stock_pop_multiple(cat_id: str, quantity: int = 1) -> list:
    """Pop up to `quantity` stock items from cat_id atomically. Returns list of items/codes."""
    qty = max(1, int(quantity))
    async with _stk_lock:
        data = _load_stock()
        items = data.get(cat_id)
        popped = []
        if isinstance(items, list):
            for _ in range(min(qty, len(items))):
                popped.append(items.pop(0))
            data[cat_id] = items
            _save_stock(data)
            return popped
        elif isinstance(items, (int, float)) and items > 0:
            count_to_deduct = min(qty, int(items))
            data[cat_id] = max(0, int(items) - count_to_deduct)
            _save_stock(data)
            return [None] * count_to_deduct
        return []

async def stock_pop(cat_id: str) -> dict | None:
    """Pop one stock item from cat_id. Returns item dict or None if empty."""
    items = await stock_pop_multiple(cat_id, 1)
    return items[0] if items else None

async def post_stock_log(cat_name: str, count: int, cat_id: str = ""):
    """Send a stock restock notification to the log channel."""
    if not LOG_CHANNEL_ID:
        return
    try:
        bot_username = await get_bot_username()
        buy_url = f"https://t.me/{bot_username}?start=cat_{cat_id}" if (bot_username and cat_id) else (f"https://t.me/{bot_username}" if bot_username else None)
        
        m = Msg()
        m.emoji("box").text(" ").bold("Product Restocked!").nl()
        m.text("━━━━━━━━━━━━━━━━━━━━").nl()
        m.emoji("cart").text(" Item: ").bold(cat_name).nl()
        m.emoji("sparkles").text(" Added: ").bold(f"{count} items").nl()
        m.emoji("check").text(" Status: ").bold("Available Now for Instant Delivery").nl()
        m.text("━━━━━━━━━━━━━━━━━━━━").nl()
        if bot_username:
            m.emoji("bot").text(" Shop Bot: ").bold(f"@{bot_username}")

        t, ent = m.build()
        kb = build_keyboard([[btn("🛒 Buy Now", url=buy_url, emoji_key="shop", style="success")]]) if buy_url else None
        await send_msg(LOG_CHANNEL_ID, t, ent, keyboard=kb)
    except Exception as ex:
        logger.warning(f"[post_stock_log] Failed to post stock log: {ex}")


async def fulfill_order_auto(order_id: str, verified_amount: float = None, sender: str = "", ref: str = ""):
    """Fulfill an order automatically (delivering digital product or crediting wallet top-up)."""
    order = await order_get(order_id)
    if not order:
        return False
        
    user_id = order["user_id"]
    order_type = order.get("order_type", "purchase")
    amount_to_credit = float(verified_amount if verified_amount is not None else order["price"])
    
    # Check if already approved (prevent double fulfillment)
    if order.get("status") == "approved":
        return True

    # Mark transaction reference as permanently used
    if ref:
        await mark_reference_used(ref, order_id, user_id, amount_to_credit)
        
    await order_set_status(order_id, "approved")
    
    # 1. Top-up Fulfillment
    if order_type == "topup":
        await db_add_balance(user_id, amount_to_credit)
        await post_sale_log("💳 Wallet Top Up", amount_to_credit, "topup", order_id=order_id, user_id=user_id)
        
        db_data = await db_get_user(user_id)
        balance = db_data.get("balance", 0.0) if db_data else 0.0
        
        m = Msg()
        m.emoji("check").text(" ").bold("Wallet Top-Up Successful!").nl(2)
        m.emoji("balance").text(" Amount Credited: ").bold(f"Br {amount_to_credit:,.2f}").nl()
        m.emoji("wallet").text(" Updated Balance: ").bold(f"Br {balance:,.2f}").nl()
        if ref:
            m.emoji("key").text(" Transaction ID: ").code(ref.upper()).nl()
        m.nl()
        m.italic("Your balance is ready for instant 1-click purchases in the shop!")
        t, ent = m.build()
        
        await send_msg(user_id, t, ent,
            keyboard=build_keyboard([
                [btn("🛒 Go to Shop", "shop", emoji_key="shop", style="success")],
                [btn("💳 My Wallet", "wallet", emoji_key="wallet")],
            ])
        )
        
        for adm in ADMINS:
            try:
                await send_msg(adm, f"💰 *Wallet Top-Up Approved*\nUser: `{user_id}`\nAmount: *Br {amount_to_credit:,.2f}*\nRef: `{ref or order.get('screenshot_file_id', 'N/A')}`")
            except Exception:
                pass
        return True

    # 2. Product Purchase Fulfillment
    cat_id = order.get("cat_id")
    cats = _load_categories()
    cat = cats.get(cat_id, {})
    quantity = max(1, int(order.get("quantity", 1)))
    unit_price = float(order.get("unit_price", order["price"] / quantity))
    total_price = float(order["price"])
    cat_name = order.get("cat_name", "Product")
    
    sp_id = cat.get("safwan_product_id")
    delivered_contents = []
    
    if sp_id and SAFWAN_API_KEY:
        try:
            res = await safwan_order(product_id=sp_id, quantity=quantity)
            logger.info(f"[fulfill_order_auto] Safwan order response for order #{order_id}: {res}")
            if isinstance(res, dict) and res.get("ok"):
                order_obj = res.get("order") if isinstance(res.get("order"), dict) else {}
                
                # Check list fields across order object and root
                items = (
                    order_obj.get("items") or 
                    res.get("items") or 
                    order_obj.get("accounts") or 
                    res.get("accounts") or 
                    order_obj.get("codes") or 
                    res.get("codes") or 
                    res.get("data") or 
                    []
                )
                
                if isinstance(items, list):
                    for a in items:
                        if isinstance(a, dict):
                            val = a.get("content") or a.get("code") or a.get("link") or a.get("account") or a.get("item") or json.dumps(a)
                            delivered_contents.append(str(val).strip())
                        elif isinstance(a, str) and a.strip():
                            delivered_contents.append(a.strip())
                        elif a is not None:
                            delivered_contents.append(str(a).strip())
                elif isinstance(items, str) and items.strip():
                    delivered_contents.append(items.strip())
                
                # Check single item fields
                if not delivered_contents:
                    single = (
                        order_obj.get("code") or 
                        res.get("code") or 
                        order_obj.get("content") or 
                        res.get("content") or 
                        order_obj.get("link") or 
                        res.get("link")
                    )
                    if single:
                        delivered_contents.append(str(single).strip())
            else:
                logger.warning(f"[fulfill_order_auto] Safwan order returned non-ok: {res}")
        except Exception as ex:
            logger.error(f"[fulfill_order_auto] Safwan order failed: {ex}")
            
    if not delivered_contents:
        # Local stock fulfillment
        popped_items = await stock_pop_multiple(cat_id, quantity)
        for it in popped_items:
            if isinstance(it, dict):
                c = it.get("content", "") or it.get("code", "") or it.get("link", "")
                if c:
                    delivered_contents.append(str(c).strip())
            elif isinstance(it, str) and it.strip():
                delivered_contents.append(it.strip())
                
    await db_record_purchase(user_id, total_price)
    item_label = f"{cat_name} (x{quantity})" if quantity > 1 else cat_name
    
    if not delivered_contents:
        # Product requires manual admin link/credentials input!
        await order_set_status(order_id, "awaiting_delivery")
        
        # 1. Notify Customer that order is confirmed and waiting for admin link delivery
        cm = Msg()
        cm.emoji("check").text(" ").bold("Order Confirmed & Payment Received!").nl(2)
        cm.emoji("cart").text(" Product: ").bold(item_label).nl()
        cm.emoji("balance").text(" Amount Paid: ").bold(f"Br {total_price:,.2f}").nl()
        cm.emoji("key").text(" Order ID: ").code(f"#{order_id[:8].upper()}").nl(2)
        cm.emoji("timer").text(" ").bold("Delivery in Progress:").nl()
        cm.italic("Your product requires manual link activation. Our administrator is preparing your activation link and will deliver it directly to you here in this chat shortly.").nl(2)
        cm.emoji("star").text(" Thank you for your patience!").nl()
        ct, cent = cm.build()
        await send_msg(user_id, ct, cent, keyboard=build_keyboard([
            [btn("💬 Message Support", url=SUPPORT_LINK, emoji_key="support")],
            [btn("🏠 Main Menu", "back_main", emoji_key="back")],
        ]))
        
        # 2. Notify Admins with interactive [Send Activation Link] button
        buyer_info = await db_get_user(user_id)
        buyer_name = buyer_info.get("first_name", "Customer") if buyer_info else "Customer"
        buyer_uname = f"@{buyer_info.get('username')}" if buyer_info and buyer_info.get("username") else f"ID: {user_id}"
        
        adm_m = Msg()
        adm_m.emoji("thunder").text(" ").bold("Manual Delivery Required!").nl(2)
        adm_m.emoji("cart").text(f" Product: {item_label}\n")
        adm_m.emoji("balance").text(f" Amount Paid: Br {total_price:,.2f}\n")
        adm_m.emoji("user").text(f" Customer: {buyer_name} ({buyer_uname})\n")
        adm_m.emoji("key").text(f" Order ID: ").code(f"#{order_id[:8].upper()}").nl(2)
        adm_m.emoji("link").text(" ").italic("This product does not have auto-delivery API. Tap the button below to input and send the activation link to the customer:")
        adm_t, adm_ent = adm_m.build()
        
        adm_kb = build_keyboard([
            [btn("🔗 Send Activation Link", f"deliver_{order_id}", emoji_key="channel", style="success")],
        ])
        for adm in ADMINS:
            try:
                await send_msg(adm, adm_t, adm_ent, keyboard=adm_kb)
            except Exception as ex:
                logger.warning(f"[fulfill_order_auto] Failed to notify admin {adm}: {ex}")
        return True

    # Automated delivery branch (Safwan API or local stock)
    await post_sale_log(item_label, total_price, "purchase", order_id=order_id, user_id=user_id)
    
    m = Msg()
    m.emoji("check").text(" ").bold("Order Completed & Delivered!").nl(2)
    m.emoji("cart").text(" Product: ").bold(item_label).nl()
    m.emoji("balance").text(" Total Price: ").bold(f"Br {total_price:,.2f}").nl()
    if quantity > 1:
        m.emoji("box").text(" Quantity: ").bold(f"{quantity} units").nl()
    m.nl()
    
    delivery_buttons = []
    if len(delivered_contents) == 1:
        item_val = delivered_contents[0]
        is_url = item_val.startswith(("http://", "https://", "t.me/"))
        title_text = "Your Activation Link:" if is_url else "Your Account / Code Details:"
        m.emoji("key").text(" ").bold(title_text).nl()
        m.code(item_val).nl(2)
        if is_url:
            full_url = item_val if item_val.startswith(("http://", "https://")) else f"https://{item_val}"
            m.italic("Tap the button below or copy the link to activate your subscription!").nl(2)
            delivery_buttons.append([btn("🔗 Open Activation Link", url=full_url, emoji_key="channel", style="success")])
    else:
        m.emoji("key").text(" ").bold(f"Your Delivered Items ({len(delivered_contents)} items):").nl()
        for idx, c in enumerate(delivered_contents, 1):
            m.bold(f"{idx}️⃣ Item #{idx}:").nl()
            m.code(c).nl()
        m.nl()
        
    m.emoji("thunder").text(" ").italic("Thank you for shopping with ET Market!")
    t, ent = m.build()
    
    delivery_buttons.append([btn("🛒 Shop More", "shop", emoji_key="shop", style="success" if not delivery_buttons else None)])
    delivery_buttons.append([btn("🏠 Home", "back_main", emoji_key="back")])
    
    await send_msg(user_id, t, ent, keyboard=build_keyboard(delivery_buttons))
    
    for adm in ADMINS:
        try:
            await send_msg(adm, f"🛍️ *Product Order Fulfilled*\nProduct: *{item_label}*\nUser: `{user_id}`\nQuantity: *{quantity}*\nTotal: *Br {total_price:,.2f}*")
        except Exception:
            pass
    return True

async def process_giveaway_claim(chat_id, user: dict, gw_id: str):
    """Process a giveaway claim via /start gw_xxxx link."""
    is_winner, gw = await giveaway_claim_atomic(gw_id, user)
    if "error" in gw:
        await send_msg(chat_id, "❌ Giveaway not found or has expired.")
        return
    
    cat_name = gw.get("cat_name", "Product")
    if is_winner:
        cat_id = gw.get("cat_id")
        item = await stock_pop(cat_id) if cat_id else None
        if item:
            item_text = item.get("account_data", item.get("text", str(item))) if isinstance(item, dict) else str(item)
            m = Msg()
            m.emoji("pop").text(" ").bold("Congratulations! You won the giveaway!").nl(2)
            m.emoji("shop").text(" Product: ").bold(cat_name).nl()
            m.emoji("key").text(" Your Account/Key:").nl()
            m.code(item_text).nl(2)
            m.text("Thank you for participating in our giveaway!")
            t, ent = m.build()
            await send_msg(chat_id, t, ent, kb_main(user.get("id")))
        else:
            m = Msg()
            m.emoji("pop").text(" ").bold("Congratulations! You won the giveaway!").nl(2)
            m.emoji("shop").text(" Product: ").bold(cat_name).nl()
            m.text("Please contact support @et_market_place to claim your prize.")
            t, ent = m.build()
            await send_msg(chat_id, t, ent, kb_main(user.get("id")))
    else:
        winner = gw.get("winner_username", "another user")
        m = Msg()
        m.emoji("timer").text(" ").bold("Giveaway Already Claimed!").nl(2)
        m.text(f"This giveaway for ").bold(cat_name).text(f" was already claimed by {winner}.").nl(2)
        m.text("Stay tuned in our official channel for the next giveaway!")
        t, ent = m.build()
        await send_msg(chat_id, t, ent, kb_main(user.get("id")))

async def process_inbot_giveaway_claim(chat_id, user: dict, gw_id: str, cq_id: str = None, mid: int = None):
    """Process an in-bot button giveaway claim."""
    real_id = f"gw_{gw_id}" if not gw_id.startswith("gw_") else gw_id
    is_winner, gw = await giveaway_claim_atomic(real_id, user)
    if "error" in gw:
        if cq_id:
            await answer_cb(cq_id, "❌ Giveaway not found or expired.", alert=True)
        return
    
    cat_name = gw.get("cat_name", "Product")
    if is_winner:
        if cq_id:
            await answer_cb(cq_id, "🎉 CONGRATULATIONS! You won the giveaway!", alert=True)
        if mid:
            try:
                await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
            except Exception:
                pass
        
        cat_id = gw.get("cat_id")
        item = await stock_pop(cat_id) if cat_id else None
        if item:
            item_text = item.get("account_data", item.get("text", str(item))) if isinstance(item, dict) else str(item)
            m = Msg()
            m.emoji("pop").text(" ").bold("Congratulations! You won the giveaway!").nl(2)
            m.emoji("shop").text(" Product: ").bold(cat_name).nl()
            m.emoji("key").text(" Your Account/Key:").nl()
            m.code(item_text).nl(2)
            m.text("Thank you for participating!")
            t, ent = m.build()
            await send_msg(chat_id, t, ent, kb_main(user.get("id")))
        else:
            m = Msg()
            m.emoji("pop").text(" ").bold("Congratulations! You won the giveaway!").nl(2)
            m.emoji("shop").text(" Product: ").bold(cat_name).nl()
            m.text("Please contact support @et_market_place to claim your prize.")
            t, ent = m.build()
            await send_msg(chat_id, t, ent, kb_main(user.get("id")))
    else:
        winner = gw.get("winner_username", "another user")
        if cq_id:
            await answer_cb(cq_id, f"⚡ Too late! Claimed by {winner}.", alert=True)
        if mid:
            try:
                await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
            except Exception:
                pass
        m = Msg()
        m.emoji("timer").text(" ").bold("Giveaway Already Claimed!").nl(2)
        m.text(f"This giveaway for ").bold(cat_name).text(f" was already claimed by {winner}.").nl(2)
        m.text("Stay tuned for future giveaways!")
        t, ent = m.build()
        await send_msg(chat_id, t, ent, kb_main(user.get("id")))

# ─── HANDLERS ─────────────────────────────────────────────────

async def _handle_admin_state(chat_id, user_id, text: str, message: dict) -> bool:
    """
    Handle multi-step admin conversations.
    Returns True if the message was consumed by an admin flow.
    """
    global VERIFY_ET_API_KEY
    state = _admin_state.get(user_id)
    if not state:
        return False

    step = state.get("step")

    # ── /addcategory & ➕ Add Product flow ──────────────────────
    if step == "addcat_name":
        clean_name = text.strip()
        if not clean_name:
            await send_msg(chat_id, "❌ Product name cannot be empty. Please enter the name (or /cancel):")
            return True
        if clean_name.lower() in ("/cancel", "cancel"):
            _admin_state.pop(user_id, None)
            cats = await cat_get_all()
            counts = await get_all_stock_counts(cats)
            await send_msg(chat_id, "❌ Product creation cancelled.", keyboard=kb_admin_products(cats, counts))
            return True
            
        state["data"]["name"] = clean_name
        state["step"] = "addcat_price"
        await send_msg(chat_id,
            f"💰 *Step 2/4: Set Price for {clean_name}*\n\n"
            f"Enter the price in ETB (e.g. `250` or `1499.99`):",
            keyboard=build_keyboard([[btn("Cancel", "admin_products", emoji_key="cross")]])
        )
        return True

    if step == "addcat_price":
        if text.strip().lower() in ("/cancel", "cancel"):
            _admin_state.pop(user_id, None)
            cats = await cat_get_all()
            counts = await get_all_stock_counts(cats)
            await send_msg(chat_id, "❌ Product creation cancelled.", keyboard=kb_admin_products(cats, counts))
            return True
            
        try:
            price = float(text.strip().replace(",", ""))
            if price <= 0:
                raise ValueError
        except ValueError:
            await send_msg(chat_id, "❌ Invalid price. Enter a positive number (e.g. 500):")
            return True
            
        state["data"]["price"] = price
        state["step"] = "addcat_emoji"
        await send_msg(chat_id,
            "✨ *Step 3/4: Send Product Emoji / Premium Icon*\n\n"
            "Send ANY of the following:\n"
            "• A **Telegram Premium custom emoji** from your emoji keyboard\n"
            "• A standard emoji (e.g. 🍿, 🎬, 💎, ⚡, 🤖, 🛒)\n"
            "• A custom emoji sticker\n"
            "• A numeric Custom Emoji ID\n\n"
            "Or choose a preset below:",
            keyboard=build_keyboard([
                [btn("🍿 Cinema", "admin_addcat_preset_emoji_🍿"),
                 btn("💎 Premium", "admin_addcat_preset_emoji_💎"),
                 btn("⚡ Fast", "admin_addcat_preset_emoji_⚡")],
                [btn("🤖 AI Tool", "admin_addcat_preset_emoji_🤖"),
                 btn("🛒 Market", "admin_addcat_preset_emoji_🛒"),
                 btn("Skip (🛒 Default)", "admin_addcat_preset_emoji_🛒")],
                [btn("Cancel", "admin_products", emoji_key="cross")]
            ])
        )
        return True

    if step == "addcat_emoji":
        if text.strip().lower() in ("/cancel", "cancel"):
            _admin_state.pop(user_id, None)
            cats = await cat_get_all()
            counts = await get_all_stock_counts(cats)
            await send_msg(chat_id, "❌ Product creation cancelled.", keyboard=kb_admin_products(cats, counts))
            return True

        sticker = message.get("sticker")
        emoji_char = "🛒"
        emoji_id = ""

        if sticker:
            emoji_id = str(sticker.get("custom_emoji_id") or "")
            emoji_char = sticker.get("emoji") or "⭐"
        else:
            entities = message.get("entities") or []
            for ent in entities:
                if ent.get("type") == "custom_emoji":
                    emoji_id = str(ent.get("custom_emoji_id", ""))
                    offset = ent.get("offset", 0)
                    length = ent.get("length", 1)
                    try:
                        raw = text.encode("utf-16-le")
                        emoji_char = raw[offset*2 : (offset+length)*2].decode("utf-16-le")
                    except Exception:
                        emoji_char = "⭐"
                    break

            if not emoji_id:
                clean_text = text.strip()
                if clean_text.lower() in ("skip", "-", "—", "default", "none"):
                    emoji_char = "🛒"
                    emoji_id = ""
                elif clean_text.isdigit() and len(clean_text) >= 10:
                    emoji_id = clean_text
                    emoji_char = "⭐"
                elif clean_text:
                    emoji_char = clean_text[:4]
                    emoji_id = ""

        state["data"]["emoji_char"] = emoji_char
        state["data"]["emoji_id"]   = emoji_id
        state["step"] = "addcat_type"

        m = Msg()
        m.emoji("check").text(" ").bold("Product Icon Selected: ")
        if emoji_id:
            m.custom_emoji(emoji_char, emoji_id).text(f" (Premium ID: `{emoji_id}`)\n\n")
        else:
            m.text(f"{emoji_char}\n\n")
        m.bold("Step 4/4: Select Delivery Type:\n\n")
        m.text("🔗 Link — Admin uploads activation links or invite URLs.\n")
        m.text("🔐 ID & Pass — Admin uploads email:password account credentials.")
        t, ent = m.build()
        await send_msg(chat_id, t, ent, keyboard=build_keyboard([
            [btn("🔗 Link", "admincat_type_link"),
             btn("🔐 ID & Pass", "admincat_type_id_pass")],
            [btn("Cancel", "admin_products", emoji_key="cross")]
        ]))
        return True

    if step == "addcat_type":
        await send_msg(chat_id,
            "⬆️ Please tap a button above to choose the delivery type (Link or ID & Pass):",
            keyboard=build_keyboard([
                [btn("🔗 Link", "admincat_type_link"),
                 btn("🔐 ID & Pass", "admincat_type_id_pass")],
                [btn("Cancel", "admin_products", emoji_key="cross")]
            ])
        )
        return True

    if step == "addcat_safwan":
        if text.strip().lower() in ("/cancel", "cancel"):
            _admin_state.pop(user_id, None)
            cats = await cat_get_all()
            counts = await get_all_stock_counts(cats)
            await send_msg(chat_id, "❌ Cancelled.", keyboard=kb_admin_products(cats, counts))
            return True
        val = text.strip()
        sp_id = None
        if val not in ("0", "skip", "-", "—", "none", ""):
            try:
                sp_id = int(val)
            except ValueError:
                await send_msg(chat_id, "❌ Invalid ID. Enter a numeric Safwan Product ID or send 0 to skip:")
                return True
        state["data"]["safwan_id"] = sp_id
        state["step"] = "addcat_desc"
        await send_msg(chat_id,
            "📝 *Enter Product Description:*\n\n"
            "Send the description to display on the customer product card.\n"
            "Supports multiple lines, formatting, and Telegram Premium custom emojis!\n\n"
            "Send *skip* or *—* to skip description.",
            keyboard=build_keyboard([[btn("Skip Description", "admin_addcat_skip_desc")]])
        )
        return True

    if step == "addcat_desc":
        if text.strip().lower() in ("/cancel", "cancel"):
            _admin_state.pop(user_id, None)
            cats = await cat_get_all()
            counts = await get_all_stock_counts(cats)
            await send_msg(chat_id, "❌ Cancelled.", keyboard=kb_admin_products(cats, counts))
            return True

        desc = text.strip()
        if desc.lower() in ("-", "—", "skip", "none"):
            desc = ""
            desc_entities = []
        else:
            entities = message.get("entities") or []
            desc_entities = [
                dict(e) for e in entities
                if e.get("type") in ("custom_emoji", "bold", "italic", "underline", "strikethrough", "code", "text_link")
            ]

        state["data"]["description"] = desc
        state["data"]["desc_entities"] = desc_entities
        state["step"] = "addcat_confirm"

        d = state["data"]
        type_label = "🔗 Link" if d.get("cat_type") == "link" else "🔐 ID & Pass"
        
        m = Msg()
        m.emoji("star").text(" ").bold("Confirm New Product").nl()
        m.text("━━━━━━━━━━━━━━━━━━━━").nl()
        m.text("• Icon: ")
        if d.get("emoji_id"):
            m.custom_emoji(d.get("emoji_char", "🛒"), d["emoji_id"]).text(f" (Premium ID: `{d['emoji_id']}`)\n")
        else:
            m.text(f"{d.get('emoji_char', '🛒')}\n")
        m.text("• Name: ").bold(d["name"]).nl()
        m.text("• Price: ").bold(f"Br {d['price']:,.2f}").nl()
        m.text("• Type: ").bold(type_label).nl()
        if d.get("safwan_id"):
            m.text("• Safwan Supplier ID: ").code(str(d["safwan_id"])).nl()
        m.text("━━━━━━━━━━━━━━━━━━━━").nl()
        if desc:
            m.bold("Description Preview:").nl()
            if desc_entities:
                m.raw_with_entities(desc, desc_entities).nl(2)
            else:
                m.italic(desc).nl(2)
        m.text("━━━━━━━━━━━━━━━━━━━━").nl()
        m.italic("Tap Confirm below to save the product to the store:")
        t, ent = m.build()
        await send_msg(chat_id, t, ent, keyboard=build_keyboard([
            [btn("✅ Confirm & Save Product", "admin_addcat_confirm", emoji_key="check", style="success")],
            [btn("❌ Cancel", "admin_products", emoji_key="cross")],
        ]))
        return True

    if step == "addcat_confirm":
        if text.strip().upper() in ("YES", "Y", "CONFIRM"):
            d = state["data"]
            cat_id = d["name"].lower().replace(" ", "_")
            await cat_save(cat_id, d["name"], d["price"],
                           d.get("emoji_char", "🛒"), d.get("emoji_id", ""),
                           d.get("cat_type", "id_pass"),
                           d.get("description", ""),
                           d.get("desc_entities", []))
            if d.get("safwan_id"):
                async with _cat_lock:
                    all_cats = _load_categories()
                    if cat_id in all_cats:
                        all_cats[cat_id]["safwan_product_id"] = d["safwan_id"]
                        _save_categories(all_cats)
            _admin_state.pop(user_id, None)
            cats = await cat_get_all()
            counts = await get_all_stock_counts(cats)
            card_text, card_ent = build_admin_product_card(cats.get(cat_id, {}), 0)
            
            m = Msg()
            m.emoji("check").text(" ").bold(f"Product {d['name']} added successfully!").nl(2)
            m.text(card_text)
            full_t, base_ent = m.build()
            prefix_len = u16(full_t) - u16(card_text)
            merged_ent = base_ent + [dict(e, offset=e['offset'] + prefix_len) for e in card_ent]
            await send_msg(chat_id, full_t, merged_ent, keyboard=kb_admin_product_detail(cat_id))
        else:
            _admin_state.pop(user_id, None)
            cats = await cat_get_all()
            counts = await get_all_stock_counts(cats)
            await send_msg(chat_id, "❌ Cancelled. Product was not added.", keyboard=kb_admin_products(cats, counts))
        return True

    # ── /addstock flow ─────────────────────────────────────────
    if step == "addstock_pick":
        # Expect admin to type category name or number shown in list
        cats = _load_categories()
        cat_list = list(cats.values())
        try:
            idx = int(text.strip()) - 1
            if idx < 0 or idx >= len(cat_list):
                raise ValueError
            chosen = cat_list[idx]
        except ValueError:
            # Try matching by name
            chosen = next(
                (c for c in cat_list
                 if c["name"].lower() == text.strip().lower()), None)
        if not chosen:
            await send_msg(chat_id,
                "❌ Category not found. Send the number from the list:")
            return True
        state["data"]["cat_id"]   = chosen["id"]
        state["data"]["cat_name"] = chosen["name"]
        state["data"]["cat_type"] = chosen.get("cat_type", "id_pass")
        state["step"] = "addstock_count"

        current = await stock_get_count(chosen["id"])
        cat_type  = chosen.get("cat_type", "id_pass")
        type_label = "🔗 Link" if cat_type == "link" else "🔐 ID & Pass"
        await send_msg(chat_id,
            f"📦 *{chosen['name']}* ({type_label})\n"
            f"Current stock: {current}\n\n"
            f"How many items are available? (Enter a number)\n"
            f"Example: 10")
        return True

    if step == "addstock_count":
        try:
            count = int(text.strip())
            if count < 0:
                raise ValueError
        except ValueError:
            await send_msg(chat_id, "❌ Enter a valid number (0 or more):")
            return True

        cat_id   = state["data"]["cat_id"]
        cat_name = state["data"]["cat_name"]
        await stock_set_count(cat_id, count)
        del _admin_state[user_id]

        # Post to log channel
        cats = _load_categories()
        cat  = cats.get(cat_id)
        if cat and count > 0:
            await post_stock_log(cat_name, count, cat_id)

        await send_msg(chat_id,
            f"✅ Stock for *{cat_name}* set to *{count}*.")
        return True

        cat_type = chosen.get("cat_type", "id_pass")
        if cat_type == "link":
            await send_msg(chat_id,
                f"🔗 Adding links to *{chosen['name']}*\n\n"
                "Send activation links one per line.\n"
                "Each line = one link (full URL).\n\n"
                "Example:\n"
                "https://t.me/+abcxyz123\n"
                "https://example.com/activate?code=xyz\n\n"
                "When done, send DONE.")
        else:
            await send_msg(chat_id,
                f"🔐 Adding accounts to *{chosen['name']}*\n\n"
                "Send accounts one per line in this format:\n"
                "`email:password`\n\n"
                "When done, send DONE.")
        return True

    if step == "addstock_items":
        if text.strip().upper() == "DONE":
            items    = state["data"]["items"]
            cat_name = state["data"]["cat_name"]
            cat_id   = state["data"]["cat_id"]
            cat_type = state["data"].get("cat_type", "id_pass")
            if items:
                await stock_add(cat_id, items)
                del _admin_state[user_id]
                label = "link(s)" if cat_type == "link" else "account(s)"
                await send_msg(chat_id,
                    f"✅ Added {len(items)} {label} to *{cat_name}*.")
            else:
                del _admin_state[user_id]
                await send_msg(chat_id, "❌ No items added. Cancelled.")
            return True

        # Parse lines based on category type
        cat_type = state["data"].get("cat_type", "id_pass")
        added  = 0
        errors = 0

        if cat_type == "link":
            for line in text.strip().splitlines():
                line = line.strip()
                if line.startswith("http://") or line.startswith("https://") or line.startswith("t.me"):
                    state["data"]["items"].append({"link": line})
                    added += 1
                elif line:
                    errors += 1
            msg_parts = [f"🔗 {added} link(s) received."]
        else:
            for line in text.strip().splitlines():
                line = line.strip()
                if ":" in line:
                    parts = line.split(":", 1)
                    state["data"]["items"].append({
                        "email":    parts[0].strip(),
                        "password": parts[1].strip(),
                    })
                    added += 1
                elif line:
                    errors += 1
            msg_parts = [f"➕ {added} account(s) received."]

        if errors:
            msg_parts.append(f"⚠️ {errors} line(s) skipped (bad format).")
        msg_parts.append("Send more or type DONE to finish.")
        await send_msg(chat_id, "\n".join(msg_parts))
        return True

    # ── /deletecategory flow ───────────────────────────────────
    if step == "delcat_pick":
        cats = _load_categories()
        cat_list = list(cats.values())
        try:
            idx = int(text.strip()) - 1
            if idx < 0 or idx >= len(cat_list):
                raise ValueError
            chosen = cat_list[idx]
        except ValueError:
            chosen = next(
                (c for c in cat_list
                 if c["name"].lower() == text.strip().lower()), None)
        if not chosen:
            await send_msg(chat_id,
                "❌ Category not found. Send the number from the list:")
            return True
        state["data"]["cat_id"]   = chosen["id"]
        state["data"]["cat_name"] = chosen["name"]
        state["step"] = "delcat_confirm"
        await send_msg(chat_id,
            f"⚠️ Are you sure you want to DELETE *{chosen['name']}*?\n"
            "This will remove the category AND all its stock.\n\n"
            "Reply YES to confirm or NO to cancel.")
        return True

    if step == "delcat_confirm":
        if text.strip().upper() == "YES":
            cat_name = state["data"]["cat_name"]
            cat_id   = state["data"]["cat_id"]
            await cat_delete(cat_id)
            del _admin_state[user_id]
            await send_msg(chat_id,
                f"✅ Category *{cat_name}* and its stock have been deleted.")
        else:
            del _admin_state[user_id]
            await send_msg(chat_id, "❌ Cancelled. Category was not deleted.")
        return True

    # ── deliver_link flow (after approving link-type order) ───
    if step == "deliver_link":
        d        = state["data"]
        order_id = d["order_id"]
        buyer_id = d["buyer_id"]
        cat_name = d["cat_name"]

        if text and text.strip().lower() in ("/cancel", "cancel"):
            del _admin_state[user_id]
            await send_msg(chat_id, "❌ Delivery cancelled.", keyboard=kb_admin_panel())
            return True

        link = text.strip()
        if not (link.startswith("http") or link.startswith("t.me") or link.startswith("tg://") or "/" in link or "." in link):
            await send_msg(chat_id,
                "❌ That doesn't look like a valid link. Send a URL (e.g. https://... or t.me/...) or type /cancel to abort:")
            return True

        del _admin_state[user_id]

        # Update order in database
        order = await order_get(order_id)
        if order:
            async with _ord_lock:
                all_orders = _load_orders()
                if order_id in all_orders:
                    all_orders[order_id]["status"] = "approved"
                    all_orders[order_id]["delivery_content"] = link
                    all_orders[order_id]["delivered_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    _save_orders(all_orders)

        # Build and send delivery card to buyer
        dm = Msg()
        dm.emoji("check").text(" ").bold("Your Product is Ready & Delivered!").nl(2)
        dm.emoji("cart").text(" Product: ").bold(cat_name).nl()
        if order:
            dm.emoji("balance").text(" Amount Paid: ").bold(f"Br {order['price']:,.2f}").nl()
        dm.emoji("key").text(" Order ID: ").code(f"#{order_id[:8].upper()}").nl(2)
        dm.emoji("link").text(" ").bold("Your Activation Link / Access:").nl()
        dm.code(link).nl(2)
        dm.italic("Tap the button below or copy the link to access and activate your subscription!").nl(2)
        dm.emoji("thunder").text(" Thank you for shopping with ").bold("ET Market").text("!")
        deliver_text, deliver_ent = dm.build()

        kb_rows = []
        full_url = link if link.startswith(("http://", "https://")) else (f"https://{link}" if link.startswith("t.me/") else None)
        if full_url:
            kb_rows.append([btn("🔗 Open Activation Link", url=full_url, emoji_key="channel", style="success")])
        kb_rows.append([btn("🛒 Shop More", "shop", emoji_key="shop", style="success" if not full_url else None)])
        kb_rows.append([btn("🏠 Main Menu", "back_main", emoji_key="back")])

        await send_msg(buyer_id, deliver_text, deliver_ent, keyboard=build_keyboard(kb_rows))

        # Notify admin of successful delivery
        adm_resp = Msg()
        adm_resp.emoji("check").text(" ").bold("Product Link Delivered Successfully!").nl(2)
        adm_resp.emoji("cart").text(f" Product: {cat_name}\n")
        adm_resp.emoji("user").text(f" Customer: ").code(str(buyer_id)).nl()
        adm_resp.emoji("link").text(f" Link Sent: ").code(link).nl(2)
        adm_resp.italic("The customer has received their activation link and buttons in their chat.")
        adm_t, adm_ent = adm_resp.build()
        await send_msg(chat_id, adm_t, adm_ent, keyboard=kb_admin_panel())

        # Post sale log
        if order:
            await post_sale_log(cat_name, float(order.get('price', 0.0)), "purchase", order_id=order_id, user_id=buyer_id)
        return True

    # ── deliver_creds flow (after approving id_pass order) ────
    if step == "deliver_creds":
        d        = state["data"]
        order_id = d["order_id"]
        buyer_id = d["buyer_id"]
        cat_name = d["cat_name"]

        if text and text.strip().lower() in ("/cancel", "cancel"):
            del _admin_state[user_id]
            await send_msg(chat_id, "❌ Delivery cancelled.", keyboard=kb_admin_panel())
            return True

        line = text.strip()
        if ":" not in line:
            await send_msg(chat_id,
                "❌ Invalid format. Send credentials as:\n`email:password` (or type /cancel to abort):")
            return True

        parts    = line.split(":", 1)
        email    = parts[0].strip()
        password = parts[1].strip()

        del _admin_state[user_id]

        # Update order in database
        order = await order_get(order_id)
        if order:
            async with _ord_lock:
                all_orders = _load_orders()
                if order_id in all_orders:
                    all_orders[order_id]["status"] = "approved"
                    all_orders[order_id]["delivery_content"] = f"{email}:{password}"
                    all_orders[order_id]["delivered_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    _save_orders(all_orders)

        # Build and send delivery card to buyer
        dm = Msg()
        dm.emoji("check").text(" ").bold("Your Product is Ready & Delivered!").nl(2)
        dm.emoji("cart").text(" Product: ").bold(cat_name).nl()
        if order:
            dm.emoji("balance").text(" Amount Paid: ").bold(f"Br {order['price']:,.2f}").nl()
        dm.emoji("key").text(" Order ID: ").code(f"#{order_id[:8].upper()}").nl(2)
        dm.emoji("box").text(" ").bold("Your Account Credentials:").nl()
        dm.text("Email: ").code(email).nl()
        dm.emoji("key").text(" Password: ").code(password).nl(2)
        dm.italic("Use the credentials above to log in to your account!").nl(2)
        dm.emoji("thunder").text(" Thank you for shopping with ").bold("ET Market").text("!")
        deliver_text, deliver_ent = dm.build()
        await send_msg(buyer_id, deliver_text, deliver_ent,
            keyboard=build_keyboard([
                [btn("🛒 Shop More", "shop", emoji_key="shop", style="success")],
                [btn("🏠 Main Menu", "back_main", emoji_key="back")],
            ]))

        # Notify admin
        adm_resp = Msg()
        adm_resp.emoji("check").text(" ").bold("Account Credentials Delivered!").nl(2)
        adm_resp.emoji("cart").text(f" Product: {cat_name}\n")
        adm_resp.emoji("user").text(f" Customer: ").code(str(buyer_id)).nl()
        adm_resp.emoji("key").text(f" Credentials: ").code(f"{email}:{password}").nl(2)
        adm_resp.italic("The customer has received their login credentials in their chat.")
        adm_t, adm_ent = adm_resp.build()
        await send_msg(chat_id, adm_t, adm_ent, keyboard=kb_admin_panel())

        # Post sale log
        if order:
            await post_sale_log(cat_name, float(order.get('price', 0.0)), "purchase", order_id=order_id, user_id=buyer_id)
        return True

    # ── updateprice flow ───────────────────────────────────────
    if step == "updateprice_pick":
        cats     = _load_categories()
        cat_list = list(cats.values())
        try:
            idx = int(text.strip()) - 1
            if idx < 0 or idx >= len(cat_list):
                raise ValueError
            chosen = cat_list[idx]
        except ValueError:
            chosen = next(
                (c for c in cat_list
                 if c["name"].lower() == text.strip().lower()), None)
        if not chosen:
            await send_msg(chat_id,
                "❌ Category not found. Send the number from the list:")
            return True
        state["data"]["cat_id"]   = chosen["id"]
        state["data"]["cat_name"] = chosen["name"]
        state["data"]["old_price"] = chosen["price"]
        state["step"] = "updateprice_value"
        await send_msg(chat_id,
            f"💰 *{chosen['name']}*\n"
            f"Current price: Br {chosen['price']:.2f}\n\n"
            f"Enter the new price (ETB):")
        return True

    if step == "updateprice_value":
        try:
            new_price = float(text.strip())
            if new_price <= 0:
                raise ValueError
        except ValueError:
            await send_msg(chat_id, "❌ Invalid price. Enter a positive number:")
            return True

        cat_id    = state["data"]["cat_id"]
        cat_name  = state["data"]["cat_name"]
        old_price = state["data"]["old_price"]

        async with _cat_lock:
            data = _load_categories()
            if cat_id in data:
                data[cat_id]["price"] = new_price
                _save_categories(data)

        del _admin_state[user_id]
        await send_msg(chat_id,
            f"✅ Price updated!\n\n"
            f"{cat_name}\n"
            f"Old: Br {old_price:.2f} → New: Br {new_price:.2f}")
        return True

    # ── admin_broadcast_msg flow ──────────────────────────────
    if step == "admin_broadcast_msg":
        if text and text.strip().lower() == "/cancel":
            _admin_state.pop(user_id, None)
            await send_msg(chat_id, "❌ Broadcast cancelled.", keyboard=kb_admin_panel())
            return True

        _admin_state.pop(user_id, None)
        users = _load_db()
        total = len(users)
        success = 0
        failed = 0
        
        status_msg = await send_msg(chat_id, f"📢 Broadcasting to {total} users... please wait a moment.")
        status_mid = status_msg.get("result", {}).get("message_id") if status_msg.get("ok") else None
        
        photo_list = message.get("photo")
        if photo_list:
            file_id = photo_list[-1]["file_id"]
            caption = message.get("caption", "") or ""
            cap_entities = message.get("caption_entities")
            for uid in users.keys():
                try:
                    payload = {"chat_id": int(uid), "photo": file_id}
                    if caption:
                        payload["caption"] = caption
                    if cap_entities:
                        payload["caption_entities"] = cap_entities
                    res = await api_call("sendPhoto", payload)
                    if res.get("ok"):
                        success += 1
                    else:
                        failed += 1
                    await asyncio.sleep(0.04)
                except Exception:
                    failed += 1
        else:
            bc_text = text or message.get("text", "")
            entities = message.get("entities")
            for uid in users.keys():
                try:
                    res = await send_msg(int(uid), bc_text, entities=entities)
                    if res.get("ok"):
                        success += 1
                    else:
                        failed += 1
                    await asyncio.sleep(0.04)
                except Exception:
                    failed += 1
                    
        res_text = (
            f"📢 Broadcast Report:\n\n"
            f"✅ Successfully Delivered: {success}\n"
            f"❌ Failed / Blocked: {failed}\n"
            f"👥 Total Targeted: {total}"
        )
        if status_mid:
            await api_call("deleteMessage", {"chat_id": chat_id, "message_id": status_mid})
        await send_msg(chat_id, res_text, keyboard=kb_admin_panel())
        return True

    # ── admin_user_lookup flow ────────────────────────────────
    if step == "admin_user_lookup":
        if text.strip().lower() == "/cancel":
            del _admin_state[user_id]
            await send_msg(chat_id, "❌ User search cancelled.", keyboard=kb_admin_panel())
            return True

        query = text.strip().lstrip("@")
        users = _load_db()
        found_user = None
        found_uid = None
        for uid, u in users.items():
            if uid == query or (u.get("username", "").lower() == query.lower()):
                found_user = u
                found_uid = uid
                break
        
        del _admin_state[user_id]
        if not found_user:
            await send_msg(chat_id, f"❌ User '{query}' not found in database.", keyboard=kb_admin_panel())
            return True
        
        m = Msg()
        m.emoji("user").text(" ").bold("Customer Profile Card").nl(2)
        m.text(f"• ID: `{found_uid}`\n")
        m.text(f"• Name: {found_user.get('first_name','')}\n")
        m.text(f"• Username: @{found_user.get('username','none')}\n")
        m.emoji("balance").text(f"  Balance: ").bold(f"Br {found_user.get('balance', 0.0):.2f}").nl()
        m.emoji("cart").text(f"  Total Spent: ").bold(f"Br {found_user.get('total_spent', 0.0):.2f}").nl()
        m.emoji("box").text(f"  Products Bought: ").bold(f"{found_user.get('products_bought', 0)}").nl()
        m.text(f"• Joined: {found_user.get('joined_at','N/A')}\n\n")
        m.italic("Use quick buttons below to adjust balance:")
        t, ent = m.build()
        
        kb = build_keyboard([
            [btn("➕ Add Br 100", f"admgive_{found_uid}_100"),
             btn("➕ Add Br 500", f"admgive_{found_uid}_500")],
            [btn("➕ Add Br 1000", f"admgive_{found_uid}_1000"),
             btn("➖ Reset to 0", f"admresetbal_{found_uid}")],
            [btn("Back to Admin Panel", "admin_panel", emoji_key="back")]
        ])
        await send_msg(chat_id, t, ent, kb)
        return True

    # ── admin_editname_quick flow ─────────────────────────────
    if step == "admin_editname_quick":
        cat_id = state["data"]["cat_id"]
        cat_name = state["data"]["cat_name"]
        if text.strip().lower() in ("/cancel", "cancel"):
            del _admin_state[user_id]
            cats = _load_categories()
            cnt = await stock_count(cat_id)
            card_text, card_ent = build_admin_product_card(cats.get(cat_id, {}), cnt)
            await send_msg(chat_id, "❌ Name edit cancelled.", keyboard=kb_admin_product_detail(cat_id))
            return True

        new_name = text.strip()
        if len(new_name) < 2 or len(new_name) > 100:
            await send_msg(chat_id, "❌ Name must be between 2 and 100 characters. Enter a valid name (or /cancel):")
            return True

        async with _cat_lock:
            cats = _load_categories()
            if cat_id in cats:
                cats[cat_id]["name"] = new_name
                _save_categories(cats)
        del _admin_state[user_id]

        cnt = await stock_count(cat_id)
        cats = _load_categories()
        card_text, card_ent = build_admin_product_card(cats[cat_id], cnt)
        t, ent = merge_with_prefix(f"✅ Product name updated to *{new_name}*!\n\n", card_text, card_ent)
        await send_msg(chat_id, t, ent, keyboard=kb_admin_product_detail(cat_id))
        return True

    # ── admin_editemoji_quick flow ────────────────────────────
    if step == "admin_editemoji_quick":
        cat_id = state["data"]["cat_id"]
        cat_name = state["data"]["cat_name"]
        if text.strip().lower() in ("/cancel", "cancel"):
            del _admin_state[user_id]
            cats = _load_categories()
            cnt = await stock_count(cat_id)
            card_text, card_ent = build_admin_product_card(cats.get(cat_id, {}), cnt)
            await send_msg(chat_id, "❌ Icon edit cancelled.", keyboard=kb_admin_product_detail(cat_id))
            return True

        sticker = message.get("sticker")
        emoji_char = "🛒"
        emoji_id = ""

        if sticker:
            emoji_id = str(sticker.get("custom_emoji_id") or "")
            emoji_char = sticker.get("emoji") or "⭐"
        else:
            entities = message.get("entities") or []
            for ent in entities:
                if ent.get("type") == "custom_emoji":
                    emoji_id = str(ent.get("custom_emoji_id", ""))
                    offset = ent.get("offset", 0)
                    length = ent.get("length", 1)
                    try:
                        raw = text.encode("utf-16-le")
                        emoji_char = raw[offset*2 : (offset+length)*2].decode("utf-16-le")
                    except Exception:
                        emoji_char = "⭐"
                    break

            if not emoji_id:
                clean_text = text.strip()
                if clean_text.lower() in ("default", "none"):
                    emoji_char = "🛒"
                    emoji_id = ""
                elif clean_text.isdigit() and len(clean_text) >= 10:
                    emoji_id = clean_text
                    emoji_char = "⭐"
                elif clean_text in UNICODE_TO_CUSTOM_EMOJI:
                    emoji_char = clean_text
                    emoji_id = UNICODE_TO_CUSTOM_EMOJI[clean_text]
                elif clean_text:
                    emoji_char = clean_text[:4]
                    emoji_id = ""

        async with _cat_lock:
            cats = _load_categories()
            if cat_id in cats:
                cats[cat_id]["emoji_char"] = emoji_char
                cats[cat_id]["emoji_id"] = emoji_id
                _save_categories(cats)
        del _admin_state[user_id]

        cnt = await stock_count(cat_id)
        cats = _load_categories()
        card_text, card_ent = build_admin_product_card(cats[cat_id], cnt)
        t, ent = merge_with_prefix(f"✅ Product icon updated!\n\n", card_text, card_ent)
        await send_msg(chat_id, t, ent, keyboard=kb_admin_product_detail(cat_id))
        return True

    # ── admin_editprice_quick flow ────────────────────────────
    if step == "admin_editprice_quick":
        cat_id = state["data"]["cat_id"]
        cat_name = state["data"]["cat_name"]
        if text.strip().lower() == "/cancel":
            del _admin_state[user_id]
            await send_msg(chat_id, "❌ Price edit cancelled.", keyboard=kb_admin_product_detail(cat_id))
            return True

        try:
            new_price = float(text.strip())
            if new_price <= 0:
                raise ValueError
        except ValueError:
            await send_msg(chat_id, "❌ Invalid price. Enter a positive number:")
            return True
        
        async with _cat_lock:
            cats = _load_categories()
            if cat_id in cats:
                cats[cat_id]["price"] = new_price
                _save_categories(cats)
        del _admin_state[user_id]
        
        cnt = await stock_count(cat_id)
        cats = _load_categories()
        card_text, card_ent = build_admin_product_card(cats[cat_id], cnt)
        t, ent = merge_with_prefix(f"✅ Price for *{cat_name}* updated to *Br {new_price:.2f}*!\n\n", card_text, card_ent)
        await send_msg(chat_id, t, ent, keyboard=kb_admin_product_detail(cat_id))
        return True

    # ── admin_editstock_quick flow ────────────────────────────
    if step == "admin_editstock_quick":
        cat_id = state["data"]["cat_id"]
        cat_name = state["data"]["cat_name"]
        if text.strip().lower() == "/cancel":
            del _admin_state[user_id]
            await send_msg(chat_id, "❌ Stock edit cancelled.", keyboard=kb_admin_product_detail(cat_id))
            return True

        try:
            new_count = int(text.strip())
            if new_count < 0:
                raise ValueError
        except ValueError:
            await send_msg(chat_id, "❌ Invalid quantity. Enter 0 or more:")
            return True
        
        await stock_set_count(cat_id, new_count)
        del _admin_state[user_id]
        
        cats = _load_categories()
        card_text, card_ent = build_admin_product_card(cats[cat_id], new_count)
        t, ent = merge_with_prefix(f"✅ Stock for *{cat_name}* updated to *{new_count}*!\n\n", card_text, card_ent)
        await send_msg(chat_id, t, ent, keyboard=kb_admin_product_detail(cat_id))
        return True

    # ── admin_link_safwan flow ────────────────────────────────
    if step == "admin_link_safwan":
        cat_id = state["data"]["cat_id"]
        cat_name = state["data"]["cat_name"]
        if text.strip().lower() == "/cancel":
            del _admin_state[user_id]
            await send_msg(chat_id, "❌ Cancelled.", keyboard=kb_admin_product_detail(cat_id))
            return True

        val = text.strip()
        try:
            sp_id = int(val)
        except ValueError:
            await send_msg(chat_id, "❌ Invalid Product ID. Enter a number (e.g. 1 for Gemini, 53 for Canva, or 0 to unlink):")
            return True

        async with _cat_lock:
            cats = _load_categories()
            if cat_id in cats:
                if sp_id > 0:
                    cats[cat_id]["safwan_product_id"] = sp_id
                else:
                    cats[cat_id].pop("safwan_product_id", None)
                _save_categories(cats)
        del _admin_state[user_id]

        cnt = await stock_count(cat_id)
        cats = _load_categories()
        card_text, card_ent = build_admin_product_card(cats[cat_id], cnt)
        status_msg = f"linked to SafwanTiger Product #{sp_id}" if sp_id > 0 else "unlinked from SafwanTiger API"
        t, ent = merge_with_prefix(f"✅ *{cat_name}* {status_msg}!\n\n", card_text, card_ent)
        await send_msg(chat_id, t, ent, keyboard=kb_admin_product_detail(cat_id))
        return True

    # ── admin_set_vet_key flow ────────────────────────────────
    if step in ("admin_set_verify_key", "admin_set_vet_key"):
        if text.strip().lower() == "/cancel":
            del _admin_state[user_id]
            await send_msg(chat_id, "❌ Cancelled.", keyboard=kb_admin_settings())
            return True
        key = text.strip()
        del _admin_state[user_id]
        set_env_setting("VERIFY_ET_API_KEY", key)
        t, ent = await build_admin_settings_screen()
        full_t, full_ent = merge_with_prefix("✅ *Verify.ET API Key updated and saved to .env!*\n\n", t, ent)
        await send_msg(chat_id, full_t, full_ent, keyboard=kb_admin_settings())
        return True

    # ── admin_set_safwan_key flow ─────────────────────────────
    if step == "admin_set_safwan_key":
        if text.strip().lower() == "/cancel":
            del _admin_state[user_id]
            await send_msg(chat_id, "❌ Cancelled.", keyboard=kb_admin_settings())
            return True
        key = text.strip()
        del _admin_state[user_id]
        set_env_setting("SAFWAN_API_KEY", key)
        t, ent = await build_admin_settings_screen()
        full_t, full_ent = merge_with_prefix("✅ *SafwanTiger API Key updated and saved to .env!*\n\n", t, ent)
        await send_msg(chat_id, full_t, full_ent, keyboard=kb_admin_settings())
        return True

    # ── admin_set_log_ch flow ─────────────────────────────────
    if step == "admin_set_log_ch":
        if text.strip().lower() == "/cancel":
            del _admin_state[user_id]
            await send_msg(chat_id, "❌ Cancelled.", keyboard=kb_admin_settings())
            return True
        val = text.strip()
        try:
            ch_id = int(val)
        except ValueError:
            await send_msg(chat_id, "❌ Invalid Channel ID. It should be a number (e.g. -1003806764959):")
            return True
        del _admin_state[user_id]
        set_env_setting("LOG_CHANNEL_ID", str(ch_id))
        t, ent = await build_admin_settings_screen()
        full_t, full_ent = merge_with_prefix(f"✅ *Sales Log Channel updated to `{ch_id}` and saved to .env!*\n\n", t, ent)
        await send_msg(chat_id, full_t, full_ent, keyboard=kb_admin_settings())
        return True

    # ── admin_set_fj_id flow ──────────────────────────────────
    if step == "admin_set_fj_id":
        if text.strip().lower() == "/cancel":
            del _admin_state[user_id]
            await send_msg(chat_id, "❌ Cancelled.", keyboard=kb_admin_settings())
            return True
        val = text.strip()
        try:
            ch_id = int(val)
        except ValueError:
            await send_msg(chat_id, "❌ Invalid Channel ID. It should be a number (e.g. -1002205327334):")
            return True
        del _admin_state[user_id]
        set_env_setting("FORCE_JOIN_CHANNEL_ID", str(ch_id))
        t, ent = await build_admin_settings_screen()
        full_t, full_ent = merge_with_prefix(f"✅ *Force Join Channel ID updated to `{ch_id}` and saved to .env!*\n\n", t, ent)
        await send_msg(chat_id, full_t, full_ent, keyboard=kb_admin_settings())
        return True

    # ── admin_set_fj_link flow ────────────────────────────────
    if step == "admin_set_fj_link":
        if text.strip().lower() == "/cancel":
            del _admin_state[user_id]
            await send_msg(chat_id, "❌ Cancelled.", keyboard=kb_admin_settings())
            return True
        link = text.strip()
        if not (link.startswith("http://") or link.startswith("https://") or link.startswith("t.me/")):
            await send_msg(chat_id, "❌ Invalid link format. Must start with https://t.me/...")
            return True
        del _admin_state[user_id]
        set_env_setting("FORCE_JOIN_CHANNEL_LINK", link)
        t, ent = await build_admin_settings_screen()
        full_t, full_ent = merge_with_prefix(f"✅ *Force Join Link updated to {link} and saved to .env!*\n\n", t, ent)
        await send_msg(chat_id, full_t, full_ent, keyboard=kb_admin_settings())
        return True

    # ── admin_set_telebirr flows ──────────────────────────────
    if step == "admin_set_telebirr_name":
        if text.strip().lower() == "/cancel":
            del _admin_state[user_id]
            await send_msg(chat_id, "❌ Cancelled.", keyboard=kb_admin_settings())
            return True
        name = text.strip()
        state["data"]["name"] = name
        state["step"] = "admin_set_telebirr_acc"
        await send_msg(chat_id, f"✅ Name set to: *{name}*\n\n📱 Now send the Telebirr Account Number (e.g. 0967979014):")
        return True

    if step == "admin_set_telebirr_acc":
        if text.strip().lower() == "/cancel":
            del _admin_state[user_id]
            await send_msg(chat_id, "❌ Cancelled.", keyboard=kb_admin_settings())
            return True
        acc = text.strip()
        name = state["data"]["name"]
        del _admin_state[user_id]
        set_env_setting("PAYMENT_NAME", name)
        set_env_setting("PAYMENT_ACCOUNT", acc)
        t, ent = await build_admin_settings_screen()
        full_t, full_ent = merge_with_prefix(f"✅ *Telebirr details updated ({name} / {acc}) and saved to .env!*\n\n", t, ent)
        await send_msg(chat_id, full_t, full_ent, keyboard=kb_admin_settings())
        return True

    # ── admin_set_cbe flows ───────────────────────────────────
    if step == "admin_set_cbe_name":
        if text.strip().lower() == "/cancel":
            del _admin_state[user_id]
            await send_msg(chat_id, "❌ Cancelled.", keyboard=kb_admin_settings())
            return True
        name = text.strip()
        state["data"]["name"] = name
        state["step"] = "admin_set_cbe_acc"
        await send_msg(chat_id, f"✅ CBE Name set to: *{name}*\n\n🏦 Now send the CBE Account Number (e.g. 1000424161075):")
        return True

    if step == "admin_set_cbe_acc":
        if text.strip().lower() == "/cancel":
            del _admin_state[user_id]
            await send_msg(chat_id, "❌ Cancelled.", keyboard=kb_admin_settings())
            return True
        acc = text.strip()
        name = state["data"]["name"]
        del _admin_state[user_id]
        set_env_setting("CBE_NAME", name)
        set_env_setting("CBE_ACCOUNT", acc)
        t, ent = await build_admin_settings_screen()
        full_t, full_ent = merge_with_prefix(f"✅ *CBE details updated ({name} / {acc}) and saved to .env!*\n\n", t, ent)
        await send_msg(chat_id, full_t, full_ent, keyboard=kb_admin_settings())
        return True

    # ── admin_set_cbebirr flows ───────────────────────────────
    if step == "admin_set_cbebirr_name":
        if text.strip().lower() == "/cancel":
            del _admin_state[user_id]
            await send_msg(chat_id, "❌ Cancelled.", keyboard=kb_admin_settings())
            return True
        name = text.strip()
        state["data"]["name"] = name
        state["step"] = "admin_set_cbebirr_acc"
        await send_msg(chat_id, f"✅ CBE Birr Name set to: *{name}*\n\n🏦 Now send the CBE Birr Phone Number (e.g. 0967979014):")
        return True

    if step == "admin_set_cbebirr_acc":
        if text.strip().lower() == "/cancel":
            del _admin_state[user_id]
            await send_msg(chat_id, "❌ Cancelled.", keyboard=kb_admin_settings())
            return True
        acc = text.strip()
        name = state["data"]["name"]
        del _admin_state[user_id]
        set_env_setting("CBEBIRR_NAME", name)
        set_env_setting("CBEBIRR_ACCOUNT", acc)
        t, ent = await build_admin_settings_screen()
        full_t, full_ent = merge_with_prefix(f"✅ *CBE Birr details updated ({name} / {acc}) and saved to .env!*\n\n", t, ent)
        await send_msg(chat_id, full_t, full_ent, keyboard=kb_admin_settings())
        return True

    # ── admin_set_admins flow ─────────────────────────────────
    if step == "admin_set_admins":
        if text.strip().lower() == "/cancel":
            del _admin_state[user_id]
            await send_msg(chat_id, "❌ Cancelled.", keyboard=kb_admin_settings())
            return True
        ids_raw = text.strip()
        parsed = [int(x.strip()) for x in ids_raw.replace(" ", "").split(",") if x.strip().isdigit()]
        if not parsed:
            await send_msg(chat_id, "❌ Invalid input. Please send comma-separated Telegram user IDs (e.g. 6241860023, 8708984302):")
            return True
        if user_id not in parsed:
            parsed.append(user_id)  # Never lock self out
        del _admin_state[user_id]
        val_str = ",".join(str(x) for x in parsed)
        set_env_setting("ADMINS", val_str)
        t, ent = await build_admin_settings_screen()
        full_t, full_ent = merge_with_prefix(f"✅ *Admin user IDs updated ({val_str}) and saved to .env!*\n\n", t, ent)
        await send_msg(chat_id, full_t, full_ent, keyboard=kb_admin_settings())
        return True

    # ── admtxt_input custom message editing flow ──────────────
    if step == "admtxt_input":
        key = state.get("data", {}).get("key")
        info = RESPONSE_TEMPLATES.get(key, {"name": key})
        
        if text and text.strip().lower() in ("/cancel", "cancel"):
            _admin_state.pop(user_id, None)
            t, ent = build_admin_custom_texts_menu()
            full_t, full_ent = merge_with_prefix("❌ Edit cancelled.\n\n", t, ent)
            await send_msg(chat_id, full_t, full_ent, kb_admin_custom_texts())
            return True
            
        if text and text.strip().lower() in ("/reset", "reset"):
            _admin_state.pop(user_id, None)
            await reset_custom_response(key)
            t, ent = build_admin_custom_texts_menu()
            full_t, full_ent = merge_with_prefix(f"✅ *{info['name']}* has been reset to default!\n\n", t, ent)
            await send_msg(chat_id, full_t, full_ent, kb_admin_custom_texts())
            return True

        msg_text = message.get("text") or text or ""
        msg_entities = message.get("entities") or []
        
        if not msg_text.strip():
            await send_msg(chat_id, "❌ Message cannot be empty. Please send the new text, or type /cancel to abort:")
            return True

        await set_custom_response(key, msg_text, msg_entities)
        _admin_state.pop(user_id, None)

        sample_ctx = {
            "user": "Abebe Kebede",
            "name": "Abebe Kebede",
            "username": "@abebe_k",
            "id": str(user_id),
            "uid": str(user_id),
            "balance": "Br 1,250.00",
            "amount": "500.00",
            "title": "Telebirr Top Up",
            "product_name": "Telegram Premium (1 Year)",
            "account": PAYMENT_ACCOUNT,
            "expiry": str(ORDER_EXPIRY_MINUTES),
            "channel_name": FORCE_JOIN_CHANNEL_NAME,
            "channel_link": FORCE_JOIN_CHANNEL_LINK,
            "support_link": SUPPORT_LINK,
            "dev_link": DEVELOPER_LINK,
        }
        prev_text, prev_ent = render_text_template(msg_text, msg_entities, sample_ctx)

        m = Msg()
        m.emoji("check").text(" ").bold(f"Successfully updated {info['name']}!").nl()
        m.text("━━━━━━━━━━━━━━━━━━━━").nl()
        m.bold("Live Preview:").nl(2)
        m.text(prev_text)
        t, ent = m.build()
        merged_ent = ent + [dict(e, offset=e['offset'] + u16(t) - u16(prev_text)) for e in prev_ent]

        kb = build_keyboard([
            [btn("Edit Again", f"admtxt_edit_{key}", emoji_key="other"),
             btn("Reset to Default", f"admtxt_reset_{key}", emoji_key="cross")],
            [btn("Custom Messages Menu", "admin_custom_texts", emoji_key="back"),
             btn("Admin Panel", "admin_panel", emoji_key="crown")],
        ])
        await send_msg(chat_id, t, merged_ent, kb)
        return True

    return False


async def handle_message(msg: dict):
    global VERIFY_ET_API_KEY
    chat_id = msg["chat"]["id"]
    user    = msg.get("from", {})
    user_id = user.get("id")
    text    = msg.get("text", "") or ""

    # Save / update user in DB on every message
    await db_upsert_user(user)

    # ── Force Join check (skip for admins) ────────────────────
    if not is_admin(user_id):
        is_member = await check_membership(user_id)
        if not is_member:
            await send_join_prompt(chat_id)
            return
        
        # Check terms acceptance
        db_data = await db_get_user(user_id)
        terms_accepted = db_data.get("terms_accepted", False) if db_data else False
        if not terms_accepted:
            t, ent = build_terms()
            await send_msg(chat_id, t, ent,
                keyboard=build_keyboard([
                    [btn("I Agree", "accept_terms", emoji_key="check", style="success")],
                    [btn("Decline", "decline_terms", emoji_key="cross")],
                ])
            )
            return

    # ── Admin multi-step state ─────────────────────────────────
    if is_admin(user_id):
        consumed = await _handle_admin_state(chat_id, user_id, text, msg)
        if consumed:
            return

    # ── Payment Reference Number & Verify.ET Automated Verification Handler ────
    if user_id in _awaiting_screenshot:
        order_id = _awaiting_screenshot.get(user_id)
        order = await order_get(order_id) if order_id else None
        
        if not order or order["status"] not in ("pending_payment", "pending_approval"):
            _awaiting_screenshot.pop(user_id, None)
            await send_msg(chat_id, "❌ This order is no longer active. Please start a new order.")
            return

        # Check if user typed cancel
        if text and text.lower() in ("/cancel", "cancel", "❌ cancel", "exit"):
            _awaiting_screenshot.pop(user_id, None)
            await order_set_status(order_id, "cancelled")
            if order.get("order_type") == "topup":
                db_data = await db_get_user(user_id)
                balance = db_data.get("balance", 0.0) if db_data else 0.0
                t, ent = build_wallet(balance)
                full_t, full_ent = merge_with_prefix("❌ Top-up cancelled.\n\n", t, ent)
                await send_msg(chat_id, full_t, full_ent, keyboard=kb_wallet())
            else:
                await send_msg(chat_id, "❌ Order cancelled.\n\nYou can browse the shop anytime.",
                    keyboard=build_keyboard([
                        [btn("Back to Shop", "shop", emoji_key="back")],
                        [btn("Home", "back_main", emoji_key="back")],
                    ])
                )
            return

        input_text = text.strip() if text else (msg.get("caption", "") or "").strip()
        order_method = order.get("payment_method", "")
        
        if not input_text and msg.get("photo"):
            hint_text = "CBE Birr Transaction ID (e.g. `1029384756` or `REC12345`) or paste the SMS text from CBE Birr (889)" if order_method == "cbebirr" else "Telebirr Transaction ID (e.g. `TRA12345678` or `DGJBFFH`) or paste the SMS text from Telebirr (127)"
            await send_msg(chat_id,
                f"📸 Please enter your **{hint_text}** to verify automatically:\n\n"
                "(Or tap Cancel below to cancel this order)",
                keyboard=build_keyboard([[btn("❌ Cancel Order", f"cancel_{order_id}", emoji_key="cross")]])
            )
            return

        cbe_ref = extract_cbe_reference(input_text)
        cbebirr_ref = extract_cbebirr_reference(input_text)
        telebirr_ref = extract_telebirr_reference(input_text)
        
        if order_method == "cbebirr":
            ref = cbebirr_ref or telebirr_ref or cbe_ref
            bank = "cbebirr"
        elif order_method == "cbe" or (cbe_ref and cbe_ref.startswith("FT")):
            ref = cbe_ref or telebirr_ref or cbebirr_ref
            bank = "cbe"
        else:
            ref = telebirr_ref or cbebirr_ref or cbe_ref
            bank = "telebirr"

        if not ref:
            hint_text = "CBE Birr Transaction ID (e.g. `1029384756` or `REC12345`) or paste the full SMS from 889" if order_method == "cbebirr" else "Telebirr Transaction ID (e.g. `TRA12345678` or `DGJBFFH`) or paste the full SMS from 127"
            await send_msg(chat_id,
                f"❌ Could not find a valid Transaction Reference Number in your message.\n\n"
                f"Please enter your **{hint_text}**:",
                keyboard=build_keyboard([[btn("❌ Cancel Order", f"cancel_{order_id}", emoji_key="cross")]])
            )
            return

        clean_ref = ref.strip().upper()
        
        # Check for duplicate transaction reference
        if is_reference_used(clean_ref):
            await send_msg(chat_id,
                f"❌ **Duplicate Transaction Reference**\n\n"
                f"• Reference: `{clean_ref}`\n"
                f"• Error: This transaction ID has already been used and claimed for another order!\n\n"
                f"Please enter a new, unused Transaction ID:\n"
                f"(Or tap Cancel below to abort)",
                keyboard=build_keyboard([[btn("❌ Cancel Order", f"cancel_{order_id}", emoji_key="cross")]])
            )
            return

        # Perform instant automated verification with Verify.ET
        wait_msg = await send_msg(chat_id, f"⚡ Verifying transaction `{clean_ref}` with Verify.ET in real time...")
        wait_mid = wait_msg.get("result", {}).get("message_id") if wait_msg.get("ok") else None
        
        vet_res = await vet_verify(bank, clean_ref)
        if not vet_res.get("verified") and bank in ("telebirr", "cbebirr"):
            alt_bank = "cbebirr" if bank == "telebirr" else "telebirr"
            alt_res = await vet_verify(alt_bank, clean_ref)
            if alt_res.get("verified"):
                vet_res = alt_res
                bank = alt_bank
        
        if wait_mid:
            try:
                await api_call("deleteMessage", {"chat_id": chat_id, "message_id": wait_mid})
            except Exception:
                pass

        if vet_res.get("verified"):
            v_amount = float(vet_res.get("amount", 0.0) or 0.0)
            if v_amount >= order["price"]:
                _awaiting_screenshot.pop(user_id, None)
                await fulfill_order_auto(order_id, v_amount, vet_res.get("sender", ""), ref=clean_ref)
                return
            else:
                # Underpaid
                await send_msg(chat_id,
                    f"⚠️ **Amount Mismatch (Underpaid)**\n\n"
                    f"• Verified Amount: *Br {v_amount:,.2f}*\n"
                    f"• Required Order Amount: *Br {order['price']:,.2f}*\n\n"
                    f"Please check your transaction or pay the remaining amount and send the reference again:",
                    keyboard=build_keyboard([[btn("❌ Cancel Order", f"cancel_{order_id}", emoji_key="cross")]])
                )
                return
        else:
            err = vet_res.get("error") or "Transaction not found or not settled yet with bank"
            await send_msg(chat_id,
                f"❌ **Payment Verification Failed**\n\n"
                f"• Reference: `{clean_ref}`\n"
                f"• Reason: *{err}*\n\n"
                f"💡 *Tip: If you just completed the payment, please wait 15–30 seconds for the bank to process, then send the reference number again below:*",
                keyboard=build_keyboard([[btn("❌ Cancel Order", f"cancel_{order_id}", emoji_key="cross")]])
            )
            return

    # ── Top-up amount input handler ────────────────────────────
    if user_id in _awaiting_topup_amount:
        if text.lower() in ("/cancel", "cancel", "❌ cancel", "exit"):
            _awaiting_topup_amount.pop(user_id, None)
            db_data = await db_get_user(user_id)
            balance = db_data.get("balance", 0.0) if db_data else 0.0
            t, ent = build_wallet(balance)
            full_t, full_ent = merge_with_prefix("❌ Top-up cancelled.\n\n", t, ent)
            await send_msg(chat_id, full_t, full_ent, kb_wallet())
            return
        
        cleaned_text = re.sub(r'(?i)(br|etb|birr|\s|,)', '', text.strip())
        try:
            amount = float(cleaned_text)
        except ValueError:
            await send_msg(chat_id,
                "❌ Please enter a valid number (e.g. `500` or `1000`).\n\nOr click Cancel below:",
                keyboard=build_keyboard([[btn("❌ Cancel", "wallet")]])
            )
            return
        
        if amount < 1.0:
            await send_msg(chat_id,
                "⚠️ Minimum top-up amount is *Br 1.00*.\nPlease enter an amount of 1 or more:",
                keyboard=build_keyboard([[btn("❌ Cancel", "wallet")]])
            )
            return
            
        if amount > 500000:
            await send_msg(chat_id,
                "⚠️ Maximum single top-up amount is *Br 500,000.00*.\nPlease enter a lower amount:",
                keyboard=build_keyboard([[btn("❌ Cancel", "wallet")]])
            )
            return
            
        _awaiting_topup_amount.pop(user_id, None)
        await start_topup_order(chat_id, user_id, amount)
        return

    # ── Custom Product Quantity Input ──────────────────────────
    if user_id in _awaiting_qty_input:
        if text.startswith("/cancel"):
            cid = _awaiting_qty_input.pop(user_id, {}).get("cat_id")
            cats = _load_categories()
            cat = cats.get(cid)
            if cat:
                count = await stock_count(cid)
                t, ent = build_cat_detail(cat, count, qty=1)
                kb = kb_cat_detail(cid, count, qty=1)
                await send_msg(chat_id, t, ent, kb)
            else:
                await send_welcome_screen(chat_id, user)
            return
            
        qty_info = _awaiting_qty_input.get(user_id, {})
        cid = qty_info.get("cat_id")
        prompt_mid = qty_info.get("mid")
        cats = _load_categories()
        cat = cats.get(cid)
        if not cat:
            _awaiting_qty_input.pop(user_id, None)
            await send_msg(chat_id, "❌ Product not found.")
            return
            
        count = await stock_count(cid)
        try:
            qty = int(text.strip())
        except ValueError:
            qty = 0
            
        if qty < 1 or qty > count:
            await send_msg(chat_id,
                f"⚠️ *Invalid Quantity!*\nPlease enter a valid number between *1* and *{count}* (or /cancel):",
                keyboard=build_keyboard([[btn("Cancel", f"cat_{cid}", emoji_key="cross")]])
            )
            return
            
        _awaiting_qty_input.pop(user_id, None)
        t, ent = build_cat_detail(cat, count, qty=qty)
        kb = kb_cat_detail(cid, count, qty=qty)
        
        if prompt_mid:
            try:
                await api_call("deleteMessage", {"chat_id": chat_id, "message_id": prompt_mid})
            except Exception:
                pass
        await send_msg(chat_id, t, ent, kb)
        return

    # ── Admin commands ─────────────────────────────────────────
    if text == "/addcategory":
        if not is_admin(user_id):
            await send_msg(chat_id, "⛔ You are not authorized.")
            return
        _admin_state[user_id] = {"step": "addcat_name", "data": {}}
        await send_msg(chat_id, "📝 Enter the category name:")
        return

    if text == "/addstock":
        if not is_admin(user_id):
            await send_msg(chat_id, "⛔ You are not authorized.")
            return
        cats = _load_categories()
        if not cats:
            await send_msg(chat_id, "❌ No categories yet. Use /addcategory first.")
            return
        lines = ["📦 Select a category (send its number):\n"]
        for i, cat in enumerate(cats.values(), 1):
            count      = await stock_count(cat["id"])
            cat_type   = cat.get("cat_type", "id_pass")
            type_label = "🔗" if cat_type == "link" else "🔐"
            lines.append(f"{i}. {cat.get('emoji_char','🛒')} {cat['name']}"
                         f" — Br {cat['price']:.2f}  |  {type_label}  |  Stock: {count}")
        _admin_state[user_id] = {"step": "addstock_pick", "data": {}}
        await send_msg(chat_id, "\n".join(lines))
        return

    if text == "/deletecategory":
        if not is_admin(user_id):
            await send_msg(chat_id, "⛔ You are not authorized.")
            return
        cats = _load_categories()
        if not cats:
            await send_msg(chat_id, "❌ No categories to delete.")
            return
        lines = ["🗑️ Select a category to DELETE (send its number):\n"]
        for i, cat in enumerate(cats.values(), 1):
            count = await stock_count(cat["id"])
            lines.append(f"{i}. {cat.get('emoji_char','🛒')} {cat['name']}"
                         f" — Br {cat['price']:.2f}  |  Stock: {count}")
        _admin_state[user_id] = {"step": "delcat_pick", "data": {}}
        await send_msg(chat_id, "\n".join(lines))
        return

    if text == "/updateprice":
        if not is_admin(user_id):
            await send_msg(chat_id, "⛔ You are not authorized.")
            return
        cats = _load_categories()
        if not cats:
            await send_msg(chat_id, "❌ No categories yet. Use /addcategory first.")
            return
        lines = ["💰 Select a category to update its price (send its number):\n"]
        for i, cat in enumerate(cats.values(), 1):
            lines.append(f"{i}. {cat.get('emoji_char','🛒')} {cat['name']}"
                         f" — Br {cat['price']:.2f}")
        _admin_state[user_id] = {"step": "updateprice_pick", "data": {}}
        await send_msg(chat_id, "\n".join(lines))
        return

    if text in ("/admin", "/panel"):
        if not is_admin(user_id):
            await send_msg(chat_id, "⛔ You are not authorized.")
            return
        t, ent = await build_admin_dashboard()
        await send_msg(chat_id, t, ent, kb_admin_panel())
        return

    if text in ("/broadcast", "/announce"):
        if not is_admin(user_id):
            await send_msg(chat_id, "⛔ You are not authorized.")
            return
        _admin_state[user_id] = {"step": "admin_broadcast_msg", "data": {}}
        await send_msg(chat_id,
            "📢 Send the announcement message to broadcast to all customers:\n\n"
            "(Supports text, markdown, links. Type /cancel to abort.)",
            keyboard=build_keyboard([[btn("Cancel", "admin_panel", emoji_key="cross")]])
        )
        return

    if text.startswith("/give"):
        if not is_admin(user_id):
            await send_msg(chat_id, "⛔ You are not authorized.")
            return
        parts = text.strip().split()
        if len(parts) < 3:
            await send_msg(chat_id, "Usage: `/give <user_id_or_username> <amount>`\nExample: `/give 6241860023 500`")
            return
        target = parts[1].lstrip("@")
        try:
            amount = float(parts[2])
        except ValueError:
            await send_msg(chat_id, "❌ Invalid amount.")
            return
        
        users = _load_db()
        target_uid = None
        for uid, u in users.items():
            if uid == target or u.get("username", "").lower() == target.lower():
                target_uid = uid
                break
        
        if not target_uid:
            await send_msg(chat_id, f"❌ User '{target}' not found in database.")
            return
        
        await db_add_balance(target_uid, amount)
        users = _load_db()
        new_bal = users.get(target_uid, {}).get("balance", 0.0)
        
        try:
            action_word = "credited" if amount >= 0 else "deducted"
            um = Msg()
            um.emoji("wallet").text(f" Your account balance was {action_word} ").bold(f"Br {abs(amount):.2f}").nl()
            um.emoji("balance").text(f" New Balance: ").bold(f"Br {new_bal:.2f}")
            ut, ue = um.build()
            await send_msg(int(target_uid), ut, ue)
        except Exception:
            pass
        
        await send_msg(chat_id, f"✅ Adjusted balance for `{target_uid}` by *Br {amount:.2f}*.\nNew Balance: *Br {new_bal:.2f}*")
        return

    if text == "/users":
        if not is_admin(user_id):
            await send_msg(chat_id, "⛔ You are not authorized.")
            return
        users = _load_db()
        lines = [f"👥 Total Customers: {len(users)}\n\nRecent 10 Customers:"]
        for uid, u in list(reversed(list(users.items())))[:10]:
            lines.append(f"• `{uid}` (@{u.get('username','none')}) — Bal: Br {u.get('balance',0):.2f} | Spent: Br {u.get('total_spent',0):.2f}")
        await send_msg(chat_id, "\n".join(lines), keyboard=kb_admin_panel())
        return

    if text.startswith("/setverifykey"):
        if not is_admin(user_id):
            await send_msg(chat_id, "⛔ You are not authorized.")
            return
        parts = text.strip().split(maxsplit=1)
        if len(parts) < 2:
            await send_msg(chat_id, "Usage: `/setverifykey <YOUR_VERIFY_ET_API_KEY>`")
            return
        VERIFY_ET_API_KEY = parts[1].strip()
        os.environ["VERIFY_ET_API_KEY"] = VERIFY_ET_API_KEY
        await send_msg(chat_id, "✅ *Verify.ET API Key updated successfully!*\n\nAutomated 24/7 payment verification is now *ACTIVE 🟢*.", keyboard=kb_admin_panel())
        return

    # ── Regular commands & Button actions ───────────────────────
    if text.startswith("/start") or text in ("/home", "/menu", "🏠 Main Menu", "🏠 Home", "Main Menu", "Home", "Menu"):
        parts = text.split()
        if len(parts) > 1 and parts[1].startswith("gw_"):
            gw_id = parts[1]
            await process_giveaway_claim(chat_id, user, gw_id)
            return
        elif len(parts) > 1 and parts[1].startswith("ref_"):
            referrer_id = parts[1][4:].strip()
            if referrer_id and referrer_id != str(user_id):
                async with _db_lock:
                    db = _load_db()
                    cur_u = db.get(str(user_id), {})
                    if not cur_u.get("referred_by"):
                        cur_u["referred_by"] = referrer_id
                        db[str(user_id)] = cur_u
                        if referrer_id in db:
                            db[referrer_id]["referrals_count"] = int(db[referrer_id].get("referrals_count", 0) or 0) + 1
                        _save_db(db)
        await send_welcome_screen(chat_id, user)

    elif text == "/giveaway" and is_admin(user_id):
        cats = await cat_get_all()
        t, ent = build_admin_giveaway_select(cats)
        kb = kb_admin_giveaway_select(cats)
        await send_msg(chat_id, t, ent, kb)

    elif text.startswith("/search") or text.startswith("/find"):
        parts = text.split(maxsplit=1)
        if len(parts) > 1 and parts[1].strip():
            query = parts[1].strip()
            cats = await cat_get_all()
            matched = search_products(query, cats)
            counts = await get_all_stock_counts(matched)
            if matched:
                t, ent = build_search_results_screen(query, len(matched))
                kb = kb_search_results(matched, counts)
                await send_msg(chat_id, t, ent, kb)
            else:
                m = Msg()
                m.emoji("cross").text(" ").bold("No products found").nl()
                m.text("━━━━━━━━━━━━━━━━━━━━").nl()
                m.text("No products matched: ").code(query).nl(2)
                m.italic("💡 Try searching with different keywords or check your regex pattern.").nl()
                t, ent = m.build()
                kb = build_keyboard([
                    [btn("🔍 Search Again", "shop_search"),
                     btn("🛍️ All Products", "shop")]
                ])
                await send_msg(chat_id, t, ent, kb)
        else:
            _awaiting_search[user_id] = True
            t, ent = build_search_prompt_screen()
            kb = build_keyboard([[btn("Back to Products", "shop", emoji_key="back")]])
            await send_msg(chat_id, t, ent, kb)

    elif text in ("/shop", "🛍️ Browse Products / Shop", "🛍️ Shop / Products", "🛍️ Shop", "Shop", "Products"):
        cats = await cat_get_all()
        counts = await get_all_stock_counts(cats)
        kb, total_pages = kb_shop_paginated(cats, counts, page=0)
        t, ent = build_shop_paginated(len(cats), 0, total_pages)
        await send_msg(chat_id, t, ent, kb)

    elif text in ("/profile", "👤 My Profile", "👤 Profile", "Profile", "My Profile"):
        db_data = await db_get_user(user_id)
        await send_profile(chat_id, user, db_data, kb_profile())

    elif text in ("/wallet", "/balance", "💳 My Wallet", "💳 Wallet", "Wallet", "Balance"):
        db_data = await db_get_user(user_id)
        balance = db_data.get("balance", 0.0) if db_data else 0.0
        t, ent  = build_wallet(balance)
        await send_msg(chat_id, t, ent, kb_wallet())

    elif text == "/deposit" or text == "/topup":
        db_data = await db_get_user(user_id)
        balance = db_data.get("balance", 0.0) if db_data else 0.0
        t, ent  = build_topup_prompt(balance)
        _awaiting_topup_amount[user_id] = True
        await send_msg(chat_id, t, ent, keyboard=kb_topup_prompt())

    elif text in ("/history", "📜 Order History", "📜 History", "Order History", "History"):
        # Show user's recent orders
        async with _ord_lock:
            all_orders = _load_orders()
        user_orders = [
            o for o in all_orders.values()
            if o["user_id"] == str(user_id)
        ]
        # Sort newest first, show last 5
        user_orders.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        recent = user_orders[:5]

        m = Msg()
        m.emoji("clipboard").text(" ").bold("Order ").italic("History").nl(2)
        if not recent:
            m.emoji("box").text(" ").italic("No orders yet.").nl(2)
            m.text("Start shopping to see your orders here!")
        else:
            for o in recent:
                status = o["status"]
                if status == "approved":
                    m.emoji("check")
                elif status in ("pending_payment", "pending_approval"):
                    m.emoji("timer")
                else:
                    m.emoji("cross")
                m.text(" ").bold(o["cat_name"]).nl()
                m.emoji("balance").text(f" Br {o['price']:.2f}").text(f"  •  {o['created_at'][:10]}").nl(2)
        t, ent = m.build()
        await send_msg(chat_id, t, ent,
            keyboard=build_keyboard([[btn("🏠 Home", "back_main")]])
        )

    elif text in ("/logs", "/botlogs", "/orderlogs", "📊 Bot Logs", "📊 Live Logs", "Bot Logs", "Order Logs", "Logs"):
        m = Msg()
        m.emoji("channel").text(" ").bold("Official Bot Logs Group").nl()
        m.text("━━━━━━━━━━━━━━━━━━━━").nl()
        m.emoji("thunder").text(" View real-time live order status updates, completed purchases, deposits, and restocks directly on our official logs group.").nl(2)
        m.emoji("star").text(" Logs Group: ").bold("https://t.me/+2RORZ17pHqNiYzM0").nl()
        m.text("━━━━━━━━━━━━━━━━━━━━")
        t, ent = m.build()
        kb = build_keyboard([
            [btn("📢 Open Bot Logs Group", url=LOG_CHANNEL_LINK, emoji_key="channel", style="success")],
            [btn("🏠 Main Menu", "back_main", emoji_key="back")],
        ])
        await send_msg(chat_id, t, ent, kb)

    elif text in ("/referral", "/ref", "/invite", "👥 Referral", "👥 Invite", "Referral", "Invite"):
        (t, ent), kb = build_referral_screen()
        await send_msg(chat_id, t, ent, kb)

    elif text in ("/support", "/contact", "/helpdesk", "🎧 Support", "Support", "Contact"):
        t, ent = build_support_screen()
        kb = build_keyboard([
            [btn("💬 Message Support", url=SUPPORT_LINK, emoji_key="support", style="success")],
            [btn("🏠 Main Menu", "back_main", emoji_key="back")],
        ])
        await send_msg(chat_id, t, ent, kb)

    elif text in ("/channel", "/news", "/updates", "📢 Official Channel", "📢 Channel", "Channel"):
        m = Msg()
        m.emoji("channel").text(" ").bold("Join Our Official Channel").nl(2)
        m.text("Stay updated with daily restocks, new products, and flash giveaways!").nl(2)
        m.emoji("star").text(" Official Channel: ").bold(FORCE_JOIN_CHANNEL_NAME).nl()
        t, ent = m.build()
        kb = build_keyboard([
            [btn("📢 Join Channel", url=FORCE_JOIN_CHANNEL_LINK, emoji_key="channel", style="success")],
            [btn("🏠 Main Menu", "back_main", emoji_key="back")],
        ])
        await send_msg(chat_id, t, ent, kb)

    elif text in ("/admin", "/panel", "👑 Admin Control Panel", "Admin Control Panel", "Admin Panel"):
        if not is_admin(user_id):
            await send_msg(chat_id, "⛔ You are not authorized.")
            return
        t, ent = await build_admin_dashboard()
        await send_msg(chat_id, t, ent, kb_admin_panel())
        return

    elif text in ("/developer", "/dev", "👨‍💻 Developed By @kidanewold777", "💎 Developed By @kidanewold777", "👨‍💻 Developed By", "Developed By", "Developer"):
        t, ent = build_dev_screen()
        kb = build_keyboard([
            [btn("💬 Message Developer (@kidanewold777)", url=DEVELOPER_LINK, emoji_key="support", style="success")],
            [btn("📢 Official Channel", url=FORCE_JOIN_CHANNEL_LINK, emoji_key="channel")],
            [btn("🏠 Main Menu", "back_main", emoji_key="back")],
        ])
        await send_msg(chat_id, t, ent, kb)
        return

    elif text == "/help" or text == "/commands":
        t, ent = build_help()
        await send_msg(chat_id, t, ent, kb_home())

    elif text == "/test":
        t, ent = build_test()
        await send_msg(chat_id, t, ent)

    # ── Product shortcut commands ──────────────────────────────
    elif text.startswith("/"):
        # Try to match command with product name (e.g., /telegram, /netflix)
        command = text[1:].lower().strip()
        cats = _load_categories()
        
        # Try to find matching category by command
        matched_cat = None
        for cat_id, cat in cats.items():
            cat_name_clean = cat["name"].lower().replace(" ", "").replace("-", "")
            # Check if command matches category ID or simplified name
            if cat_id.lower() == command or command in cat_name_clean:
                matched_cat = (cat_id, cat)
                break
        
        if matched_cat:
            cat_id, cat = matched_cat
            count = await stock_count(cat_id)
            
            # Build product detail message
            description = cat.get("description", "").strip()
            desc_entities = cat.get("desc_entities", [])
            stock_status_text = "Available ✅" if count > 0 else "Out of Stock ❌"

            if description:
                # Check if description has stored entities (new system) or placeholders (old system)
                if desc_entities:
                    # NEW SYSTEM: Use stored premium emoji entities
                    cat_emoji = cat.get('emoji_char', '🛒')
                    header = f"{cat_emoji} "
                    
                    m = Msg()
                    m.text(header).bold(cat["name"]).nl(2)
                    header_text, header_entities = m.build()
                    
                    desc_offset = u16(header_text)
                    
                    footer = Msg()
                    footer.nl().text("━━━━━━━━━━━━━━━━").nl()
                    footer.emoji("balance").text(" Price: ").bold(f"Br {cat['price']:.2f}").nl()
                    footer.emoji("box").text(f" Stock: {stock_status_text}")
                    footer_text, footer_entities = footer.build()
                    
                    full_text = header_text + description + footer_text
                    
                    adjusted_desc_entities = []
                    for ent in desc_entities:
                        adjusted_ent = {
                            "type": ent.get("type"),
                            "offset": ent.get("offset", 0) + desc_offset,
                            "length": ent.get("length", 1),
                            "custom_emoji_id": str(ent.get("custom_emoji_id", ""))
                        }
                        adjusted_desc_entities.append(adjusted_ent)
                    
                    footer_offset = desc_offset + u16(description)
                    adjusted_footer_entities = []
                    for ent in footer_entities:
                        adjusted_ent = dict(ent)
                        adjusted_ent["offset"] = ent.get("offset", 0) + footer_offset
                        adjusted_footer_entities.append(adjusted_ent)
                    
                    text = full_text
                    entities = header_entities + adjusted_desc_entities + adjusted_footer_entities
                else:
                    # OLD SYSTEM: Process {{placeholder}} style descriptions
                    m = Msg()
                    cat_emoji = cat.get('emoji_char', '🛒')
                    m.text(f"{cat_emoji} ").bold(cat["name"]).nl(2)
                    
                    placeholder_map = {
                        "{{balance}}": "balance", "{{check}}": "check", "{{cart}}": "cart",
                        "{{key}}": "key", "{{box}}": "box", "{{pop}}": "pop",
                        "{{clock}}": "clock", "{{timer}}": "timer", "{{camera}}": "camera",
                        "{{thunder}}": "thunder", "{{arrow}}": "arrow", "{{clipboard}}": "clipboard",
                        "{{cross}}": "cross", "{{checkmark}}": "checkmark",
                    }
                    
                    for line in description.splitlines():
                        stripped = line.strip()
                        if not stripped:
                            m.nl()
                            continue
                        
                        has_placeholder = any(p in stripped for p in placeholder_map.keys())
                        
                        if has_placeholder:
                            remaining = stripped
                            while remaining:
                                first_pos = len(remaining)
                                first_placeholder = None
                                first_key = None
                                
                                for placeholder, emoji_key in placeholder_map.items():
                                    pos = remaining.find(placeholder)
                                    if pos != -1 and pos < first_pos:
                                        first_pos = pos
                                        first_placeholder = placeholder
                                        first_key = emoji_key
                                
                                if first_placeholder:
                                    if first_pos > 0:
                                        m.text(remaining[:first_pos])
                                    m.emoji(first_key)
                                    remaining = remaining[first_pos + len(first_placeholder):]
                                else:
                                    m.text(remaining)
                                    break
                            m.nl()
                        else:
                            if stripped.startswith(("•", "-", "▶", "▸")):
                                m.text(stripped).nl()
                            elif stripped.endswith(":") and len(stripped) <= 40:
                                m.bold(stripped).nl()
                            else:
                                m.text(stripped).nl()
                    
                    m.nl().text("━━━━━━━━━━━━━━━━").nl()
                    m.emoji("balance").text(" Price: ").bold(f"Br {cat['price']:.2f}").nl()
                    m.emoji("box").text(f" Stock: {stock_status_text}")
                    text, entities = m.build()
            else:
                m = Msg()
                m.text(f"{cat.get('emoji_char', '🛒')} ").bold(cat["name"]).nl(2)
                m.emoji("balance").text("  Price: ").bold(f"Br {cat['price']:.2f}").nl()
                m.emoji("box").text(f"  Stock: {stock_status_text}").nl(2)
                if count > 0:
                    m.emoji("check").text(" Tap Buy to purchase.")
                else:
                    m.emoji("timer").text(" Out of stock. Check back soon!")
                text, entities = m.build()

            kb = build_keyboard([
                [btn("Buy Now", f"buy_{cat_id}", emoji_key="cart", style="success")] if count > 0 else
                [btn("Out of Stock", "noop", emoji_key="cross")],
                [btn("Back to Shop", "shop", emoji_key="back")],
            ])
            await send_msg(chat_id, text, entities or None, kb)


async def handle_callback(cq: dict):
    cq_id   = cq["id"]
    user    = cq.get("from", {})
    data    = cq.get("data", "")
    msg     = cq.get("message", {})
    mid     = msg.get("message_id")
    chat_id = msg.get("chat", {}).get("id")

    # Save / update user in DB on every callback
    await db_upsert_user(user)

    # ── check_join button — re-check membership ────────────────
    if data == "check_join":
        user_id   = user.get("id")
        is_member = await check_membership(user_id)
        if is_member:
            # Check if user has accepted terms
            db_data = await db_get_user(user_id)
            terms_accepted = db_data.get("terms_accepted", False) if db_data else False
            
            if not terms_accepted:
                # Show terms & conditions
                await answer_cb(cq_id, "✅ Verified! Please accept our terms to continue.", alert=False)
                await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
                t, ent = build_terms()
                await send_msg(chat_id, t, ent,
                    keyboard=build_keyboard([
                        [btn("I Agree", "accept_terms", emoji_key="check", style="success")],
                        [btn("Decline", "decline_terms", emoji_key="cross")],
                    ])
                )
            else:
                # Already accepted terms, show welcome
                await answer_cb(cq_id, "✅ Welcome back!", alert=False)
                await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
                await send_welcome_screen(chat_id, user)
        else:
            await answer_cb(cq_id,
                "You haven't joined yet! Please join the channel first.",
                alert=True)
        return

    # ── Terms acceptance callbacks ─────────────────────────────
    if data == "accept_terms":
        user_id = user.get("id")
        await db_accept_terms(user_id)
        await answer_cb(cq_id, "✅ Thank you! Welcome to ET Market!", alert=False)
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_welcome_screen(chat_id, user)
        return

    if data == "decline_terms":
        await answer_cb(cq_id, "❌ You must accept our terms to use the bot.", alert=True)
        return

    # ── Force Join check for all other callbacks (skip admins) ─
    if not is_admin(user.get("id")):
        user_id = user.get("id")
        is_member = await check_membership(user_id)
        if not is_member:
            await answer_cb(cq_id)
            await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
            await send_join_prompt(chat_id)
            return
        
        # Check terms acceptance for non-admins
        db_data = await db_get_user(user_id)
        terms_accepted = db_data.get("terms_accepted", False) if db_data else False
        if not terms_accepted:
            await answer_cb(cq_id)
            await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
            t, ent = build_terms()
            await send_msg(chat_id, t, ent,
                keyboard=build_keyboard([
                    [btn("I Agree", "accept_terms", emoji_key="check", style="success")],
                    [btn("Decline", "decline_terms", emoji_key="cross")],
                ])
            )
            return

    # ── Strict Admin Authorization Guard ─────────────────────────
    if data in ("admin_panel", "admin_products", "admin_sync_safwan", "admin_addcat") or data.startswith(("admin_", "admset_", "admgw_", "admgive_", "admresetbal_")):
        if not is_admin(user.get("id")):
            await answer_cb(cq_id, "⛔ Access Denied: Administrator privileges required.", alert=True)
            return

    await answer_cb(cq_id)

    if data == "back_main":
        # Delete current message (could be photo or text) then send fresh
        try:
            await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        except Exception:
            pass
        await send_welcome_screen(chat_id, user)

    elif data == "shop":
        _awaiting_search.pop(user.get("id"), None)
        await answer_cb(cq_id)
        cats = await cat_get_all()
        counts = await get_all_stock_counts(cats)
        kb, total_pages = kb_shop_paginated(cats, counts, page=0)
        t, ent = build_shop_paginated(len(cats), 0, total_pages)
        res = await edit_msg(chat_id, mid, t, ent, kb)
        if not res.get("ok"):
            try:
                await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
            except Exception:
                pass
            await send_msg(chat_id, t, ent, kb)

    elif data == "shop_search":
        _awaiting_search[user.get("id")] = True
        await answer_cb(cq_id)
        try:
            await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        except Exception:
            pass
        t, ent = build_search_prompt_screen()
        kb = build_keyboard([
            [btn("Back to Products", "shop", emoji_key="back")]
        ])
        await send_msg(chat_id, t, ent, kb)

    elif data.startswith("shop_page_"):
        await answer_cb(cq_id)
        page_num = int(data[10:])
        cats = await cat_get_all()
        counts = await get_all_stock_counts(cats)
        kb, total_pages = kb_shop_paginated(cats, counts, page=page_num)
        t, ent = build_shop_paginated(len(cats), page_num, total_pages)
        await edit_msg(chat_id, mid, t, ent, kb)

    elif data == "profile":
        db_data = await db_get_user(user.get("id"))
        await edit_profile(chat_id, mid, user, db_data, kb_profile())

    elif data == "support":
        try:
            await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        except Exception:
            pass
        t, ent = build_support_screen()
        kb = build_keyboard([
            [btn("💬 Message Support", url=SUPPORT_LINK, emoji_key="support", style="success")],
            [btn("🏠 Main Menu", "back_main", emoji_key="back")],
        ])
        await send_msg(chat_id, t, ent, kb)

    elif data == "referral":
        await answer_cb(cq_id, "⏳ Referral Program is Coming Soon!", alert=False)
        try:
            await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        except Exception:
            pass
        (t, ent), kb = build_referral_screen()
        await send_msg(chat_id, t, ent, kb)

    elif data == "terms":
        try:
            await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        except Exception:
            pass
        kb = build_keyboard([
            [btn("🎧 Contact Support", url=SUPPORT_LINK, emoji_key="support")],
            [btn("🏠 Main Menu", "back_main", emoji_key="back")],
        ])
        await send_msg(chat_id, TERMS_TEXT, keyboard=kb)

    elif data == "wallet":
        user_id = user.get("id")
        _awaiting_topup_amount.pop(user_id, None)
        db_data = await db_get_user(user_id)
        balance = db_data.get("balance", 0.0) if db_data else 0.0
        t, ent  = build_wallet(balance)
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_msg(chat_id, t, ent, kb_wallet())

    elif data == "menu":
        t, ent = build_menu()
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_msg(chat_id, t, ent, kb_menu())

    elif data in ("add_balance", "topup_wallet"):
        user_id = user.get("id")
        db_data = await db_get_user(user_id)
        balance = db_data.get("balance", 0.0) if db_data else 0.0
        t, ent  = build_topup_prompt(balance)
        _awaiting_topup_amount[user_id] = True
        await edit_msg(chat_id, mid, t, ent, keyboard=kb_topup_prompt())

    elif data.startswith("topup_amt_"):
        user_id = user.get("id")
        _awaiting_topup_amount.pop(user_id, None)
        amt_str = data[10:]
        try:
            amount = float(amt_str)
        except ValueError:
            amount = 100.0
        await start_topup_order(chat_id, user_id, amount, edit_mid=mid)

    elif data.startswith("topup_telebirr_"):
        order_id = data[15:]
        order    = await order_get(order_id)
        user_id  = user.get("id")

        if not order:
            await answer_cb(cq_id, "❌ Order not found.", alert=True)
            return
        if str(order["user_id"]) != str(user_id):
            await answer_cb(cq_id, "⛔ Unauthorized.", alert=True)
            return
        if order["status"] not in ("pending_payment",):
            await answer_cb(cq_id, "⚠️ Order already processed.", alert=True)
            return

        async with _ord_lock:
            all_orders = _load_orders()
            if order_id in all_orders:
                all_orders[order_id]["payment_method"] = "telebirr"
                _save_orders(all_orders)

        caption, cap_entities = build_payment_caption("💳 Wallet Top Up", order["price"])
        kb = build_keyboard([
            [btn("I've Paid via Telebirr — Done", f"done_telebirr_{order_id}", emoji_key="check", style="success")],
            [btn("Cancel", f"cancel_{order_id}", emoji_key="cross")],
        ])
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        if os.path.exists(PAYMENT_IMAGE):
            await send_local_photo(chat_id, PAYMENT_IMAGE, caption, kb, cap_entities)
        else:
            await send_msg(chat_id, caption, cap_entities, kb)

    elif data.startswith("topup_cbebirr_"):
        order_id = data[14:]
        order    = await order_get(order_id)
        user_id  = user.get("id")

        if not order:
            await answer_cb(cq_id, "❌ Order not found.", alert=True)
            return
        if str(order["user_id"]) != str(user_id):
            await answer_cb(cq_id, "⛔ Unauthorized.", alert=True)
            return
        if order["status"] not in ("pending_payment",):
            await answer_cb(cq_id, "⚠️ Order already processed.", alert=True)
            return

        async with _ord_lock:
            all_orders = _load_orders()
            if order_id in all_orders:
                all_orders[order_id]["payment_method"] = "cbebirr"
                _save_orders(all_orders)

        caption, cap_entities = build_cbebirr_payment_caption("💳 Wallet Top Up", order["price"])
        kb = build_keyboard([
            [btn("I've Paid via CBE Birr — Done", f"done_cbebirr_{order_id}", emoji_key="check", style="success")],
            [btn("Cancel", f"cancel_{order_id}", emoji_key="cross")],
        ])
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        if os.path.exists(CBEBIRR_IMAGE):
            await send_local_photo(chat_id, CBEBIRR_IMAGE, caption, kb, cap_entities)
        else:
            await send_msg(chat_id, caption, cap_entities, kb)

    elif data.startswith("cat_"):
        cat_id = data[4:]
        cats   = _load_categories()
        cat    = cats.get(cat_id)
        if not cat:
            await answer_cb(cq_id, "❌ Product not found.", alert=True)
            return
        count = await stock_count(cat_id)
        t, ent = build_cat_detail(cat, count, qty=1)
        kb = kb_cat_detail(cat_id, count, qty=1)
        await edit_msg(chat_id, mid, t, ent, kb)

    elif data.startswith("qty_set_"):
        parts = data.split("_")
        if len(parts) >= 4:
            cat_id = "_".join(parts[2:-1])
            try:
                qty = int(parts[-1])
            except ValueError:
                qty = 1
        else:
            cat_id = parts[2]
            qty = 1
            
        cats = _load_categories()
        cat = cats.get(cat_id)
        if not cat:
            await answer_cb(cq_id, "❌ Product not found.", alert=True)
            return
        count = await stock_count(cat_id)
        qty = max(1, min(qty, max(1, count)))
        t, ent = build_cat_detail(cat, count, qty=qty)
        kb = kb_cat_detail(cat_id, count, qty=qty)
        await edit_msg(chat_id, mid, t, ent, kb)

    elif data.startswith("qty_custom_"):
        cat_id = data[11:]
        cats = _load_categories()
        cat = cats.get(cat_id)
        if not cat:
            await answer_cb(cq_id, "❌ Product not found.", alert=True)
            return
        count = await stock_count(cat_id)
        if count <= 0:
            await answer_cb(cq_id, "❌ Product is out of stock.", alert=True)
            return
            
        user_id = user.get("id")
        _awaiting_qty_input[user_id] = {"cat_id": cat_id, "mid": mid}
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        
        m = Msg()
        m.emoji("box").text(" ").bold(f"Enter Quantity for {cat['name']}").nl()
        m.text("━━━━━━━━━━━━━━━━━━━━").nl()
        m.text(f"• Unit Price: ").bold(f"Br {cat['price']:,.2f}").nl()
        m.text(f"• Available Stock: ").bold(f"{count} units").nl(2)
        m.text("Please type the ").bold("number of units").text(f" you want to buy (1 - {count}):").nl()
        m.italic("(Or type /cancel to go back)")
        t, ent = m.build()
        
        await send_msg(chat_id, t, ent,
            keyboard=build_keyboard([[btn("❌ Cancel", f"cat_{cat_id}", emoji_key="cross")]])
        )

    elif data == "noop":
        pass

    elif data.startswith("buy_"):
        parts = data.split("_")
        if len(parts) >= 3 and parts[-1].isdigit():
            cat_id = "_".join(parts[1:-1])
            qty = int(parts[-1])
        else:
            cat_id = "_".join(parts[1:])
            qty = 1
            
        cats = _load_categories()
        cat = cats.get(cat_id)
        if not cat:
            await answer_cb(cq_id, "❌ Product not found.", alert=True)
            return
        count = await stock_count(cat_id)
        if count < qty or count <= 0:
            await answer_cb(cq_id, f"❌ Sorry, only {count} unit(s) available in stock!", alert=True)
            return

        user_id = user.get("id")
        db_data = await db_get_user(user_id)
        balance = db_data.get("balance", 0.0) if db_data else 0.0
        unit_price = float(cat["price"])
        total_price = unit_price * qty

        order_id = await order_create(
            user_id, cat_id, cat["name"], price=total_price, quantity=qty, unit_price=unit_price
        )

        pay_rows = [
            [btn(f"Pay with Wallet (Br {balance:,.2f})", f"paywallet_{order_id}", emoji_key="paywallet", style="success" if balance >= total_price else None)],
            [btn("Pay via Telebirr", f"pay_telebirr_{order_id}", emoji_key="telebirr", style="success" if balance < total_price else None)],
            [btn("Pay via CBE Birr", f"pay_cbebirr_{order_id}", emoji_key="cbe", style="success" if balance < total_price else None)],
            [btn("Back to Product", f"cat_{cat_id}", emoji_key="back"),
             btn("Cancel Order", f"cancel_{order_id}", emoji_key="cross")],
        ]

        kb = build_keyboard(pay_rows)
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})

        sm = Msg()
        sm.emoji("check").text(" ").bold("Your Order Summary").nl(2)
        sm.emoji("cart").text(" Product: ").bold(f"{cat['name']} (x{qty})").nl()
        sm.emoji("balance").text(" Unit Price: ").bold(f"Br {unit_price:,.2f}").nl()
        sm.emoji("box").text(" Quantity: ").bold(f"{qty} unit{'s' if qty > 1 else ''}").nl()
        sm.emoji("wallet").text(" Total Price: ").bold(f"Br {total_price:,.2f} ETB").nl()
        sm.emoji("balance").text(" Your Wallet Balance: ").bold(f"Br {balance:,.2f} ETB").nl(2)
        sm.emoji("bank").text(" Choose your ").bold("payment method").text(" below:")
        sm_text, sm_ent = sm.build()
        await send_msg(chat_id, sm_text, sm_ent, kb)

    elif data.startswith("pay_telebirr_"):
        order_id = data[13:]
        order    = await order_get(order_id)
        user_id  = user.get("id")

        if not order:
            await answer_cb(cq_id, "❌ Order not found.", alert=True)
            return
        if str(order["user_id"]) != str(user_id):
            await answer_cb(cq_id, "⛔ Unauthorized.", alert=True)
            return
        if order["status"] not in ("pending_payment",):
            await answer_cb(cq_id, "⚠️ Order already processed.", alert=True)
            return

        async with _ord_lock:
            all_orders = _load_orders()
            if order_id in all_orders:
                all_orders[order_id]["payment_method"] = "telebirr"
                _save_orders(all_orders)

        caption, cap_entities = build_payment_caption(
            "Your Order Summary", order["price"], order["cat_name"]
        )
        kb = build_keyboard([
            [btn("I've Paid via Telebirr — Done", f"done_telebirr_{order_id}", emoji_key="check", style="success")],
            [btn("Back", f"buy_{order['cat_id']}_{order.get('quantity', 1)}", emoji_key="back"),
             btn("Cancel", f"cancel_{order_id}", emoji_key="cross")],
        ])
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        if os.path.exists(PAYMENT_IMAGE):
            await send_local_photo(chat_id, PAYMENT_IMAGE, caption, kb, cap_entities)
        else:
            await send_msg(chat_id, caption, cap_entities, kb)

    elif data.startswith("pay_cbebirr_"):
        order_id = data[12:]
        order    = await order_get(order_id)
        user_id  = user.get("id")

        if not order:
            await answer_cb(cq_id, "❌ Order not found.", alert=True)
            return
        if str(order["user_id"]) != str(user_id):
            await answer_cb(cq_id, "⛔ Unauthorized.", alert=True)
            return
        if order["status"] not in ("pending_payment",):
            await answer_cb(cq_id, "⚠️ Order already processed.", alert=True)
            return

        async with _ord_lock:
            all_orders = _load_orders()
            if order_id in all_orders:
                all_orders[order_id]["payment_method"] = "cbebirr"
                _save_orders(all_orders)

        caption, cap_entities = build_cbebirr_payment_caption(
            "Your Order Summary", order["price"], order["cat_name"]
        )
        kb = build_keyboard([
            [btn("I've Paid via CBE Birr — Done", f"done_cbebirr_{order_id}", emoji_key="check", style="success")],
            [btn("Back", f"buy_{order['cat_id']}_{order.get('quantity', 1)}", emoji_key="back"),
             btn("Cancel", f"cancel_{order_id}", emoji_key="cross")],
        ])
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        if os.path.exists(CBEBIRR_IMAGE):
            await send_local_photo(chat_id, CBEBIRR_IMAGE, caption, kb, cap_entities)
        else:
            await send_msg(chat_id, caption, cap_entities, kb)

    elif data.startswith("done_"):
        if data.startswith("done_cbebirr_"):
            order_id = data[13:]
            method = "cbebirr"
        elif data.startswith("done_telebirr_"):
            order_id = data[14:]
            method = "telebirr"
        else:
            order_id = data[5:]
            method = None

        order    = await order_get(order_id)
        user_id  = user.get("id")

        if not order:
            await answer_cb(cq_id, "❌ Order not found.", alert=True)
            return
        if str(order["user_id"]) != str(user_id):
            await answer_cb(cq_id, "⛔ Unauthorized.", alert=True)
            return
        if order["status"] not in ("pending_payment",):
            await answer_cb(cq_id,
                "⚠️ This order has already been submitted.", alert=True)
            return

        if method:
            async with _ord_lock:
                all_orders = _load_orders()
                if order_id in all_orders:
                    all_orders[order_id]["payment_method"] = method
                    _save_orders(all_orders)

        _awaiting_screenshot[user_id] = order_id
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        
        m = Msg()
        order_method = order.get("payment_method") or method or "telebirr"
        if order_method == "cbebirr":
            m.emoji("key").text(" ").bold("Enter CBE Birr Transaction ID").nl(2)
            m.emoji("clipboard").text(" Order: ").bold(order['cat_name']).nl()
            m.emoji("balance").text(" Amount: ").bold(f"Br {order['price']:,.2f}").nl()
            if order.get("quantity", 1) > 1:
                m.emoji("box").text(" Quantity: ").bold(f"{order['quantity']} units").nl()
            m.nl()
            m.text("Please send your ").bold("CBE Birr Transaction ID / Receipt Number").text(" (e.g. ").code("1029384756").text(" or ").code("REC12345").text(") or paste the SMS received from CBE Birr (889):").nl(2)
        else:
            m.emoji("key").text(" ").bold("Enter Telebirr Transaction ID").nl(2)
            m.emoji("clipboard").text(" Order: ").bold(order['cat_name']).nl()
            m.emoji("balance").text(" Amount: ").bold(f"Br {order['price']:,.2f}").nl()
            if order.get("quantity", 1) > 1:
                m.emoji("box").text(" Quantity: ").bold(f"{order['quantity']} units").nl()
            m.nl()
            m.text("Please send your ").bold("Telebirr Transaction ID / Reference Number").text(" (e.g. ").code("TRA12345678").text(" or ").code("DGJBFFH").text(") or paste the full SMS received from Telebirr (127):").nl(2)

        m.emoji("thunder").text(" ").italic("Instant automated 24/7 verification with Verify.ET")
        ss_text, ss_ent = m.build()
        
        await send_msg(chat_id, ss_text, ss_ent,
            keyboard=build_keyboard([
                [btn("❌ Cancel Order", f"cancel_{order_id}", emoji_key="cross")]
            ])
        )

    elif data.startswith("paywallet_"):
        order_id = data[10:]
        order    = await order_get(order_id)
        user_id  = user.get("id")

        if not order:
            await answer_cb(cq_id, "❌ Order not found.", alert=True)
            return
        if str(order["user_id"]) != str(user_id):
            await answer_cb(cq_id, "⛔ Unauthorized.", alert=True)
            return
        if order["status"] != "pending_payment":
            await answer_cb(cq_id, "⚠️ Order already processed.", alert=True)
            return
        if order.get("order_type") == "topup":
            await answer_cb(cq_id, "❌ Cannot pay a top-up with wallet.", alert=True)
            return

        # Pre-purchase live stock check
        cat_id = order.get("cat_id")
        order_qty = max(1, int(order.get("quantity", 1)))
        if cat_id:
            live_stk = await stock_count(cat_id)
            if live_stk < order_qty:
                await answer_cb(cq_id, f"❌ Sorry, insufficient stock (need {order_qty}, only {live_stk} in stock)! Your balance was NOT deducted.", alert=True)
                return

        db_data = await db_get_user(user_id)
        balance = db_data.get("balance", 0.0) if db_data else 0.0
        price   = order["price"]

        if balance < price:
            shortfall = price - balance
            await answer_cb(cq_id,
                f"❌ Insufficient wallet balance!\n\nYou have: Br {balance:,.2f}\nRequired: Br {price:,.2f}\nShortfall: Br {shortfall:,.2f}\n\nPlease top up your wallet or pay via Telebirr.",
                alert=True)
            return

        await db_deduct_balance(user_id, price)
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})

        invalidate_safwan_stock_cache()
        await fulfill_order_auto(order_id, price)
        await answer_cb(cq_id, "✅ Order paid & fulfilled!", alert=False)
        return

    elif data.startswith("cancel_"):
        order_id = data[7:]
        order    = await order_get(order_id)
        user_id  = user.get("id")

        if not order:
            await answer_cb(cq_id, "❌ Order not found.", alert=True)
            return
        if str(order["user_id"]) != str(user_id):
            await answer_cb(cq_id, "⛔ Unauthorized.", alert=True)
            return

        _awaiting_screenshot.pop(user_id, None)
        _awaiting_cbe_sms.pop(user_id, None)
        _awaiting_topup_amount.pop(user_id, None)
        await order_set_status(order_id, "cancelled")

        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        if order.get("order_type") == "topup":
            db_data = await db_get_user(user_id)
            balance = db_data.get("balance", 0.0) if db_data else 0.0
            t, ent = build_wallet(balance)
            full_t, full_ent = merge_with_prefix("❌ Top-up cancelled.\n\n", t, ent)
            await send_msg(chat_id,
                full_t, full_ent,
                keyboard=kb_wallet()
            )
        else:
            await send_msg(chat_id,
                "Order cancelled.\n\nYou can browse the shop anytime.",
                keyboard=build_keyboard([
                    [btn("Back to Shop", "shop", emoji_key="back")],
                    [btn("Home", "back_main", emoji_key="back")],
                ])
            )

    elif data.startswith("vetcheck_"):
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        parts = data.split("_", 2)
        if len(parts) >= 3:
            order_id = parts[1]
            ref_num = parts[2]
        else:
            await answer_cb(cq_id, "❌ Invalid callback data.", alert=True)
            return

        order = await order_get(order_id)
        if not order or order.get("status") not in ("pending_payment", "pending_approval"):
            await answer_cb(cq_id, "⚠️ Order already processed.", alert=True)
            return

        await answer_cb(cq_id, f"🔍 Checking Verify.ET for {ref_num}...", alert=False)
        vet_res = await vet_verify("telebirr", ref_num)
        if vet_res.get("verified"):
            v_amount = vet_res.get("amount", 0.0)
            sender = vet_res.get("sender", "")
            await fulfill_order_auto(order_id, v_amount, sender)
            await answer_cb(cq_id, f"✅ Verified & Auto-Fulfilled! (Br {v_amount:.2f})", alert=True)
            try:
                msg_caption = f"✅ Order #{order_id[:8].upper()} AUTO-VERIFIED & DELIVERED via Verify.ET!\n\n💰 Amount: Br {v_amount:,.2f}\n👤 Sender: {sender}\n🧾 Ref: `{ref_num}`"
                if msg.get("photo"):
                    await edit_caption(chat_id, mid, msg_caption)
                else:
                    await edit_msg(chat_id, mid, msg_caption)
            except Exception:
                pass
        else:
            err = vet_res.get("error", "Transaction not found or not settled")
            await answer_cb(cq_id, f"❌ Verify.ET: {err}", alert=True)

    elif data.startswith("vetprompt_"):
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        order_id = data[10:]
        _admin_state[uid] = {"step": "vet_manual_ref", "data": {"order_id": order_id}}
        await answer_cb(cq_id, "Send Telebirr Transaction ID:", alert=False)
        await send_msg(chat_id, f"🔍 Send the Telebirr Transaction ID (e.g. `TRA...` or `2608...`) for Order `#{order_id[:8].upper()}`:")

    elif data.startswith("approve_"):
        if not is_admin(user.get("id")):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        order_id = data[8:]
        order    = await order_get(order_id)
        if not order:
            await answer_cb(cq_id, "❌ Order not found.", alert=True)
            return
        if order["status"] not in ("pending_approval",):
            await answer_cb(cq_id,
                f"⚠️ Order status is already: {order['status']}", alert=True)
            return

        await fulfill_order_auto(order_id, order["price"])

        await edit_caption(
            chat_id, mid,
            f"✅ APPROVED & FULFILLED — Order #{order_id[:8].upper()}\n\n"
            f"🛒 {order['cat_name']}\n"
            f"💰 Br {order['price']:.2f}\n"
            f"👤 User ID: {order['user_id']}"
        )
        await answer_cb(cq_id, "✅ Order approved & processed!")
        return

    elif data.startswith("deliver_"):
        # Admin only — triggered for manual link or credentials delivery
        if not is_admin(user.get("id")):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        order_id = data[8:]
        order    = await order_get(order_id)
        if not order:
            await answer_cb(cq_id, "❌ Order not found.", alert=True)
            return

        cats     = _load_categories()
        cat_obj  = cats.get(order.get("cat_id", ""), {})
        cat_type = cat_obj.get("cat_type", "id_pass")
        buyer_id = int(order["user_id"])

        await answer_cb(cq_id)
        try:
            await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        except Exception:
            pass

        if cat_type == "link" or not cat_type:
            # Put admin in state to type/paste the link
            _admin_state[int(user.get("id"))] = {
                "step": "deliver_link",
                "data": {
                    "order_id":  order_id,
                    "buyer_id":  buyer_id,
                    "cat_name":  order["cat_name"],
                }
            }
            m = Msg()
            m.emoji("link").text(" ").bold("Send Activation Link / Access URL").nl(2)
            m.emoji("cart").text(f" Product: {order['cat_name']}\n")
            m.emoji("user").text(f" Customer ID: ").code(str(buyer_id)).nl()
            m.emoji("key").text(f" Order ID: ").code(f"#{order_id[:8].upper()}").nl(2)
            m.italic("Type or paste the activation link below. The bot will deliver it instantly to the customer:\n(Or tap Cancel below to abort)")
            t, ent = m.build()
            await send_msg(chat_id, t, ent, keyboard=build_keyboard([
                [btn("❌ Cancel", "admin_pending", emoji_key="cross")]
            ]))
        else:
            # id_pass — put admin in deliver_creds state
            _admin_state[int(user.get("id"))] = {
                "step": "deliver_creds",
                "data": {
                    "order_id":  order_id,
                    "buyer_id":  buyer_id,
                    "cat_name":  order["cat_name"],
                    "cat_type":  cat_type,
                }
            }
            m = Msg()
            m.emoji("key").text(" ").bold("Send Account Credentials").nl(2)
            m.emoji("cart").text(f" Product: {order['cat_name']}\n")
            m.emoji("user").text(f" Customer ID: ").code(str(buyer_id)).nl()
            m.emoji("key").text(f" Order ID: ").code(f"#{order_id[:8].upper()}").nl(2)
            m.italic("Send credentials as email:password below. The bot will deliver it instantly to the customer:\n(Or tap Cancel below to abort)")
            t, ent = m.build()
            await send_msg(chat_id, t, ent, keyboard=build_keyboard([
                [btn("❌ Cancel", "admin_pending", emoji_key="cross")]
            ]))

    elif data.startswith("reject_"):
        # Admin only
        if not is_admin(user.get("id")):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        order_id = data[7:]
        order    = await order_get(order_id)
        if not order:
            await answer_cb(cq_id, "❌ Order not found.", alert=True)
            return
        if order["status"] not in ("pending_approval",):
            await answer_cb(cq_id,
                f"⚠️ Order status is already: {order['status']}", alert=True)
            return

        await order_set_status(order_id, "rejected")
        buyer_id = int(order["user_id"])

        await send_msg(buyer_id,
            f"❌ Payment Rejected\n\n"
            f"🛒 Product: {order['cat_name']}\n"
            f"💰 Amount: Br {order['price']:.2f}\n\n"
            f"Your payment screenshot could not be verified.\n"
            f"Please contact support if you believe this is a mistake.",
            keyboard=build_keyboard([
                [btn("Back to Home", "back_main", emoji_key="back")]
            ])
        )

        # Update admin message
        await edit_caption(
            chat_id, mid,
            f"❌ REJECTED — Order #{order_id[:8].upper()}\n\n"
            f"🛒 {order['cat_name']}\n"
            f"💰 Br {order['price']:.2f}\n"
            f"👤 User ID: {order['user_id']}"
        )
        await answer_cb(cq_id, "❌ Order rejected. User has been notified.")

    elif data == "history":
        user_id = user.get("id")
        async with _ord_lock:
            all_orders = _load_orders()
        user_orders = [
            o for o in all_orders.values()
            if o["user_id"] == str(user_id)
        ]
        user_orders.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        recent = user_orders[:5]

        m = Msg()
        m.emoji("clipboard").text(" ").bold("Order ").italic("History").nl(2)
        if not recent:
            m.emoji("box").text(" ").italic("No orders yet.").nl(2)
            m.text("Start shopping to see your orders here!")
        else:
            for o in recent:
                status = o["status"]
                if status == "approved":
                    m.emoji("check")
                elif status in ("pending_payment", "pending_approval"):
                    m.emoji("timer")
                else:
                    m.emoji("cross")
                m.text(" ").bold(o["cat_name"]).nl()
                m.emoji("balance").text(f" Br {o['price']:.2f}").text(f"  •  {o['created_at'][:10]}").nl(2)
        t, ent = m.build()
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_msg(chat_id, t, ent,
            keyboard=build_keyboard([[btn("🏠 Home", "back_main")]])
        )

    elif data == "bot_logs" or data.startswith("botlogs_"):
        parts = data.split("_")
        if data == "bot_logs":
            filter_type = "all"
            page = 0
        elif len(parts) >= 4 and parts[1] == "refresh":
            filter_type = parts[2]
            page = int(parts[3]) if parts[3].isdigit() else 0
        elif len(parts) >= 3:
            filter_type = parts[1]
            page = int(parts[2]) if parts[2].isdigit() else 0
        else:
            filter_type = "all"
            page = 0

        (t, ent), total_pages, counts_map = build_bot_logs(filter_type, page, per_page=5, viewer_id=user.get("id"))
        kb = kb_bot_logs(filter_type, page, total_pages, counts_map)

        res = await edit_msg(chat_id, mid, t, ent, kb)
        if not res.get("ok"):
            try:
                await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
            except Exception:
                pass
            await send_msg(chat_id, t, ent, kb)

    elif data in ("admincat_type_link", "admincat_type_id_pass"):
        # Admin pressed type button during /addcategory flow
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        state = _admin_state.get(uid)
        if not state or state.get("step") != "addcat_type":
            await answer_cb(cq_id, "⚠️ No active category creation flow.", alert=True)
            return

        cat_type   = "link" if data == "admincat_type_link" else "id_pass"
        type_label = "🔗 Link" if cat_type == "link" else "🔐 ID & Pass"
        state["data"]["cat_type"] = cat_type
        state["step"] = "addcat_desc"   # NEW: ask for description next

        await answer_cb(cq_id, f"Selected: {type_label}")
        await edit_msg(chat_id, mid,
            f"✅ Type selected: {type_label}\n\n"
            f"📝 Now send the product description.\n\n"
            f"This will be shown to users on the product detail page.\n"
            f"You can use multiple lines. Example:\n\n"
            f"📦 Product Details\n"
            f"Includes 1 month Netflix Premium access.\n\n"
            f"� Requirements\n"
            f"• Active internet connection\n"
            f"• Mobile or PC\n\n"
            f"Or send — to skip and use a default description."
        )

    # ── ADMIN PANEL CALLBACKS ──────────────────────────────────
    # ── Admin In-Bot Giveaway Flow ───────────────────────────────────
    elif data == "admin_giveaways":
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        cats = await cat_get_all()
        t, ent = build_admin_giveaway_select(cats)
        kb = kb_admin_giveaway_select(cats)
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_msg(chat_id, t, ent, kb)

    elif data.startswith("admgw_sel_"):
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        cat_id = data[10:]
        cats = await cat_get_all()
        cat = cats.get(cat_id)
        if not cat:
            await answer_cb(cq_id, "❌ Product not found.", alert=True)
            return
            
        gw = await giveaway_create(cat_id, uid)
        t, ent = build_admin_giveaway_preview(cat, gw["id"])
        kb = kb_admin_giveaway_preview(gw["id"])
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_msg(chat_id, t, ent, kb)

    elif data.startswith("admgw_broadcast_"):
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        gw_id = data[16:]
        real_id = f"gw_{gw_id}" if not gw_id.startswith("gw_") else gw_id
        gw = await giveaway_get(real_id)
        if not gw:
            await answer_cb(cq_id, "❌ Giveaway not found.", alert=True)
            return
            
        gw["status"] = "active"
        async with _gw_lock:
            gws = _load_giveaways()
            gws[real_id] = gw
            _save_giveaways(gws)
            
        t, ent = build_inbot_giveaway_announcement(gw["cat_name"])
        kb = kb_inbot_giveaway(gw["id"])
        
        # Broadcast directly to all bot users
        users = _load_db()
        sent_count = 0
        await answer_cb(cq_id, "🚀 Broadcasting giveaway to all bot users...", alert=False)
        
        for u_id in users.keys():
            try:
                res = await send_msg(u_id, t, ent, kb)
                if res.get("ok"):
                    sent_count += 1
                await asyncio.sleep(0.035)
            except Exception:
                pass
                
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        t_pan, ent_pan = await build_admin_dashboard()
        full_t, full_ent = merge_with_prefix(f"✅ Giveaway #{gw['id']} broadcasted to {sent_count} users successfully!\n\n", t_pan, ent_pan)
        await send_msg(chat_id, full_t, full_ent, kb_admin_panel())

    elif data.startswith("admgw_cancel_"):
        gw_id = data[13:]
        real_id = f"gw_{gw_id}" if not gw_id.startswith("gw_") else gw_id
        async with _gw_lock:
            gws = _load_giveaways()
            if real_id in gws:
                del gws[real_id]
                _save_giveaways(gws)
        await answer_cb(cq_id, "Giveaway setup cancelled.", alert=False)
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        t_pan, ent_pan = await build_admin_dashboard()
        await send_msg(chat_id, t_pan, ent_pan, kb_admin_panel())

    elif data.startswith("claim_gw_"):
        gw_id = data[9:]
        await process_inbot_giveaway_claim(chat_id, user, gw_id, cq_id=cq_id, mid=mid)

    elif data == "admin_panel":
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        t, ent = await build_admin_dashboard()
        await send_msg(chat_id, t, ent, kb_admin_panel())

    elif data == "admin_products":
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        await answer_cb(cq_id)
        cats = await cat_get_all(include_disabled=True)
        counts = await get_all_stock_counts(cats)
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        
        enabled_count = sum(1 for c in cats.values() if c.get("enabled", True) is not False)
        disabled_count = len(cats) - enabled_count
        
        m = Msg()
        m.emoji("shop").text(" ").bold("Product Catalog Management").nl(2)
        m.emoji("check").text(f"  • Active in Shop: ").bold(f"{enabled_count}").nl()
        m.emoji("cross").text(f"  • Disabled (Hidden): ").bold(f"{disabled_count}").nl()
        m.emoji("box").text(f"  • Total in JSON: ").bold(f"{len(cats)}").nl(2)
        m.italic("Tap any product to toggle ON/OFF, change price, or remove:")
        t, ent = m.build()
        await send_msg(chat_id, t, ent, kb_admin_products(cats, counts))

    elif data == "admin_sync_safwan":
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        await answer_cb(cq_id, "🔄 Fetching latest products from API...", alert=False)
        res = await safwan_sync_products_to_json()
        if res.get("ok"):
            msg = f"✅ Synced with API!\nTotal: {res['total']} products\nNew added: {res['new']}\nUpdated: {res['updated']}"
            await answer_cb(cq_id, msg, alert=True)
        else:
            await answer_cb(cq_id, f"❌ Sync failed: {res.get('error')}", alert=True)
            
        cats = await cat_get_all(include_disabled=True)
        counts = await get_all_stock_counts(cats)
        enabled_count = sum(1 for c in cats.values() if c.get("enabled", True) is not False)
        disabled_count = len(cats) - enabled_count
        
        m = Msg()
        m.emoji("shop").text(" ").bold("Product Catalog Management").nl(2)
        m.emoji("check").text(f"  • Active in Shop: ").bold(f"{enabled_count}").nl()
        m.emoji("cross").text(f"  • Disabled (Hidden): ").bold(f"{disabled_count}").nl()
        m.emoji("box").text(f"  • Total in JSON: ").bold(f"{len(cats)}").nl(2)
        m.italic("Tap any product to toggle ON/OFF, change price, or remove:")
        t, ent = m.build()
        await edit_msg(chat_id, mid, t, ent, kb_admin_products(cats, counts))

    elif data.startswith("admin_toggle_"):
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        cid = data[13:]
        new_status = await cat_toggle_enabled(cid)
        status_msg = "🟢 Product turned ON (Now visible in customer shop)" if new_status else "🔴 Product turned OFF (Hidden from shop)"
        await answer_cb(cq_id, status_msg, alert=False)
        
        cats = await cat_get_all(include_disabled=True)
        cat = cats.get(cid)
        if cat:
            cnt = await stock_count(cid)
            t, ent = build_admin_product_card(cat, cnt)
            await edit_msg(chat_id, mid, t, ent, kb_admin_product_detail(cid, cat))

    elif data.startswith("admin_manage_cat_"):
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        cid = data[17:]
        cats = await cat_get_all(include_disabled=True)
        cat = cats.get(cid)
        if not cat:
            await answer_cb(cq_id, "❌ Product not found.", alert=True)
            return
        cnt = await stock_count(cid)
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        t, ent = build_admin_product_card(cat, cnt)
        await send_msg(chat_id, t, ent, kb_admin_product_detail(cid, cat))

    elif data.startswith("admin_editname_"):
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        cid = data[15:]
        cats = await cat_get_all()
        cat = cats.get(cid)
        if not cat:
            await answer_cb(cq_id, "❌ Product not found.", alert=True)
            return
        _admin_state[uid] = {"step": "admin_editname_quick", "data": {"cat_id": cid, "cat_name": cat["name"]}}
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        m = Msg()
        m.emoji("other").text(" ").bold(f"Edit Name for {cat['name']}").nl(2)
        m.text("Current Name: ").bold(cat["name"]).nl(2)
        m.italic("Type the new name for this product below (or tap Cancel to abort):")
        t, ent = m.build()
        await send_msg(chat_id, t, ent, keyboard=build_keyboard([[btn("❌ Cancel", f"admin_manage_cat_{cid}", emoji_key="cross")]]))

    elif data.startswith("admin_editemoji_preset_"):
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        parts = data.split("_")
        if len(parts) >= 5:
            cid = parts[3]
            emoji_char = parts[4]
            emoji_id = UNICODE_TO_CUSTOM_EMOJI.get(emoji_char, "")
            async with _cat_lock:
                cats = _load_categories()
                if cid in cats:
                    cats[cid]["emoji_char"] = emoji_char
                    cats[cid]["emoji_id"] = emoji_id
                    _save_categories(cats)
            _admin_state.pop(uid, None)
            await answer_cb(cq_id, f"✅ Icon updated to {emoji_char}!", alert=False)
            cnt = await stock_count(cid)
            cats = _load_categories()
            card_text, card_ent = build_admin_product_card(cats[cid], cnt)
            t, ent = merge_with_prefix(f"✅ Product icon updated to {emoji_char}!\n\n", card_text, card_ent)
            await edit_msg(chat_id, mid, t, ent, kb_admin_product_detail(cid, cats[cid]))

    elif data.startswith("admin_editemoji_"):
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        cid = data[16:]
        cats = await cat_get_all()
        cat = cats.get(cid)
        if not cat:
            await answer_cb(cq_id, "❌ Product not found.", alert=True)
            return
        _admin_state[uid] = {"step": "admin_editemoji_quick", "data": {"cat_id": cid, "cat_name": cat["name"]}}
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        m = Msg()
        m.emoji("star").text(" ").bold(f"Edit Icon / Emoji for {cat['name']}").nl(2)
        m.text("Current Icon: ")
        if cat.get("emoji_id"):
            m.custom_emoji(cat.get("emoji_char", "🛒"), cat["emoji_id"]).text(f" (Premium ID: `{cat['emoji_id']}`)\n\n")
        else:
            m.text(f"{cat.get('emoji_char', '🛒')}\n\n")
        m.italic("Send ANY Telegram Premium Emoji, standard emoji, custom emoji ID, or choose a preset below:\n(Or tap Cancel to abort)")
        t, ent = m.build()
        kb = build_keyboard([
            [btn("🍿 Cinema", f"admin_editemoji_preset_{cid}_🍿"),
             btn("💎 Premium", f"admin_editemoji_preset_{cid}_💎"),
             btn("⚡ Fast", f"admin_editemoji_preset_{cid}_⚡")],
            [btn("🤖 AI Tool", f"admin_editemoji_preset_{cid}_🤖"),
             btn("🛒 Market", f"admin_editemoji_preset_{cid}_🛒"),
             btn("🎁 Gift", f"admin_editemoji_preset_{cid}_🎁")],
            [btn("❌ Cancel", f"admin_manage_cat_{cid}", emoji_key="cross")]
        ])
        await send_msg(chat_id, t, ent, keyboard=kb)

    elif data.startswith("admin_editprice_"):
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        cid = data[16:]
        cats = await cat_get_all()
        cat = cats.get(cid)
        if not cat:
            await answer_cb(cq_id, "❌ Product not found.", alert=True)
            return
        _admin_state[uid] = {"step": "admin_editprice_quick", "data": {"cat_id": cid, "cat_name": cat["name"]}}
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_msg(chat_id,
            f"💰 *{cat['name']}*\n"
            f"Current price: Br {cat['price']:.2f}\n\n"
            f"Enter the new price in ETB (or /cancel):",
            keyboard=build_keyboard([[btn("Cancel", f"admin_manage_cat_{cid}", emoji_key="cross")]])
        )

    elif data.startswith("admin_editstock_"):
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        cid = data[16:]
        cats = await cat_get_all()
        cat = cats.get(cid)
        if not cat:
            await answer_cb(cq_id, "❌ Product not found.", alert=True)
            return
        cnt = await stock_count(cid)
        _admin_state[uid] = {"step": "admin_editstock_quick", "data": {"cat_id": cid, "cat_name": cat["name"]}}
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_msg(chat_id,
            f"📦 *{cat['name']}*\n"
            f"Current stock count: {cnt}\n\n"
            f"Enter the new stock quantity number (or /cancel):",
            keyboard=build_keyboard([[btn("Cancel", f"admin_manage_cat_{cid}", emoji_key="cross")]])
        )

    elif data.startswith("admin_delete_"):
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        cid = data[13:]
        cats = await cat_get_all()
        cat = cats.get(cid)
        if not cat:
            await answer_cb(cq_id, "❌ Product not found.", alert=True)
            return
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_msg(chat_id,
            f"⚠️ Are you sure you want to delete *{cat['name']}*?\n\nThis will remove the product and all associated stock.",
            keyboard=build_keyboard([
                [btn("🗑 Yes, Delete Product", f"admin_confirm_del_{cid}", emoji_key="cross")],
                [btn("❌ Cancel", f"admin_manage_cat_{cid}", emoji_key="back")],
            ])
        )

    elif data.startswith("admin_confirm_del_"):
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        cid = data[18:]
        cats = await cat_get_all()
        cat = cats.get(cid)
        cat_name = cat["name"] if cat else cid
        await cat_delete(cid)
        await answer_cb(cq_id, f"✅ Deleted {cat_name}!")
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        updated_cats = await cat_get_all()
        counts = await get_all_stock_counts(updated_cats)
        await send_msg(chat_id, f"✅ Product *{cat_name}* was deleted.", keyboard=kb_admin_products(updated_cats, counts))

    elif data == "admin_addcat":
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        _admin_state[uid] = {"step": "addcat_name", "data": {}}
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_msg(chat_id,
            "📝 *Step 1/4: Enter Product Name*\n\nType the name for this product (e.g. `Netflix 4K UHD`):",
            keyboard=build_keyboard([[btn("Cancel", "admin_products", emoji_key="cross")]])
        )

    elif data.startswith("admin_addcat_preset_emoji_"):
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        state = _admin_state.get(uid)
        if not state or state.get("step") != "addcat_emoji":
            await answer_cb(cq_id, "⚠️ Invalid state.", alert=True)
            return
        preset_char = data[26:] or "🛒"
        state["data"]["emoji_char"] = preset_char
        state["data"]["emoji_id"]   = ""
        state["step"] = "addcat_type"
        await answer_cb(cq_id, f"Selected: {preset_char}")
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        m = Msg()
        m.emoji("check").text(f" Product Icon Selected: {preset_char}\n\n")
        m.bold("Step 4/4: Select Delivery Type:\n\n")
        m.text("🔗 Link — Admin uploads activation links or invite URLs.\n")
        m.text("🔐 ID & Pass — Admin uploads email:password account credentials.")
        t, ent = m.build()
        await send_msg(chat_id, t, ent, keyboard=build_keyboard([
            [btn("🔗 Link", "admincat_type_link"),
             btn("🔐 ID & Pass", "admincat_type_id_pass")],
            [btn("Cancel", "admin_products", emoji_key="cross")]
        ]))

    elif data in ("admincat_type_link", "admin_addtype_link", "admincat_type_id_pass", "admin_addtype_account"):
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        state = _admin_state.get(uid)
        if not state or state.get("step") != "addcat_type":
            await answer_cb(cq_id, "⚠️ No active category creation flow.", alert=True)
            return

        cat_type   = "link" if "link" in data else "id_pass"
        type_label = "🔗 Link" if cat_type == "link" else "🔐 ID & Pass"
        state["data"]["cat_type"] = cat_type
        state["step"] = "addcat_safwan"

        await answer_cb(cq_id, f"Selected: {type_label}")
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_msg(chat_id,
            f"✅ Delivery Type: *{type_label}*\n\n"
            "⚡ *Optional: Safwan Supplier Automated Delivery*\n"
            "If you want SafwanTiger to automatically fulfill this product, enter the Safwan Product ID (or tap Skip):",
            keyboard=build_keyboard([[btn("Skip (Local Stock)", "admin_addtype_nosafwan")]])
        )

    elif data == "admin_addtype_nosafwan":
        uid = user.get("id")
        if uid in _admin_state and _admin_state[uid].get("step") == "addcat_safwan":
            _admin_state[uid]["data"]["safwan_id"] = None
            _admin_state[uid]["step"] = "addcat_desc"
            await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
            await send_msg(chat_id,
                "📝 *Enter Product Description:*\n\n"
                "Send the description to display on the customer product card.\n"
                "Supports multiple lines, formatting, and Telegram Premium custom emojis!\n\n"
                "Send *skip* or *—* to skip description.",
                keyboard=build_keyboard([[btn("Skip Description", "admin_addcat_skip_desc")]])
            )

    elif data == "admin_addcat_skip_desc":
        uid = user.get("id")
        if uid in _admin_state and _admin_state[uid].get("step") == "addcat_desc":
            _admin_state[uid]["data"]["description"] = ""
            _admin_state[uid]["data"]["desc_entities"] = []
            _admin_state[uid]["step"] = "addcat_confirm"
            d = _admin_state[uid]["data"]
            type_label = "🔗 Link" if d.get("cat_type") == "link" else "🔐 ID & Pass"
            
            m = Msg()
            m.emoji("star").text(" ").bold("Confirm New Product").nl()
            m.text("━━━━━━━━━━━━━━━━━━━━").nl()
            m.text("• Icon: ")
            if d.get("emoji_id"):
                m.custom_emoji(d.get("emoji_char", "🛒"), d["emoji_id"]).text(f" (Premium ID: `{d['emoji_id']}`)\n")
            else:
                m.text(f"{d.get('emoji_char', '🛒')}\n")
            m.text("• Name: ").bold(d["name"]).nl()
            m.text("• Price: ").bold(f"Br {d['price']:,.2f}").nl()
            m.text("• Type: ").bold(type_label).nl()
            if d.get("safwan_id"):
                m.text("• Safwan Supplier ID: ").code(str(d["safwan_id"])).nl()
            m.text("━━━━━━━━━━━━━━━━━━━━").nl()
            m.italic("Tap Confirm below to save the product to the store:")
            t, ent = m.build()
            await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
            await send_msg(chat_id, t, ent, keyboard=build_keyboard([
                [btn("✅ Confirm & Save Product", "admin_addcat_confirm", emoji_key="check", style="success")],
                [btn("❌ Cancel", "admin_products", emoji_key="cross")],
            ]))

    elif data == "admin_addcat_confirm":
        uid = user.get("id")
        if uid in _admin_state and _admin_state[uid].get("step") == "addcat_confirm":
            d = _admin_state[uid]["data"]
            cat_id = d["name"].lower().replace(" ", "_")
            await cat_save(cat_id, d["name"], d["price"],
                           d.get("emoji_char", "🛒"), d.get("emoji_id", ""),
                           d.get("cat_type", "id_pass"),
                           d.get("description", ""),
                           d.get("desc_entities", []))
            if d.get("safwan_id"):
                async with _cat_lock:
                    all_cats = _load_categories()
                    if cat_id in all_cats:
                        all_cats[cat_id]["safwan_product_id"] = d["safwan_id"]
                        _save_categories(all_cats)
            _admin_state.pop(uid, None)
            await answer_cb(cq_id, f"✅ Product {d['name']} created!", alert=True)
            await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
            cats = await cat_get_all()
            counts = await get_all_stock_counts(cats)
            card_text, card_ent = build_admin_product_card(cats.get(cat_id, {}), 0)
            
            m = Msg()
            m.emoji("check").text(" ").bold(f"Product {d['name']} added successfully!").nl(2)
            m.text(card_text)
            full_t, base_ent = m.build()
            prefix_len = u16(full_t) - u16(card_text)
            merged_ent = base_ent + [dict(e, offset=e['offset'] + prefix_len) for e in card_ent]
            await send_msg(chat_id, full_t, merged_ent, keyboard=kb_admin_product_detail(cat_id))

    elif data == "admin_broadcast":
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        _admin_state[uid] = {"step": "admin_broadcast_msg", "data": {}}
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_msg(chat_id,
            "📢 Send the announcement message to broadcast to all customers:\n\n"
            "(Supports text, markdown, links. Type /cancel to abort.)",
            keyboard=build_keyboard([[btn("Cancel", "admin_panel", emoji_key="cross")]])
        )

    elif data == "admin_users":
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        _admin_state[uid] = {"step": "admin_user_lookup", "data": {}}
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        users = _load_db()
        await send_msg(chat_id,
            f"👥 Customers Registered: {len(users)}\n\n"
            "Send the customer's Telegram User ID or @username to view their profile & manage balance:",
            keyboard=build_keyboard([[btn("Cancel", "admin_panel", emoji_key="cross")]])
        )

    elif data.startswith("admgive_"):
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        parts = data.split("_")
        target_uid = parts[1]
        amount = float(parts[2])
        await db_add_balance(target_uid, amount)
        users = _load_db()
        new_bal = users.get(target_uid, {}).get("balance", 0.0)
        try:
            um = Msg()
            um.emoji("wallet").text(" Your account was credited ").bold(f"Br {amount:.2f}").nl()
            um.emoji("balance").text(f" New Balance: ").bold(f"Br {new_bal:.2f}")
            ut, ue = um.build()
            await send_msg(int(target_uid), ut, ue)
        except Exception:
            pass
        await answer_cb(cq_id, f"✅ Added Br {amount:.2f}! New Balance: Br {new_bal:.2f}", alert=True)

    elif data.startswith("admresetbal_"):
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        target_uid = data[12:]
        async with _db_lock:
            db_data = _load_db()
            if target_uid in db_data:
                db_data[target_uid]["balance"] = 0.0
                _save_db(db_data)
        await answer_cb(cq_id, f"✅ Balance reset to Br 0.00 for user {target_uid}", alert=True)

    elif data == "admin_pending":
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        t, pending = build_admin_pending_orders()
        text_content, entities = t
        kb_rows = []
        for o in pending[:6]:
            if o.get("status") == "pending_approval":
                kb_rows.append([
                    btn(f"✅ Approve #{o['order_id'][:6]}", f"approve_{o['order_id']}", emoji_key="check", style="success"),
                    btn(f"❌ Reject", f"reject_{o['order_id']}", emoji_key="cross")
                ])
            elif o.get("status") == "awaiting_delivery":
                kb_rows.append([
                    btn(f"🔗 Deliver #{o['order_id'][:6]} ({o['cat_name'][:12]})", f"deliver_{o['order_id']}", emoji_key="channel", style="success")
                ])
        kb_rows.append([btn("Back to Admin Panel", "admin_panel", emoji_key="back")])
        await send_msg(chat_id, text_content, entities, build_keyboard(kb_rows))

    elif data in ("admin_settings", "admin_payment_info"):
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        t, ent = await build_admin_settings_screen()
        await send_msg(chat_id, t, ent, kb_admin_settings())

    elif data == "admset_vet_key":
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        _admin_state[uid] = {"step": "admin_set_vet_key", "data": {}}
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_msg(chat_id,
            "🔑 *Set Verify.ET API Key*\n\n"
            "Send your Verify.ET API Key to enable automated payment verification.\n\n"
            "Type /cancel to abort.",
            keyboard=build_keyboard([[btn("Cancel", "admin_settings", emoji_key="cross")]])
        )

    elif data == "admset_safwan_key":
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        _admin_state[uid] = {"step": "admin_set_safwan_key", "data": {}}
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_msg(chat_id,
            "⚡ *Set SafwanTiger Reseller API Key*\n\n"
            "Send your SafwanTiger API Key (starts with `stapi_...`) to connect automated product delivery.\n\n"
            "Type /cancel to abort.",
            keyboard=build_keyboard([[btn("Cancel", "admin_settings", emoji_key="cross")]])
        )

    elif data == "admset_log_ch":
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        _admin_state[uid] = {"step": "admin_set_log_ch", "data": {}}
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_msg(chat_id,
            "📢 *Set Sales Log Channel ID*\n\n"
            "Send your Telegram Channel Chat ID (e.g. `-1003806764959`).\n"
            "⚠️ Note: Make sure the bot is an Admin in this channel!\n\n"
            "Type /cancel to abort.",
            keyboard=build_keyboard([[btn("Cancel", "admin_settings", emoji_key="cross")]])
        )

    elif data == "admset_fj_id":
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        _admin_state[uid] = {"step": "admin_set_fj_id", "data": {}}
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_msg(chat_id,
            "🔒 *Set Force Join Channel ID*\n\n"
            "Send your Force Join Channel Chat ID (e.g. `-1003806764959`).\n"
            "⚠️ Note: The bot must be an Admin in this channel to verify membership.\n\n"
            "Type /cancel to abort.",
            keyboard=build_keyboard([[btn("Cancel", "admin_settings", emoji_key="cross")]])
        )

    elif data == "admset_fj_link":
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        _admin_state[uid] = {"step": "admin_set_fj_link", "data": {}}
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_msg(chat_id,
            "🔗 *Set Force Join Channel Link*\n\n"
            "Send your Channel Invite Link (e.g. `https://t.me/et_market_place`).\n\n"
            "Type /cancel to abort.",
            keyboard=build_keyboard([[btn("Cancel", "admin_settings", emoji_key="cross")]])
        )

    elif data == "admset_telebirr":
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        _admin_state[uid] = {"step": "admin_set_telebirr_name", "data": {}}
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_msg(chat_id,
            "💙 *Update Telebirr Details*\n\n"
            "Step 1/2: Send the Account Holder Name (e.g. `Gelana WoldaYesus`):\n\n"
            "Type /cancel to abort.",
            keyboard=build_keyboard([[btn("Cancel", "admin_settings", emoji_key="cross")]])
        )

    elif data == "admset_cbe":
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        _admin_state[uid] = {"step": "admin_set_cbe_name", "data": {}}
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_msg(chat_id,
            "🏦 *Update Commercial Bank of Ethiopia (CBE) Details*\n\n"
            "Step 1/2: Send the CBE Account Holder Name (e.g. `Naol Meseret Fransua`):\n\n"
            "Type /cancel to abort.",
            keyboard=build_keyboard([[btn("Cancel", "admin_settings", emoji_key="cross")]])
        )

    elif data == "admset_cbebirr":
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        _admin_state[uid] = {"step": "admin_set_cbebirr_name", "data": {}}
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_msg(chat_id,
            "🏦 *Update CBE Birr Details*\n\n"
            "Step 1/2: Send the CBE Birr Account Holder Name (e.g. `Naol Meseret`):\n\n"
            "Type /cancel to abort.",
            keyboard=build_keyboard([[btn("Cancel", "admin_settings", emoji_key="cross")]])
        )

    elif data == "admset_admins":
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        _admin_state[uid] = {"step": "admin_set_admins", "data": {}}
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        cur_admins = ", ".join(str(a) for a in ADMINS)
        await send_msg(chat_id,
            f"👥 *Update Admin User IDs*\n\n"
            f"Current Admins: `{cur_admins}`\n\n"
            "Send the new comma-separated list of Telegram numeric User IDs (e.g. `6241860023, 8708984302`).\n\n"
            "Type /cancel to abort.",
            keyboard=build_keyboard([[btn("Cancel", "admin_settings", emoji_key="cross")]])
        )

    elif data == "admin_custom_texts":
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        t, ent = build_admin_custom_texts_menu()
        await send_msg(chat_id, t, ent, kb_admin_custom_texts())

    elif data.startswith("admtxt_edit_"):
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        key = data[12:]
        if key not in RESPONSE_TEMPLATES:
            await answer_cb(cq_id, "❌ Invalid template key.", alert=True)
            return
        _admin_state[uid] = {"step": "admtxt_input", "data": {"key": key}}
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        (t, ent), kb = build_admin_edit_template_prompt(key)
        await send_msg(chat_id, t, ent, kb)

    elif data.startswith("admtxt_reset_"):
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        key = data[13:]
        info = RESPONSE_TEMPLATES.get(key, {"name": key})
        await reset_custom_response(key)
        _admin_state.pop(uid, None)
        await answer_cb(cq_id, f"✅ {info['name']} reset to default!", alert=False)
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        t, ent = build_admin_custom_texts_menu()
        full_t, full_ent = merge_with_prefix(f"✅ *{info['name']}* restored to default built-in message!\n\n", t, ent)
        await send_msg(chat_id, full_t, full_ent, kb_admin_custom_texts())

    elif data == "admtxt_reset_all":
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        await send_msg(chat_id,
            "⚠️ *Are you sure you want to reset ALL bot messages to default?*\n\n"
            "This will clear all customized messages (welcome, terms, support, etc.) and restore factory defaults.",
            keyboard=build_keyboard([
                [btn("🗑 Yes, Reset Everything", "admtxt_confirm_reset_all", emoji_key="cross", style="danger")],
                [btn("❌ Cancel", "admin_custom_texts", emoji_key="back")],
            ])
        )

    elif data == "admtxt_confirm_reset_all":
        uid = user.get("id")
        if not is_admin(uid):
            await answer_cb(cq_id, "⛔ Admins only.", alert=True)
            return
        await reset_all_custom_responses()
        _admin_state.pop(uid, None)
        await answer_cb(cq_id, "✅ All custom messages reset to default!", alert=True)
        await api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        t, ent = build_admin_custom_texts_menu()
        full_t, full_ent = merge_with_prefix("✅ *All bot messages have been reset to factory defaults!*\n\n", t, ent)
        await send_msg(chat_id, full_t, full_ent, kb_admin_custom_texts())

    else:
        await answer_cb(cq_id, "✅ Coming soon!", alert=True)

# ─── PRODUCTION DISPATCHERS ───────────────────────────────────
async def safe_handle_message(msg: dict):
    try:
        await handle_message(msg)
    except Exception as ex:
        logger.error(f"[safe_handle_message] Unhandled error: {ex}", exc_info=True)

async def safe_handle_callback(cq: dict):
    try:
        await handle_callback(cq)
    except Exception as ex:
        logger.error(f"[safe_handle_callback] Unhandled error: {ex}", exc_info=True)

async def process_update(upd: dict):
    """Process a single Telegram update (message or callback_query)."""
    if "message" in upd:
        msg = upd["message"]
        uid = msg.get("from", {}).get("id")
        if uid and throttler.is_throttled(uid):
            logger.warning(f"[RateLimit] Throttled rapid messages from user {uid}")
            return
        await safe_handle_message(msg)

    elif "callback_query" in upd:
        cq = upd["callback_query"]
        uid = cq.get("from", {}).get("id")
        if uid and throttler.is_throttled(uid):
            await answer_cb(cq.get("id", ""), "⏳ Please slow down...", alert=False)
            return
        await safe_handle_callback(cq)

# ─── PRODUCTION POLLING LOOP ──────────────────────────────────
async def poll():
    offset = 0
    consecutive_errors = 0
    logger.info("⚡ [PRODUCTION] Polling started — ET Market Bot is LIVE!")
    
    # Run initial database snapshot
    create_database_backup()
    
    # Launch background backup scheduler
    backup_task = asyncio.create_task(backup_scheduler_loop())

    try:
        while True:
            try:
                data = await api_call("getUpdates", {
                    "offset":          offset,
                    "timeout":         25,
                    "allowed_updates": ["message", "callback_query"],
                })
                if not data.get("ok"):
                    desc = data.get("description", "")
                    if "Conflict" in desc:
                        logger.warning("Conflict detected — another instance running. Waiting 15s...")
                        await asyncio.sleep(15)
                    else:
                        consecutive_errors += 1
                        sleep_time = min(2 ** consecutive_errors, 30)
                        logger.warning(f"[poll] getUpdates error: {desc}. Backing off {sleep_time}s...")
                        await asyncio.sleep(sleep_time)
                    continue

                consecutive_errors = 0
                for upd in data.get("result", []):
                    offset = upd["update_id"] + 1
                    asyncio.create_task(process_update(upd))

            except asyncio.CancelledError:
                logger.info("[poll] Received termination signal, shutting down polling loop...")
                break
            except Exception as ex:
                consecutive_errors += 1
                sleep_time = min(2 ** consecutive_errors, 30)
                logger.error(f"[poll] Unexpected loop error: {ex}. Retrying in {sleep_time}s...")
                await asyncio.sleep(sleep_time)
    finally:
        backup_task.cancel()
        create_database_backup()

# ─── SET BOT COMMANDS (Hamburger Menu) ───────────────────────
async def set_bot_commands():
    """Register bot commands so they appear in Telegram's hamburger menu."""
    commands = [
        {"command": "start",    "description": "🏠 Main menu — Welcome screen"},
        {"command": "shop",     "description": "🛒 Browse products & buy"},
        {"command": "profile",  "description": "👤 View your profile & stats"},
        {"command": "wallet",   "description": "💳 Check wallet balance & deposit"},
        {"command": "history",  "description": "📜 View your order history"},
        {"command": "referral", "description": "👥 Invite friends & earn rewards"},
        {"command": "support",  "description": "🎧 Contact official support"},
        {"command": "channel",  "description": "📢 Join official channel"},
        {"command": "help",     "description": "❓ Terms & help information"},
    ]
    data = await api_call("setMyCommands", {"commands": commands})
    if data.get("ok"):
        logger.info("✅ Bot commands (hamburger menu) set successfully.")
    else:
        logger.warning(f"⚠️ Failed to set bot commands: {data.get('description','?')}")
    
    # Configure Telegram Chat Menu Button [Menu]
    btn_data = await api_call("setChatMenuButton", {"menu_button": {"type": "commands"}})
    if btn_data.get("ok"):
        logger.info("✅ Telegram [Menu] rectangle button configured successfully.")
    else:
        logger.warning(f"⚠️ Failed to set chat menu button: {btn_data.get('description','?')}")

# ─── MAIN — Python 3.14 compatible ───────────────────────────
async def main():
    logger.info("=" * 50)
    logger.info("ET Market Bot Starting...")
    logger.info("=" * 50)
    await db_init()
    # Register hamburger menu commands
    await set_bot_commands()
    # Clear any active webhook so polling works cleanly
    await api_call("deleteWebhook", {"drop_pending_updates": False})
    try:
        await poll()
    finally:
        await close_session()
        logger.info("Bot stopped.")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        try:
            loop.close()
        except Exception:
            pass

