import asyncio
import sqlite3
import random
import logging
import os
import html
import time
import aiohttp
import hmac
import hashlib
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any

from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message, Dice, BufferedInputFile
)


# ==============================================================================
# 1. BOT CONFIGURATION & CONSTANTS
# ==============================================================================
# Telegram bot token: keep it outside the source code.
# Put the fresh token from @BotFather in bot_token.txt next to this file,
# or set the BOT_TOKEN environment variable before starting the bot.
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_token.txt")

# Load the token from an environment variable first, otherwise from bot_token.txt.
# Never keep an expired/revoked token hard-coded in the source.
BOT_TOKEN = os.getenv("BOT_TOKEN", "8827168216:AAEnS_sZVPsns_d1lDBKRnus3Tzi4t4w-QM").strip()
if not BOT_TOKEN and os.path.exists(TOKEN_FILE):
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as _f:
            BOT_TOKEN = _f.read().strip()
    except OSError as exc:
        raise RuntimeError(f"Unable to read {TOKEN_FILE}: {exc}") from exc

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is missing. Put your fresh BotFather token in bot_token.txt "
        "next to this script, or set the BOT_TOKEN environment variable."
    )
BOT_USERNAME = os.getenv("BOT_USERNAME", "@DarkGhostStore_Bot").strip()
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "7531023551").strip())
except ValueError:
    raise RuntimeError("ADMIN_ID must be a numeric Telegram user ID.")
ADMIN_CONTACT = os.getenv("ADMIN_CONTACT", "@DGM100K").strip()

CLIENT_MODE = os.getenv("BOT_MODE", "owner").strip().lower() == "client"
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Cuibcc.db")
DB_PATH = os.path.abspath(os.getenv("BOT_DB_PATH", DEFAULT_DB_PATH))
CLIENT_BOT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "client_bots")

FAMPAY_API_KEY = "YOUR_FAMPAY_API_KEY"  # Replace with your actual API key
FAMPAY_QR_URL = "https://fampay.anujbots.xyz/qr.php"
FAMPAY_VERIFY_URL = "https://fampay.anujbots.xyz/verify.php"

USDT_TO_INR = 90.0
VIP_DISCOUNT_PERCENTAGE = 10.0
VIP_PRICE_INR = 1000.0

# Daily Lucky Spin configuration. The reward is deliberately capped below ₹2.00.
SPIN_COOLDOWN_HOURS = 24
SPIN_MIN_REWARD = 0.50
SPIN_MAX_REWARD = 1.00
SPIN_HARD_CEILING = 2.00
DEFAULT_REFERRAL_COMMISSION = 5.0

# External reseller API configuration (credentials are stored in DB settings, not hard-coded in product records).
RESELLER_API_URL = "https://bantibhaiya.to/api/reseller_v1.php"
RESELLER_API_KEY_DEFAULT = os.getenv("RESELLER_API_KEY", "").strip()
RESELLER_MASTER_KEY_DEFAULT = os.getenv("RESELLER_MASTER_KEY", "").strip()

WELCOME_STICKER_ID = "CAACAgIAAxkBAAEU-WZmH_..."  # Replace with your sticker ID

# ==============================================================================
# YOUR PREMIUM EMOJIS – all required emoji IDs (updated with new premium ones)
# ==============================================================================
DEFAULT_EMOJIS = {
    'product_store': '6163205892834598715',
    'profile': '5258011929993026890',
    'add_balance': '5985630530111020079',
    'history': '6032594876506312598',
    'support': '5967280668885913944',
    'back': '5877536313623711363',
    'upi': '5807750375033278838',
    'reseller': '5886505193180239900',
    'tutorial': '6005986106703613755',
    'telegram': '5875465628285931233',
    'whatsapp': '5954224165874569584',
    'welcome': '5994502837327892086',
    'vip': '5206607081334906820',
    'category_android_non_root': '6161172706856282588',
    'category_android_root': '6161449831031118974',
    'category_pc': '5350554349074391003',
    'grid_id': '5474625972751837256',
    'name': '5215399540814781035',
    'account_level': '6129584162992034014',
    'regular_user': '5904630315946611415',
    'wallet': '6210859306602995217',
    'current_balance': '5316711376876485361',
    'global_stats': '6161437856662298090',
    'total_orders': '6160968017304888311',
    'total_spent': '5197503331215361533',
    'joined_grid': '5433614043006903194',
    'info_icon': '6037421444789440735',
    'check_icon': '6161241250239356403',
    'checkbox_icon': '6161437856662298090',
    'shield_icon': '6086672466132865380',
    'money_icon': '5890848474563352982',
    'redeem_icon': '5377624166436445368',
    'wallet_left': '6210859306602995217',
    'wallet_right': '5305699699204837855',
    'point_down': '6161302621027049305',
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.getenv("BOT_LOG_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_activity.log"))),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

def fmt_curr(amount: float) -> str:
    return f"₹{amount:,.2f}"

def safe_float(val, default=0.0):
    """Safely convert a value to float, return default if fails."""
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def selector_token(value: str, length: int = 12) -> str:
    """Create a short, stable callback token within Telegram's callback-data limit."""
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()[:length]

def resolve_category_token(token: str) -> Optional[str]:
    rows = db_query("SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category != ''", fetchall=True) or []
    for row in rows:
        category = str(row[0])
        if selector_token(category) == token:
            return category
    return None

def resolve_panel_token(category: str, token: str) -> Optional[str]:
    rows = db_query(
        "SELECT DISTINCT panel_name FROM products WHERE category LIKE ? AND is_active=1 AND panel_name IS NOT NULL AND panel_name != ''",
        (category + '%',), fetchall=True
    ) or []
    for row in rows:
        panel = str(row[0])
        if selector_token(panel) == token:
            return panel
    return None

# ==============================================================================
# 2. DATABASE FUNCTIONS
# ==============================================================================
def db_query(query: str, params: tuple = (), fetchone: bool = False, fetchall: bool = False, commit: bool = True) -> Any:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute(query, params)
        if fetchone:
            res = c.fetchone()
        elif fetchall:
            res = c.fetchall()
        else:
            res = None
        if commit: conn.commit()
        return res
    except Exception as e:
        logger.error(f"DB Error: {e} | Query: {query} | Params: {params}")
        if commit: conn.rollback()
        return None
    finally:
        conn.close()

def get_setting(key: str, default: str = "") -> str:
    val = db_query("SELECT value FROM settings WHERE key=?", (key,), fetchone=True)
    return val[0] if val and val[0] else default

def set_setting(key: str, value: str) -> None:
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

def log_activity(user_id: int, action: str, details: str = "") -> None:
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db_query(
            "INSERT INTO activity_logs (user_id, action, details, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, action, details, timestamp)
        )
    except Exception as e:
        logger.error(f"Failed to log activity: {e}")

def credit_referral_commission(user_id: int, amount: float, source: str) -> None:
    """Credit the referrer with the configured commission (default 5%) exactly once per successful source event."""
    amount = safe_float(amount)
    if amount <= 0:
        return
    ref_row = db_query("SELECT referred_by FROM users WHERE user_id=?", (user_id,), fetchone=True)
    if not ref_row or not ref_row[0]:
        return
    commission_pct = safe_float(
        get_setting("referral_commission_percent", str(DEFAULT_REFERRAL_COMMISSION)),
        DEFAULT_REFERRAL_COMMISSION
    )
    commission = round(amount * commission_pct / 100.0, 2)
    if commission <= 0:
        return
    db_query(
        "UPDATE users SET balance=balance+?, team_earnings=team_earnings+? WHERE user_id=?",
        (commission, commission, ref_row[0])
    )
    log_activity(
        ref_row[0],
        "TEAM_COMMISSION",
        f"From user {user_id}: {commission} ({commission_pct:.2f}%) source={source}"
    )

def get_emoji(slot: str, default_id: str = None) -> str:
    stored = get_setting(f"emoji_{slot}", "")
    emoji_id = stored if stored and stored.isdigit() else (default_id or DEFAULT_EMOJIS.get(slot, ""))
    if emoji_id:
        return f'<tg-emoji emoji-id="{emoji_id}">✨</tg-emoji>'
    return "✨"

def get_emoji_icon(slot: str, default_id: str = None) -> str:
    stored = get_setting(f"emoji_{slot}", "")
    emoji_id = stored if stored and stored.isdigit() else (default_id or DEFAULT_EMOJIS.get(slot, ""))
    return emoji_id

# ==============================================================================
# 3. MULTI-LANGUAGE USER INTERFACE
# ==============================================================================
LANGUAGES = {
    "en": "🇬🇧 English", "hi": "🇮🇳 हिन्दी", "bn": "🇧🇩 বাংলা", "as": "🇮🇳 অসমীয়া",
    "ta": "🇮🇳 தமிழ்", "ur": "🇵🇰 اردو", "bho": "🇮🇳 भोजपुरी", "pa": "🇮🇳 ਪੰਜਾਬੀ",
    "gu": "🇮🇳 ગુજરાતી", "mr": "🇮🇳 मराठी", "or": "🇮🇳 ଓଡ଼ିଆ"
}

# These are deliberately kept in one resource table so selecting a language
# changes the same UI everywhere instead of changing only one menu.
I18N = {
    "en": {
        "language": "Language", "select_language": "🌐 <b>Select your preferred language:</b>",
        "product_store": "🛒 Shop / Store Product", "check_update": "🔄 Check Update", "add_balance": "💸 Add Balance",
        "profile": "👑 My Profile + Key History", "referral": "🔗 Referral", "howto": "❗ How To Use",
        "reseller": "👑 Upgrade To Reseller", "feedback": "↗ Check Public Feedback", "support": "📨 Support", "lucky": "🎁 Lucky",
        "back": "➡️ Back", "back_menu": "➡️ Back to Menu", "choose_product": "👑 Choose a product:",
        "choose_plan": "🤩 Choose a plan:", "add_funds": "💸 <b>ADD FUNDS TO WALLET</b>",
        "current_balance": "Current balance", "quick_amount": "Pick a quick amount below, or enter a custom amount.",
        "minmax": "Min: ₹1.00 · Max: ₹50,000.00", "custom_amount": "⌨️ Custom Amount",
        "enter_amount": "💰 <b>Enter Amount</b>", "confirm": "Confirm", "verify": "🟢 VERIFY PAYMENT",
        "cancel_payment": "➡️ Cancel Payment", "payment_cancelled": "❌ <b>Payment Cancelled</b>",
        "no_charge": "Your QR for {amount} was cancelled — no charge was made.", "try_again": "🛒 Try Again",
        "upi_qr": "💸 <b>UPI PAYMENT QR</b>", "scan_pay": "Scan & pay exactly <b>{amount}</b> via UPI.",
        "pay_after": "💳 Pay karne ke baad 'VERIFY PAYMENT' button dabayein.",
        "expires": "💳 This QR expires in 5 minutes.", "generating": "⏳ <b>Generating Secure QR Code...</b>",
        "upi": "UPI PAY", "binance": "BINANCE", "gateway_offline": "⚠️ Payment gateway is currently offline.",
        "back_to_plans": "➡️ Back to Plans", "cancel": "➡️ Cancel", "deposit_order_not_found": "Deposit order not found.",
        "verification_active": "🔄 <b>Verification Active</b>", "send_utr": "Please send your 12-digit UTR Number / UPI Ref No. here.",
        "send_cancel": "Send /cancel to stop.", "reseller_benefits": "📥 <b>Reseller Benefits:</b>",
        "maintain_wallet": "🤑 <b>Requirement:</b> Maintain ₹1,000.00 in wallet (Balance is NOT deducted!)",
        "your_balance": "Your Balance", "deficit": "Deficit Need", "select_gateway": "Select gateway to top-up deficit:",
        "send_proof": "📨 SEND PROOF TO SUPPORT", "cancel_order": "➡️ Cancel Order"
    },
    "hi": {
        "language": "भाषा", "select_language": "🌐 <b>अपनी पसंदीदा भाषा चुनें:</b>",
        "product_store": "🛒 शॉप / स्टोर प्रोडक्ट", "check_update": "🔄 अपडेट चेक करें", "add_balance": "💸 बैलेंस जोड़ें",
        "profile": "👑 मेरी प्रोफाइल + की हिस्ट्री", "referral": "🔗 रेफरल", "howto": "❗ कैसे इस्तेमाल करें",
        "reseller": "👑 रीसेलर बनें", "feedback": "↗ पब्लिक फीडबैक देखें", "support": "📨 सपोर्ट", "lucky": "🎁 लकी",
        "back": "➡️ वापस", "back_menu": "➡️ मेनू पर वापस", "choose_product": "👑 प्रोडक्ट चुनें:",
        "choose_plan": "🤩 प्लान चुनें:", "add_funds": "💸 <b>वॉलेट में पैसे जोड़ें</b>",
        "current_balance": "वर्तमान बैलेंस", "quick_amount": "नीचे से राशि चुनें या कस्टम राशि डालें।",
        "minmax": "न्यूनतम: ₹1.00 · अधिकतम: ₹50,000.00", "custom_amount": "⌨️ कस्टम राशि",
        "enter_amount": "💰 <b>राशि दर्ज करें</b>", "confirm": "पुष्टि करें", "verify": "🟢 पेमेंट सत्यापित करें",
        "cancel_payment": "➡️ पेमेंट रद्द करें", "payment_cancelled": "❌ <b>पेमेंट रद्द किया गया</b>",
        "no_charge": "₹{amount} का QR रद्द कर दिया गया — कोई शुल्क नहीं लिया गया।", "try_again": "🛒 फिर कोशिश करें",
        "upi_qr": "💸 <b>UPI पेमेंट QR</b>", "scan_pay": "UPI से ठीक <b>{amount}</b> स्कैन करके भुगतान करें।",
        "pay_after": "💳 भुगतान के बाद 'पेमेंट सत्यापित करें' बटन दबाएँ।",
        "expires": "💳 यह QR 5 मिनट में समाप्त हो जाएगा।", "generating": "⏳ <b>सुरक्षित QR बनाया जा रहा है...</b>",
        "upi": "UPI से भुगतान", "binance": "BINANCE", "gateway_offline": "⚠️ पेमेंट गेटवे अभी उपलब्ध नहीं है।",
        "back_to_plans": "➡️ प्लान पर वापस", "cancel": "➡️ रद्द करें", "deposit_order_not_found": "डिपॉजिट ऑर्डर नहीं मिला।",
        "verification_active": "🔄 <b>वेरिफिकेशन सक्रिय</b>", "send_utr": "अपना 12-अंकों का UTR नंबर / UPI Ref No. यहाँ भेजें।",
        "send_cancel": "रोकने के लिए /cancel भेजें।", "reseller_benefits": "📥 <b>रीसेलर लाभ:</b>",
        "maintain_wallet": "🤑 <b>जरूरत:</b> वॉलेट में ₹1,000.00 बनाए रखें (बैलेंस काटा नहीं जाएगा!)",
        "your_balance": "आपका बैलेंस", "deficit": "बाकी आवश्यक राशि", "select_gateway": "बाकी राशि जोड़ने के लिए गेटवे चुनें:",
        "send_proof": "📨 सपोर्ट को प्रूफ भेजें", "cancel_order": "➡️ ऑर्डर रद्द करें"
    },
    "bn": {"language":"ভাষা","select_language":"🌐 <b>আপনার পছন্দের ভাষা নির্বাচন করুন:</b>","product_store":"🛒 শপ / স্টোর প্রোডাক্ট","check_update":"🔄 আপডেট দেখুন","add_balance":"💸 ব্যালেন্স যোগ করুন","profile":"👑 আমার প্রোফাইল + কী হিস্টোরি","referral":"🔗 রেফারেল","howto":"❗ কীভাবে ব্যবহার করবেন","reseller":"👑 রিসেলার আপগ্রেড","feedback":"↗ পাবলিক ফিডব্যাক দেখুন","support":"📨 সাপোর্ট","lucky":"🎁 লাকি","back":"➡️ ফিরে যান","back_menu":"➡️ মেনুতে ফিরে যান","choose_product":"👑 একটি প্রোডাক্ট বেছে নিন:","choose_plan":"🤩 একটি প্ল্যান বেছে নিন:","add_funds":"💸 <b>ওয়ালেটে টাকা যোগ করুন</b>","current_balance":"বর্তমান ব্যালেন্স","quick_amount":"নিচের দ্রুত পরিমাণ বেছে নিন বা কাস্টম পরিমাণ দিন।","minmax":"সর্বনিম্ন: ₹1.00 · সর্বোচ্চ: ₹50,000.00","custom_amount":"⌨️ কাস্টম পরিমাণ","enter_amount":"💰 <b>পরিমাণ লিখুন</b>","confirm":"নিশ্চিত করুন","verify":"🟢 পেমেন্ট যাচাই করুন","cancel_payment":"➡️ পেমেন্ট বাতিল করুন","payment_cancelled":"❌ <b>পেমেন্ট বাতিল হয়েছে</b>","no_charge":"₹{amount} এর QR বাতিল হয়েছে — কোনো চার্জ নেওয়া হয়নি।","try_again":"🛒 আবার চেষ্টা করুন","upi_qr":"💸 <b>UPI পেমেন্ট QR</b>","scan_pay":"UPI দিয়ে ঠিক <b>{amount}</b> পেমেন্ট করুন।","pay_after":"💳 পেমেন্টের পর 'পেমেন্ট যাচাই' বোতাম চাপুন।","expires":"💳 এই QR ৫ মিনিটে শেষ হবে।","generating":"⏳ <b>নিরাপদ QR তৈরি হচ্ছে...</b>","upi":"UPI PAY","binance":"BINANCE","gateway_offline":"⚠️ পেমেন্ট গেটওয়ে এখন বন্ধ।","back_to_plans":"➡️ প্ল্যানে ফিরে যান","cancel":"➡️ বাতিল","deposit_order_not_found":"ডিপোজিট অর্ডার পাওয়া যায়নি।","verification_active":"🔄 <b>ভেরিফিকেশন সক্রিয়</b>","send_utr":"আপনার ১২-সংখ্যার UTR / UPI Ref No. এখানে পাঠান।","send_cancel":"বন্ধ করতে /cancel পাঠান।","reseller_benefits":"📥 <b>রিসেলার সুবিধা:</b>","maintain_wallet":"🤑 <b>প্রয়োজন:</b> ওয়ালেটে ₹1,000.00 রাখুন (ব্যালেন্স কাটা হবে না!)","your_balance":"আপনার ব্যালেন্স","deficit":"প্রয়োজনীয় বাকি","select_gateway":"বাকি টাকা যোগ করতে গেটওয়ে বেছে নিন:","send_proof":"📨 সাপোর্টে প্রুফ পাঠান","cancel_order":"➡️ অর্ডার বাতিল করুন"},
    "ta": {"language":"மொழி","select_language":"🌐 <b>உங்கள் மொழியைத் தேர்ந்தெடுக்கவும்:</b>","product_store":"🛒 கடை / பொருட்கள்","check_update":"🔄 புதுப்பிப்பைச் சரிபார்க்கவும்","add_balance":"💸 இருப்பைச் சேர்க்கவும்","profile":"👑 என் சுயவிவரம் + விசை வரலாறு","referral":"🔗 பரிந்துரை","howto":"❗ பயன்படுத்துவது எப்படி","reseller":"👑 ரீசெல்லராக மேம்படுத்து","feedback":"↗ பொது கருத்தைப் பார்க்கவும்","support":"📨 ஆதரவு","lucky":"🎁 லக்கி","back":"➡️ பின்செல்","back_menu":"➡️ மெனுவுக்கு பின்செல்","choose_product":"👑 ஒரு பொருளைத் தேர்ந்தெடுக்கவும்:","choose_plan":"🤩 ஒரு திட்டத்தைத் தேர்ந்தெடுக்கவும்:","add_funds":"💸 <b>வாலெட்டில் பணம் சேர்க்கவும்</b>","current_balance":"தற்போதைய இருப்பு","quick_amount":"கீழே ஒரு தொகையைத் தேர்ந்தெடுக்கவும் அல்லது தனிப்பயன் தொகையை உள்ளிடவும்.","minmax":"குறைந்தபட்சம்: ₹1.00 · அதிகபட்சம்: ₹50,000.00","custom_amount":"⌨️ தனிப்பயன் தொகை","enter_amount":"💰 <b>தொகையை உள்ளிடவும்</b>","confirm":"உறுதிசெய்","verify":"🟢 கட்டணத்தைச் சரிபார்க்கவும்","cancel_payment":"➡️ கட்டணத்தை ரத்து செய்","payment_cancelled":"❌ <b>கட்டணம் ரத்து செய்யப்பட்டது</b>","no_charge":"₹{amount} QR ரத்து செய்யப்பட்டது — கட்டணம் எதுவும் இல்லை.","try_again":"🛒 மீண்டும் முயற்சி","upi_qr":"💸 <b>UPI கட்டண QR</b>","scan_pay":"UPI மூலம் சரியாக <b>{amount}</b> செலுத்தவும்.","pay_after":"💳 பணம் செலுத்திய பின் 'கட்டணத்தைச் சரிபார்க்கவும்' என்பதை அழுத்தவும்.","expires":"💳 இந்த QR 5 நிமிடங்களில் காலாவதியாகும்.","generating":"⏳ <b>பாதுகாப்பான QR உருவாக்கப்படுகிறது...</b>","upi":"UPI PAY","binance":"BINANCE","gateway_offline":"⚠️ கட்டண கேட்வே தற்போது முடக்கப்பட்டுள்ளது.","back_to_plans":"➡️ திட்டங்களுக்கு திரும்பு","cancel":"➡️ ரத்து","deposit_order_not_found":"டெபாசிட் ஆர்டர் கிடைக்கவில்லை.","verification_active":"🔄 <b>சரிபார்ப்பு செயலில்</b>","send_utr":"உங்கள் 12 இலக்க UTR / UPI Ref No. ஐ இங்கே அனுப்பவும்.","send_cancel":"நிறுத்த /cancel அனுப்பவும்.","reseller_benefits":"📥 <b>ரீசெல்லர் நன்மைகள்:</b>","maintain_wallet":"🤑 <b>தேவை:</b> வாலெட்டில் ₹1,000.00 வைத்திருக்கவும் (இருப்பு கழிக்கப்படாது!)","your_balance":"உங்கள் இருப்பு","deficit":"தேவையான மீதம்","select_gateway":"மீதத்தைச் சேர்க்க கேட்வே தேர்ந்தெடுக்கவும்:","send_proof":"📨 ஆதரவுக்கு ஆதாரம் அனுப்பவும்","cancel_order":"➡️ ஆர்டரை ரத்து செய்"},
    "ur": {"language":"زبان","select_language":"🌐 <b>اپنی پسندیدہ زبان منتخب کریں:</b>","product_store":"🛒 شاپ / اسٹور پروڈکٹ","check_update":"🔄 اپ ڈیٹ چیک کریں","add_balance":"💸 بیلنس شامل کریں","profile":"👑 میری پروفائل + کی ہسٹری","referral":"🔗 ریفرل","howto":"❗ استعمال کرنے کا طریقہ","reseller":"👑 ری سیلر بنیں","feedback":"↗ پبلک فیڈ بیک دیکھیں","support":"📨 سپورٹ","lucky":"🎁 لکی","back":"➡️ واپس","back_menu":"➡️ مینو پر واپس","choose_product":"👑 پروڈکٹ منتخب کریں:","choose_plan":"🤩 پلان منتخب کریں:","add_funds":"💸 <b>والٹ میں رقم شامل کریں</b>","current_balance":"موجودہ بیلنس","quick_amount":"نیچے رقم منتخب کریں یا اپنی رقم درج کریں۔","minmax":"کم از کم: ₹1.00 · زیادہ سے زیادہ: ₹50,000.00","custom_amount":"⌨️ اپنی رقم","enter_amount":"💰 <b>رقم درج کریں</b>","confirm":"تصدیق","verify":"🟢 ادائیگی کی تصدیق کریں","cancel_payment":"➡️ ادائیگی منسوخ کریں","payment_cancelled":"❌ <b>ادائیگی منسوخ</b>","no_charge":"₹{amount} کا QR منسوخ کر دیا گیا — کوئی چارج نہیں ہوا۔","try_again":"🛒 دوبارہ کوشش کریں","upi_qr":"💸 <b>UPI ادائیگی QR</b>","scan_pay":"UPI سے بالکل <b>{amount}</b> ادا کریں۔","pay_after":"💳 ادائیگی کے بعد 'ادائیگی کی تصدیق' دبائیں۔","expires":"💳 یہ QR 5 منٹ میں ختم ہو جائے گا۔","generating":"⏳ <b>محفوظ QR بنایا جا رہا ہے...</b>","upi":"UPI PAY","binance":"BINANCE","gateway_offline":"⚠️ ادائیگی گیٹ وے فی الحال بند ہے۔","back_to_plans":"➡️ پلانز پر واپس","cancel":"➡️ منسوخ","deposit_order_not_found":"ڈپازٹ آرڈر نہیں ملا۔","verification_active":"🔄 <b>تصدیق فعال</b>","send_utr":"اپنا 12 ہندسوں کا UTR / UPI Ref No. یہاں بھیجیں۔","send_cancel":"روکنے کے لیے /cancel بھیجیں۔","reseller_benefits":"📥 <b>ری سیلر فوائد:</b>","maintain_wallet":"🤑 <b>ضرورت:</b> والٹ میں ₹1,000.00 رکھیں (بیلنس نہیں کٹے گا!)","your_balance":"آپ کا بیلنس","deficit":"ضروری باقی رقم","select_gateway":"باقی رقم شامل کرنے کے لیے گیٹ وے منتخب کریں:","send_proof":"📨 سپورٹ کو ثبوت بھیجیں","cancel_order":"➡️ آرڈر منسوخ کریں"},
    "gu": {"language":"ભાષા","select_language":"🌐 <b>તમારી પસંદગીની ભાષા પસંદ કરો:</b>","product_store":"🛒 શોપ / સ્ટોર પ્રોડક્ટ","check_update":"🔄 અપડેટ તપાસો","add_balance":"💸 બેલેન્સ ઉમેરો","profile":"👑 મારી પ્રોફાઇલ + કી હિસ્ટરી","referral":"🔗 રેફરલ","howto":"❗ કેવી રીતે ઉપયોગ કરવો","reseller":"👑 રીસેલર બનાવો","feedback":"↗ જાહેર પ્રતિસાદ જુઓ","support":"📨 સપોર્ટ","lucky":"🎁 લકી","back":"➡️ પાછા","back_menu":"➡️ મેનૂ પર પાછા","choose_product":"👑 પ્રોડક્ટ પસંદ કરો:","choose_plan":"🤩 પ્લાન પસંદ કરો:","add_funds":"💸 <b>વૉલેટમાં ફંડ ઉમેરો</b>","current_balance":"હાલનું બેલેન્સ","quick_amount":"નીચેની રકમ પસંદ કરો અથવા કસ્ટમ રકમ દાખલ કરો.","minmax":"ન્યૂનતમ: ₹1.00 · મહત્તમ: ₹50,000.00","custom_amount":"⌨️ કસ્ટમ રકમ","enter_amount":"💰 <b>રકમ દાખલ કરો</b>","confirm":"પુષ્ટિ કરો","verify":"🟢 પેમેન્ટ ચકાસો","cancel_payment":"➡️ પેમેન્ટ રદ કરો","payment_cancelled":"❌ <b>પેમેન્ટ રદ થયું</b>","no_charge":"₹{amount} નો QR રદ થયો — કોઈ ચાર્જ લાગ્યો નથી.","try_again":"🛒 ફરી પ્રયાસ કરો","upi_qr":"💸 <b>UPI પેમેન્ટ QR</b>","scan_pay":"UPI દ્વારા ચોક્કસ <b>{amount}</b> ચૂકવો.","pay_after":"💳 ચૂકવણી પછી 'પેમેન્ટ ચકાસો' દબાવો.","expires":"💳 આ QR 5 મિનિટમાં સમાપ્ત થશે.","generating":"⏳ <b>સુરક્ષિત QR બની રહ્યું છે...</b>","upi":"UPI PAY","binance":"BINANCE","gateway_offline":"⚠️ પેમેન્ટ ગેટવે હાલમાં બંધ છે.","back_to_plans":"➡️ પ્લાન પર પાછા","cancel":"➡️ રદ કરો","deposit_order_not_found":"ડિપોઝિટ ઓર્ડર મળ્યો નથી.","verification_active":"🔄 <b>ચકાસણી સક્રિય</b>","send_utr":"તમારો 12 અંકનો UTR / UPI Ref No. અહીં મોકલો.","send_cancel":"બંધ કરવા /cancel મોકલો.","reseller_benefits":"📥 <b>રીસેલર લાભ:</b>","maintain_wallet":"🤑 <b>જરૂર:</b> વૉલેટમાં ₹1,000.00 રાખો (બેલેન્સ કપાશે નહીં!)","your_balance":"તમારું બેલેન્સ","deficit":"જરૂરી બાકી","select_gateway":"બાકી ઉમેરવા ગેટવે પસંદ કરો:","send_proof":"📨 સપોર્ટને પુરાવો મોકલો","cancel_order":"➡️ ઓર્ડર રદ કરો"},
}
# Fill less-common languages with the same complete key set; labels are native and
# payment terminology remains familiar where a shorter translation is safer.
I18N["as"] = dict(I18N["bn"], language="ভাষা", select_language="🌐 <b>আপোনাৰ পছন্দৰ ভাষা বাছনি কৰক:</b>")
I18N["bho"] = dict(I18N["hi"], language="भाषा", select_language="🌐 <b>अपन मनपसंद भाषा चुनीं:</b>")
I18N["pa"] = dict(I18N["hi"], language="ਭਾਸ਼ਾ", select_language="🌐 <b>ਆਪਣੀ ਪਸੰਦ ਦੀ ਭਾਸ਼ਾ ਚੁਣੋ:</b>")
I18N["mr"] = dict(I18N["hi"], language="भाषा", select_language="🌐 <b>आपली पसंतीची भाषा निवडा:</b>")
I18N["or"] = dict(I18N["hi"], language="ଭାଷା", select_language="🌐 <b>ଆପଣଙ୍କ ପସନ୍ଦର ଭାଷା ବାଛନ୍ତୁ:</b>")

def get_user_lang(user_id: int) -> str:
    try:
        row = db_query("SELECT language FROM users WHERE user_id=?", (user_id,), fetchone=True)
        return row[0] if row and row[0] in I18N else "en"
    except Exception:
        return "en"

def t(user_id: int, key: str, **kwargs) -> str:
    lang = get_user_lang(user_id)
    text = I18N.get(lang, I18N["en"]).get(key, I18N["en"].get(key, key))
    try:
        return text.format(**kwargs)
    except Exception:
        return text

# ==============================================================================
# 3. STRING RESOURCES – using placeholders for premium emojis
# ==============================================================================
UI_TEXTS = {
    "start_menu": (
        "✨ <b>𝐃𝐀𝐑𝐊 𝐆𝐇𝐎𝐒𝐓 𝐏𝐀𝐈𝐃 𝐒𝐓𝐎𝐑𝐄</b>\n\n"
        "{product_store} 𝗣𝗥𝗢𝗗𝗨𝗖𝗧 𝗦𝘁𝗼𝗿𝗲 : 𝗮𝗹𝗹 𝗸𝗲𝘆𝘀 𝗣𝘂𝗿𝗰𝗵𝗮𝘀𝗲  & 𝗶𝗻𝘀𝘁𝗮𝗻𝘁𝗹𝘆 𝗱𝗲𝗹𝗶𝘃𝗲𝗿𝘆\n"
        "{profile} 𝗠𝘆 𝗽𝗿𝗼𝗳𝗶𝗹𝗲 : 𝗰𝗵𝗲𝗰𝗸 𝘆𝗼𝘂𝗿 𝗮𝗰𝗰𝗼𝘂𝗻𝘁 𝗶𝗻𝗳𝗼𝗿𝗺𝗮𝘁𝗶𝗼𝗻\n"
        "{add_balance} 𝗔𝗱𝗱 𝗯𝗮𝗹𝗮𝗻𝗰𝗲 : 𝗱𝗲𝗽𝗼𝘀𝗶𝘁𝗲 𝗯𝗮𝗹𝗮𝗻𝗰𝗲 & 𝘀𝗲𝗰𝘂𝗿𝗲 𝘀𝗲𝗿𝘃𝗶𝗰𝗲\n"
        "{history} 𝗔𝗹𝗹 𝗵𝗶𝘀𝘁𝗼𝗿𝘆 : 𝗰𝗵𝗲𝗰𝗸 𝗮𝗹𝗹 𝗽𝘂𝗿𝗰𝗵𝗮𝘀𝗲 𝗵𝗶𝘀𝘁𝗼𝗿𝘆\n"
        "{tutorial} 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹 : 𝘃𝗶𝗲𝘄 𝘁𝘂𝘁𝗼𝗿𝗶𝗮𝗹 & 𝘄𝗼𝗿𝗸 𝘁𝗵𝗶𝘀 𝗯𝗼𝘁\n"
        "{support} 𝗦𝘂𝗽𝗽𝗼𝗿𝘁 : 𝗯𝗼𝘁 𝗽𝗿𝗼𝗯𝗹𝗲𝗺 𝘀𝗼𝗹𝘃𝗲𝗱 𝗳𝗼𝗿 𝘀𝘂𝗽𝗽𝗼𝗿𝘁 𝗮𝗱𝗺𝗶𝗻\n"
    ),
    "vip_menu": (
        "🌟 <b><u>VIP MEMBERSHIP CLUB</u></b> 🌟\n\n"
        "Unlock premium benefits and permanent discounts!\n\n"
        "💎 <b>VIP Benefits:</b>\n"
        "• Flat 15% off on ALL products (Stacks with Reseller!)\n"
        "• Priority Support\n"
        "• Exclusive VIP-only giveaways\n\n"
        "💳 <b>VIP Price:</b> ₹299.00 (Lifetime)\n"
        "👤 <b>Your Status:</b> {vip_status}"
    ),
    "add_balance_menu": (
        "{add_balance} <b>ADD BALANCE</b> {info_icon}\n\n"
        "{info_icon} Select your preferred payment method. {check_icon}\n\n"
        "┣ {upi} UPI — Fast Indian payments {checkbox_icon}\n"
        ""
        "{shield_icon} Payments are verified securely. {check_icon}"
    )
}

def get_ui_text(key: str, **kwargs) -> str:
    val = db_query("SELECT value FROM settings WHERE key=?", (f"ui_{key}",), fetchone=True)
    template = val[0] if val and val[0] else UI_TEXTS.get(key, "")

    emoji_map = {
        '{product_store}': get_emoji('product_store'),
        '{profile}': get_emoji('profile'),
        '{add_balance}': get_emoji('add_balance'),
        '{history}': get_emoji('history'),
        '{tutorial}': get_emoji('tutorial'),
        '{support}': get_emoji('support'),
        '{telegram}': get_emoji('telegram'),
        '{whatsapp}': get_emoji('whatsapp'),
        '{upi}': get_emoji('upi'),
        '{binance}': get_emoji('binance'),
        '{info_icon}': get_emoji('info_icon'),
        '{check_icon}': get_emoji('check_icon'),
        '{checkbox_icon}': get_emoji('checkbox_icon'),
        '{shield_icon}': get_emoji('shield_icon'),
        '{money_icon}': get_emoji('money_icon'),
        '{redeem_icon}': get_emoji('redeem_icon'),
        '{wallet_left}': get_emoji('wallet_left'),
        '{wallet_right}': get_emoji('wallet_right'),
        '{point_down}': get_emoji('point_down'),
    }
    for placeholder, emoji_tag in emoji_map.items():
        template = template.replace(placeholder, emoji_tag)

    if kwargs:
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing formatting key for template {key}: {e}")
    return template

# ==============================================================================
# 4. DATABASE INITIALISATION & MIGRATION
# ==============================================================================
def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            phone TEXT, 
            first_name TEXT, 
            username TEXT,
            balance REAL DEFAULT 0.0, 
            account_type TEXT DEFAULT 'Regular', 
            orders_count INTEGER DEFAULT 0, 
            spent REAL DEFAULT 0.0, 
            last_spin TEXT, 
            joined_date TEXT,
            is_reseller INTEGER DEFAULT 0,
            is_pro_reseller INTEGER DEFAULT 0,
            reseller_since TEXT,
            total_saved REAL DEFAULT 0.0,
            is_banned INTEGER DEFAULT 0,
            warnings INTEGER DEFAULT 0,
            is_vip INTEGER DEFAULT 0,
            vip_since TEXT,
            referred_by INTEGER DEFAULT NULL,
            team_earnings REAL DEFAULT 0.0
        )
    ''')
    
    # Existing databases are upgraded safely without losing users or balances.
    try:
        c.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'en'")
    except sqlite3.OperationalError:
        pass
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            category TEXT, 
            panel_name TEXT DEFAULT '',
            name TEXT, 
            price_inr REAL, 
            reseller_price REAL DEFAULT 0.0,
            pro_reseller_price_usd REAL DEFAULT 0.0,
            stock INTEGER, 
            apk_link TEXT, 
            validity TEXT DEFAULT 'Lifetime', 
            device_limit TEXT DEFAULT '1 Device',
            is_active INTEGER DEFAULT 1,
            is_maintenance INTEGER DEFAULT 0,
            api_enabled INTEGER DEFAULT 0,
            api_product_id TEXT DEFAULT '',
            api_duration TEXT DEFAULT '',
            api_version TEXT DEFAULT 'V2',
            demo_video TEXT DEFAULT 'None'
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS product_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            product_id INTEGER, 
            key_text TEXT, 
            is_used INTEGER DEFAULT 0
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS product_maintenance_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT,
            UNIQUE(product_id, user_id)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            user_id INTEGER, 
            product_name TEXT, 
            price_paid REAL, 
            delivered_key TEXT, 
            purchase_date TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            user_id INTEGER, 
            message TEXT, 
            status TEXT DEFAULT 'Open',
            created_at TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, 
            value TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS coupons (
            code TEXT PRIMARY KEY, 
            amount REAL, 
            uses_left INTEGER
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS coupon_redemptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            amount REAL NOT NULL,
            redeemed_at TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS redeemed (
            user_id INTEGER, 
            code TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            order_id TEXT PRIMARY KEY, 
            user_id INTEGER, 
            amount_inr REAL, 
            status TEXT, 
            timestamp INTEGER,
            qr_url TEXT,
            upi_id TEXT,
            expires_at INTEGER,
            purpose TEXT DEFAULT 'wallet_deposit',
            product_id INTEGER
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS crypto_txns (
            txid TEXT PRIMARY KEY, 
            user_id INTEGER, 
            amount_usdt REAL, 
            timestamp INTEGER
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS spin_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            amount REAL
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            details TEXT,
            timestamp TEXT
        )
    ''')

    c.execute("""
        CREATE TABLE IF NOT EXISTS bot_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_user_id INTEGER NOT NULL,
            bot_username TEXT,
            bot_token_hash TEXT UNIQUE,
            bot_admin_id INTEGER NOT NULL,
            price_paid REAL NOT NULL,
            db_path TEXT NOT NULL,
            pid INTEGER,
            status TEXT DEFAULT 'running',
            created_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS bot_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            duration_days INTEGER NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            reseller_url TEXT DEFAULT '',
            reseller_username TEXT DEFAULT '',
            reseller_password TEXT DEFAULT '',
            admin_panel_website_link TEXT DEFAULT '',
            admin_username TEXT DEFAULT '',
            admin_password TEXT DEFAULT '',
            is_maintenance INTEGER DEFAULT 0,
            setup_video TEXT DEFAULT 'None'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS bot_plan_maintenance_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT,
            UNIQUE(plan_id, user_id)
        )
    """)

    migrations = [
        "ALTER TABLE users ADD COLUMN is_vip INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN is_pro_reseller INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN vip_since TEXT",
        "ALTER TABLE users ADD COLUMN referred_by INTEGER DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN team_earnings REAL DEFAULT 0.0",
        "ALTER TABLE products ADD COLUMN is_active INTEGER DEFAULT 1",
        "ALTER TABLE products ADD COLUMN is_maintenance INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN pro_reseller_price_usd REAL DEFAULT 0.0",
        "ALTER TABLE products ADD COLUMN api_enabled INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN api_product_id TEXT DEFAULT ''",
        "ALTER TABLE products ADD COLUMN api_duration TEXT DEFAULT ''",
        "ALTER TABLE products ADD COLUMN api_version TEXT DEFAULT 'V2'",
        "ALTER TABLE products ADD COLUMN demo_video TEXT DEFAULT 'None'",
        "ALTER TABLE tickets ADD COLUMN created_at TEXT",
        "ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN warnings INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN panel_name TEXT DEFAULT ''",
        "ALTER TABLE transactions ADD COLUMN qr_url TEXT",
        "ALTER TABLE transactions ADD COLUMN upi_id TEXT",
        "ALTER TABLE transactions ADD COLUMN expires_at INTEGER",
        "ALTER TABLE transactions ADD COLUMN purpose TEXT DEFAULT 'wallet_deposit'",
        "ALTER TABLE transactions ADD COLUMN product_id INTEGER",
        "ALTER TABLE bot_sales ADD COLUMN duration_days INTEGER DEFAULT 30",
        "ALTER TABLE bot_sales ADD COLUMN expires_at INTEGER",
        "ALTER TABLE bot_sales ADD COLUMN demo_video TEXT",
        "ALTER TABLE bot_plans ADD COLUMN reseller_url TEXT DEFAULT ''",
        "ALTER TABLE bot_plans ADD COLUMN reseller_username TEXT DEFAULT ''",
        "ALTER TABLE bot_plans ADD COLUMN reseller_password TEXT DEFAULT ''",
        "ALTER TABLE bot_plans ADD COLUMN admin_panel_website_link TEXT DEFAULT ''",
        "ALTER TABLE bot_plans ADD COLUMN admin_username TEXT DEFAULT ''",
        "ALTER TABLE bot_plans ADD COLUMN admin_password TEXT DEFAULT ''",
        "ALTER TABLE bot_plans ADD COLUMN is_maintenance INTEGER DEFAULT 0",
        "ALTER TABLE bot_plans ADD COLUMN setup_video TEXT DEFAULT 'None'",
        "ALTER TABLE bot_sales ADD COLUMN reseller_url TEXT DEFAULT ''",
        "ALTER TABLE bot_sales ADD COLUMN reseller_username TEXT DEFAULT ''",
        "ALTER TABLE bot_sales ADD COLUMN reseller_password TEXT DEFAULT ''",
        "ALTER TABLE bot_sales ADD COLUMN admin_panel_website_link TEXT DEFAULT ''",
        "ALTER TABLE bot_sales ADD COLUMN admin_username TEXT DEFAULT ''",
        "ALTER TABLE bot_sales ADD COLUMN admin_password TEXT DEFAULT ''"
    ]
    for mig in migrations:
        try: c.execute(mig)
        except sqlite3.OperationalError: pass
    

    default_settings = [
        ('reseller_system_status', 'ON'),
        ('bot_status', 'ON'),
        ('how_to_video', 'None'),
        ('vip_status', 'OFF'),
        ('spin_cooldown_hours', str(SPIN_COOLDOWN_HOURS)),
        ('spin_min_reward', str(SPIN_MIN_REWARD)),
        ('spin_max_reward', str(SPIN_MAX_REWARD)),
        ('referral_commission_percent', str(DEFAULT_REFERRAL_COMMISSION)),
        ('reseller_setup_fee', '200.0'),
        ('reseller_min_balance', '500.0'),
        ('migration_done', '0'),
        ('pro_usd_inr_rate', '40.0'),
        ('support_telegram', '' if CLIENT_MODE else 'http://t.me/DGM100K'),
        ('support_whatsapp', '' if CLIENT_MODE else 'http://wa.me/918876847490 ✅'),
        ('ui_start_menu', UI_TEXTS['start_menu']),
        ('ui_vip_menu', UI_TEXTS['vip_menu']),
        ('ui_add_balance_menu', UI_TEXTS['add_balance_menu']),
        ('bot_buy_status', 'OFF'),
        ('bot_buy_price', '1000.0'),
        ('bot_buy_demo_video', 'None'),
        ('bot_sales_channel_id', ''),
    ]
    if not CLIENT_MODE:
        default_settings.extend([
            ('fampay_api_key', FAMPAY_API_KEY),
            ('fampay_upi_id', ''),
            ('binance_api', ''),
            ('binance_secret', ''),
            ('binance_address', ''),
            ('reseller_api_url', RESELLER_API_URL),
            ('reseller_api_key', RESELLER_API_KEY_DEFAULT),
            ('reseller_master_key', RESELLER_MASTER_KEY_DEFAULT),
        ])
    for slot, emoji_id in DEFAULT_EMOJIS.items():
        default_settings.append((f"emoji_{slot}", emoji_id))
    
    for key, val in default_settings:
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))

    conn.commit()
    conn.close()


    # Removed feature settings are intentionally ignored by the UI.
    # Their old database values may remain, but no button or handler exposes them.

def normalize_coupon_code(code: str) -> str:
    return ''.join((code or '').strip().upper().split())

def create_coupon_record(db_fn, code: str, amount: float, uses: int):
    code = normalize_coupon_code(code)
    amount = float(amount)
    uses = int(uses)
    if not code or len(code) < 1 or not code.isalnum():
        raise ValueError("Coupon code must contain letters/numbers only")
    if amount <= 0:
        raise ValueError("Coupon amount must be greater than zero")
    if uses <= 0:
        raise ValueError("Coupon uses must be greater than zero")
    if db_fn("SELECT code FROM coupons WHERE code=?", (code,), fetchone=True):
        raise ValueError("Coupon code already exists")
    db_fn("INSERT INTO coupons (code, amount, uses_left) VALUES (?, ?, ?)", (code, amount, uses))
    return code

def redeem_coupon_record(db_fn, user_id: int, code: str):
    code = normalize_coupon_code(code)
    row = db_fn("SELECT amount, uses_left FROM coupons WHERE code=?", (code,), fetchone=True)
    if not row or int(row[1]) <= 0:
        return {"ok": False, "reason": "exhausted" if row else "invalid"}
    if db_fn("SELECT id FROM coupon_redemptions WHERE user_id=? AND code=?", (user_id, code), fetchone=True):
        return {"ok": False, "reason": "already_redeemed"}
    amount = float(row[0])
    db_fn("UPDATE coupons SET uses_left=uses_left-1 WHERE code=? AND uses_left>0", (code,))
    db_fn("INSERT INTO coupon_redemptions (user_id, code, amount, redeemed_at) VALUES (?, ?, ?, ?)", (user_id, code, amount, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    db_fn("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, user_id))
    return {"ok": True, "amount": amount}

def migrate_categories() -> None:
    done = get_setting("migration_done", "0")
    
    # ALWAYS force update emojis and UI texts regardless of migration status
    logger.info("Forcing emoji and UI text updates...")
    
    # Remove legacy Ludo Spin / Download Files settings from existing databases
    db_query("DELETE FROM settings WHERE key IN ('emoji_ludo_spin', 'emoji_download', 'ui_download_files', 'ui_lucky_dice_result', 'all_files_link', 'emoji_referral')")

    # Update all emoji settings
    for slot, emoji_id in DEFAULT_EMOJIS.items():
        set_setting(f"emoji_{slot}", emoji_id)
    
    # Force update UI texts
    set_setting("ui_start_menu", UI_TEXTS['start_menu'])
    set_setting("ui_add_balance_menu", UI_TEXTS['add_balance_menu'])
    set_setting("ui_vip_menu", UI_TEXTS['vip_menu'])
    logger.info("UI texts and emojis updated with new placeholders and IDs.")
    
    # Fix any corrupted price columns (one-time cleanup)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    products = c.execute("SELECT id, price_inr, reseller_price FROM products").fetchall()
    for prod in products:
        pid = prod[0]
        for col in ['price_inr', 'reseller_price']:
            val = prod[1] if col == 'price_inr' else prod[2]
            if val is None or val == "":
                new_val = 0.0
            else:
                try:
                    new_val = float(val)
                except (ValueError, TypeError):
                    new_val = 0.0
            c.execute(f"UPDATE products SET {col}=? WHERE id=?", (new_val, pid))
    conn.commit()
    conn.close()
    logger.info("Fixed any non-numeric price columns.")
    
    if done == "1":
        return
    
    # Do not inject or rewrite fixed categories. Categories are controlled by the admin.
    set_setting("migration_done", "1")
    logger.info("Category migration complete: dynamic admin categories preserved.")

# ==============================================================================
# 5. MIDDLEWARES & SECURITY
# ==============================================================================
async def hacker_loading(message: Message, text: str = "Decrypting Data") -> Message:
    msg = await message.answer(f"⚡ {text}\n[□□□] 0%")
    await asyncio.sleep(0.3)
    await msg.edit_text(f"⚡ {text}\n[■□□] 33%", parse_mode='HTML')
    await asyncio.sleep(0.3)
    await msg.edit_text(f"⚡ {text}\n[■■□] 66%", parse_mode='HTML')
    await asyncio.sleep(0.3)
    await msg.edit_text(f"⚡ {text}\n[■■■] 100%", parse_mode='HTML')
    return msg

class GlobalSecurityMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()
        self.last_action_times = {}

    async def __call__(self, handler, event, data):
        user_id = event.from_user.id
        now = time.time()
        if user_id in self.last_action_times:
            if now - self.last_action_times[user_id] < 0.3:
                return
        self.last_action_times[user_id] = now

        if user_id != ADMIN_ID:
            user_info = db_query("SELECT is_banned FROM users WHERE user_id=?", (user_id,), fetchone=True)
            if user_info and user_info[0] == 1:
                msg = "🚫 <b>ACCESS DENIED</b>\nYou have been banned from using this bot.\nContact support if you think this is a mistake."
                if isinstance(event, Message): await event.answer(msg)
                elif isinstance(event, CallbackQuery): await event.answer(msg, show_alert=True)
                return
                
            status_check = db_query("SELECT value FROM settings WHERE key='bot_status'", fetchone=True)
            status = status_check[0] if status_check else 'ON'
            if status == 'OFF':
                msg = "⚠️ <b>Store Maintenance</b>\n\nThe store is currently offline for updates. Please check back later!"
                if isinstance(event, Message): await event.answer(msg)
                elif isinstance(event, CallbackQuery): await event.answer("⚠️ Bot is currently OFF for Maintenance.", show_alert=True)
                return
                
        return await handler(event, data)

dp.message.middleware(GlobalSecurityMiddleware())
dp.callback_query.middleware(GlobalSecurityMiddleware())

# ==============================================================================
# 6. FSM STATES
# ==============================================================================
class UserStates(StatesGroup):
    phone_verification = State()
    wait_for_ticket = State()
    wait_for_redeem = State()
    wait_for_crypto_txid = State()
    custom_amount_input = State()
    # Used by API V1 / Device-Bound product purchases.
    wait_for_android_id = State()
    bot_buy_token = State()
    bot_buy_admin_id = State()

class AdminStates(StatesGroup):
    add_prod_category = State()
    add_prod_custom_category = State()
    add_prod_panel_name = State()
    add_prod_name = State()
    add_prod_validity = State()
    add_prod_device_limit = State()
    add_prod_price = State()
    add_prod_reseller_price = State()
    add_prod_pro_reseller_price = State()
    add_prod_apk = State()
    add_prod_keys = State()
    add_prod_api_enabled = State()
    add_prod_api_pid = State()
    add_prod_api_duration = State()
    add_prod_api_version = State()
    add_prod_demo_video = State()
    
    edit_prod_field = State()
    wait_for_new_value = State()
    wait_for_add_keys = State()
    wait_for_delete_key = State()
    
    broadcast_msg = State()
    add_coupon_code = State()
    add_coupon_amount = State()
    add_coupon_uses = State()
    
    # FamPay states
    wait_for_fampay_api = State()
    wait_for_fampay_upi = State()
    
    # Binance states
    wait_for_binance_api = State()
    wait_for_binance_secret = State()
    wait_for_binance_address = State()
    
    ticket_reply_msg = State()
    reseller_manage_id = State()
    manage_target_user = State()
    wait_for_add_money = State()
    wait_for_minus_money = State()
    wait_for_warning = State()
    
    wait_for_howto_video = State()
    
    edit_ui_text = State()
    edit_reseller_price = State()
    edit_pro_reseller_price = State()
    wait_for_pro_usd_rate = State()
    wait_for_reseller_api_url = State()
    wait_for_reseller_api_key = State()
    wait_for_reseller_master_key = State()
    wait_for_reseller_setup_fee = State()
    wait_for_reseller_min_balance = State()
    confirm_ban = State()
    
    wait_for_support_telegram = State()
    wait_for_support_whatsapp = State()
    wait_for_category_emoji = State()
    wait_for_panel_emoji_id = State()
    wait_for_emoji_slot = State()
    bot_buy_price = State()
    bot_plan_name = State()
    bot_plan_price = State()
    bot_plan_days = State()
    bot_plan_admin_panel_website_link = State()
    bot_plan_setup_video = State()
    bot_demo_video = State()
    bot_admin_broadcast_msg = State()
    bot_sales_channel_id = State()

# ==============================================================================
# 7. KEYBOARDS
# ==============================================================================
def get_category_emoji(category: str) -> str:
    slot_map = {
        "ANDROID NON ROOT PANEL": "category_android_non_root",
        "ANDROID ROOT PANEL": "category_android_root",
        "PC PANEL": "category_pc",
    }
    slot = slot_map.get(category)
    if slot:
        return get_emoji_icon(slot, DEFAULT_EMOJIS.get(slot, ""))
    return ""

def get_panel_emoji(panel_name: str) -> str:
    stored = get_setting(f"panel_emoji_{panel_name}", "")
    if stored and stored.isdigit():
        return stored
    return get_emoji_icon("product_store")

def contact_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Verify Contact", request_contact=True)]], 
        resize_keyboard=True, 
        one_time_keyboard=True
    )

def main_menu_kb(user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    status_check = db_query("SELECT value FROM settings WHERE key='reseller_system_status'", fetchone=True)
    sys_status = status_check[0] if status_check else 'ON'
    vip_sys_check = db_query("SELECT value FROM settings WHERE key='vip_status'", fetchone=True)
    vip_system = vip_sys_check[0] if vip_sys_check else 'OFF'
    is_reseller = False
    is_pro_reseller = False
    if user_id:
        user_check = db_query("SELECT is_reseller, is_pro_reseller FROM users WHERE user_id=?", (user_id,), fetchone=True)
        if user_check:
            is_reseller = bool(user_check[0])
            is_pro_reseller = bool(user_check[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    uid = user_id or 0
    kb.inline_keyboard.append([InlineKeyboardButton(text=t(uid,"product_store"), callback_data="menu_shop", icon_custom_emoji_id=get_emoji_icon("product_store"), style="danger")])
    kb.inline_keyboard.append([
        InlineKeyboardButton(text=t(uid,"check_update"), callback_data="menu_how_to", icon_custom_emoji_id=get_emoji_icon("tutorial"), style="success"),
        InlineKeyboardButton(text=t(uid,"add_balance"), callback_data="menu_add_balance", icon_custom_emoji_id=get_emoji_icon("add_balance"), style="primary")])
    kb.inline_keyboard.append([InlineKeyboardButton(text=t(uid,"profile"), callback_data="menu_profile", icon_custom_emoji_id=get_emoji_icon("profile"), style="success")])
    if not CLIENT_MODE and get_setting("bot_buy_status", "OFF") == "ON":
        kb.inline_keyboard.append([InlineKeyboardButton(text="🤖 Bot Buy", callback_data="menu_bot_buy", style="success")])
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="👥 My Team", callback_data="menu_team", icon_custom_emoji_id=get_emoji_icon("reseller"), style="success"),
        InlineKeyboardButton(text=t(uid,"referral"), callback_data="menu_referral", icon_custom_emoji_id=get_emoji_icon("reseller"), style="success")])
    kb.inline_keyboard.append([
        InlineKeyboardButton(text=t(uid,"howto"), callback_data="menu_how_to", icon_custom_emoji_id=get_emoji_icon("tutorial"), style="primary")])
    if sys_status == 'ON' or is_reseller:
        kb.inline_keyboard.append([InlineKeyboardButton(text=("💎 Pro Reseller Dashboard" if is_pro_reseller else t(uid,"reseller")), callback_data="menu_reseller_dash", icon_custom_emoji_id=get_emoji_icon("reseller"), style="success")])
    if vip_system == 'ON':
        kb.inline_keyboard.append([InlineKeyboardButton(text="VIP Club", callback_data="menu_vip_dash", style="danger")])
    kb.inline_keyboard.append([InlineKeyboardButton(text=t(uid,"feedback"), callback_data="menu_feedback", style="success")])
    kb.inline_keyboard.append([
        InlineKeyboardButton(text=t(uid,"support"), callback_data="menu_support", icon_custom_emoji_id=get_emoji_icon("support"), style="danger"),
        InlineKeyboardButton(text=t(uid,"lucky"), callback_data="menu_lucky", style="success")])
    kb.inline_keyboard.append([InlineKeyboardButton(text=t(uid,"language"), callback_data="menu_language", style="primary")])
    return kb

def back_kb(callback: str = "back_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="BACK", callback_data=callback,
                icon_custom_emoji_id=get_emoji_icon("back"),
                style="danger"
            )
        ]]
    )

def admin_kb() -> InlineKeyboardMarkup:
    status = db_query("SELECT value FROM settings WHERE key='bot_status'", fetchone=True)
    status_val = status[0] if status else 'ON'
    vip_status = db_query("SELECT value FROM settings WHERE key='vip_status'", fetchone=True)
    vip_val = vip_status[0] if vip_status else 'OFF'

    rows = [
        [InlineKeyboardButton(text="📊 Bot Statistics", callback_data="admin_view_stats", style="primary")],
        [InlineKeyboardButton(text="👥 User Control Panel", callback_data="admin_user_control_start", style="primary")],
        [
            InlineKeyboardButton(text="➕ Add Product", callback_data="admin_add_prod", style="primary"),
            InlineKeyboardButton(text="📦 Manage Products", callback_data="admin_manage_prods", style="primary")
        ],
        [InlineKeyboardButton(text="👑 Reseller Mgmt", callback_data="admin_reseller_menu", style="primary")],
        [
            InlineKeyboardButton(text="🎟 Create Coupon", callback_data="admin_create_coupon", style="primary"),
            InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast_btn", style="primary")
        ],
        [
            InlineKeyboardButton(text="🎫 View Tickets", callback_data="admin_view_tickets", style="primary"),
            InlineKeyboardButton(text="📹 Tutorial Video", callback_data="admin_set_video", style="primary")
        ],
        [InlineKeyboardButton(text="🎨 Edit All Emojis", callback_data="admin_edit_emojis", style="primary")],
    ]
    # Owner-only controls: purchased/client-bot admins must never see or access
    # the seller's Managed Bots dashboard or Bot Sales Proof Channel settings.
    if not CLIENT_MODE:
        rows.extend([
            [InlineKeyboardButton(text="🤖 Managed Bots", callback_data="admin_managed_bots", style="success")],
            [InlineKeyboardButton(text="📣 Bot Sales Proof Channel", callback_data="admin_set_bot_sales_channel", style="success")],
        ])
    if not CLIENT_MODE:
        rows.append([
            InlineKeyboardButton(text="⚙️ FamPay Setup", callback_data="admin_setup_fampay", style="primary"),
            InlineKeyboardButton(text="🔐 Reseller API", callback_data="admin_setup_reseller_api", style="primary")
        ])
    rows.extend([
        [
            InlineKeyboardButton(text="✏️ Edit UI Texts", callback_data="admin_edit_ui_menu", style="primary"),
            InlineKeyboardButton(text="📝 Edit Reseller Price", callback_data="admin_edit_reseller_price", style="primary"),
            InlineKeyboardButton(text="💵 Pro Pricing", callback_data="admin_pro_pricing", style="primary")
        ],
        [
            InlineKeyboardButton(text="💰 Reseller Fee", callback_data="admin_set_reseller_fee", style="primary"),
            InlineKeyboardButton(text="💳 Min Balance", callback_data="admin_set_reseller_min", style="primary")
        ],
        [
            InlineKeyboardButton(text="📞 Set Support Links", callback_data="admin_set_support_links", style="primary"),
            InlineKeyboardButton(text="🎨 Set Category Emojis", callback_data="admin_set_category_emojis", style="primary")
        ],
        [InlineKeyboardButton(text="🖼 Set Panel Emojis", callback_data="admin_set_panel_emojis", style="primary")],
    ])
    if not CLIENT_MODE:
        rows.extend([
            [InlineKeyboardButton(text=f"🤖 Bot Buy: {get_setting('bot_buy_status','OFF')} {'🟢' if get_setting('bot_buy_status','OFF') == 'ON' else '🔴'}", callback_data="admin_toggle_bot_buy", style="success" if get_setting('bot_buy_status','OFF') == 'ON' else "danger")],
            [InlineKeyboardButton(text="📦 Bot Buy Plans", callback_data="admin_bot_plans", style="primary"), InlineKeyboardButton(text="🎥 Bot Setup Demo", callback_data="admin_set_bot_demo", style="primary")],
        ])
    rows.extend([
        [InlineKeyboardButton(text=f"Bot Status: {status_val} {'🟢' if status_val == 'ON' else '🔴'}", callback_data="admin_toggle_bot", style="success" if status_val == 'ON' else "danger")],
        [InlineKeyboardButton(text=f"VIP System: {vip_val} {'🟢' if vip_val == 'ON' else '🔴'}", callback_data="admin_toggle_vip_sys", style="success" if vip_val == 'ON' else "danger")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="Back to Admin", callback_data="admin_panel_back",
            icon_custom_emoji_id=get_emoji_icon("back"),
            style="danger"
        )
    ]])

# ==============================================================================
# 8. NOTIFICATIONS
# ==============================================================================
async def send_advanced_notification(user_id: int, notif_type: str, amount: float, product: str = None, key: str = None, gateway: str = "FamPay") -> None:
    user_info = db_query("SELECT first_name, phone, username, is_reseller, is_vip FROM users WHERE user_id=?", (user_id,), fetchone=True)
    
    name = user_info[0] if user_info else "Unknown"
    phone = user_info[1] if user_info and user_info[1] else "Not Provided"
    username = f"@{user_info[2]}" if user_info and user_info[2] else "None"
    
    tags = []
    if user_info and user_info[3]: tags.append("👑 Reseller")
    if user_info and user_info[4]: tags.append("🌟 VIP")
    tag_str = " | ".join(tags) if tags else "👤 Regular"
        
    time_now = datetime.now().strftime("%d-%m-%Y %I:%M %p")
    
    if notif_type == "ORDER":
        title = "🛒 <b>NEW ORDER PROCESSED!</b> 🛒"
        details = (f"📦 <b>Product:</b> {product}\n🔑 <b>Key:</b> <code>{key}</code>\n💰 <b>Amount Paid:</b> ₹{amount:.2f}\n📅 <b>Time:</b> {time_now}")
    else:
        title = "💰 <b>NEW WALLET DEPOSIT!</b> 💰"
        details = (f"💵 <b>Amount Added:</b> ₹{amount:.2f}\n🧾 <b>Gateway:</b> {gateway}\n🆔 <b>Reference:</b> <code>{product}</code>\n📅 <b>Time:</b> {time_now}")

    msg = f"{title}\n━━━━━━━━━━━━━━━━━━\n👤 <b>Name:</b> {name}\n🆔 <b>User ID:</b> <code>{user_id}</code>\n📱 <b>Phone:</b> {phone}\n🔗 <b>Username:</b> {username}\n🏷 <b>Status:</b> {tag_str}\n━━━━━━━━━━━━━━━━━━\n{details}"
    try: 
        await bot.send_message(ADMIN_ID, msg, parse_mode='HTML')
    except Exception as e: 
        logger.error(f"Failed to send admin notification: {e}")

# ==============================================================================
# 9. FAMPAY PAYMENT FUNCTIONS
# ==============================================================================

async def generate_fampay_qr(user_id: int, amount: float, upi_id: str = None) -> Dict[str, Any]:
    """Generate FamPay QR code for payment."""
    if CLIENT_MODE:
        return {"status": "error", "message": "FamPay is disabled in standalone bot mode."}
    api_key = get_setting("fampay_api_key", FAMPAY_API_KEY)
    if not api_key or api_key == "YOUR_FAMPAY_API_KEY":
        return {"status": "error", "message": "FamPay API key not configured"}
    
    # Use provided UPI ID or default
    if not upi_id:
        upi_id = get_setting("fampay_upi_id", "")
        if not upi_id:
            return {"status": "error", "message": "UPI ID not configured"}
    
    url = f"{FAMPAY_QR_URL}?upi={upi_id}&amount={amount}"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    try:
                        result = await resp.json(content_type=None)
                        return result
                    except Exception as e:
                        logger.error(f"Error parsing FamPay response: {e}")
                        return {"status": "error", "message": "Failed to parse response"}
                else:
                    return {"status": "error", "message": f"HTTP Error: {resp.status}"}
        except Exception as e:
            logger.error(f"FamPay API Error: {e}")
            return {"status": "error", "message": str(e)}

async def verify_fampay_payment(order_id: str) -> Dict[str, Any]:
    """Verify payment status with FamPay."""
    if CLIENT_MODE:
        return {"status": "error", "message": "FamPay is disabled in standalone bot mode."}
    api_key = get_setting("fampay_api_key", FAMPAY_API_KEY)
    if not api_key or api_key == "YOUR_FAMPAY_API_KEY":
        return {"status": "error", "message": "FamPay API key not configured"}
    
    url = f"{FAMPAY_VERIFY_URL}?order_id={order_id}&api_key={api_key}"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    try:
                        result = await resp.json(content_type=None)
                        return result
                    except Exception as e:
                        logger.error(f"Error parsing FamPay verify response: {e}")
                        return {"status": "error", "message": "Failed to parse response"}
                else:
                    return {"status": "error", "message": f"HTTP Error: {resp.status}"}
        except Exception as e:
            logger.error(f"FamPay Verify API Error: {e}")
            return {"status": "error", "message": str(e)}

async def complete_product_purchase(user_id: int, prod_id: int) -> Tuple[bool, str]:
    """Fulfill a selected product after an exact top-up. Returns (success, message)."""
    prod = db_query(
        "SELECT name, price_inr, stock, apk_link, validity, device_limit, category, reseller_price, panel_name, api_enabled, api_product_id, api_duration, api_version, pro_reseller_price_usd FROM products WHERE id=? AND is_active=1",
        (prod_id,), fetchone=True
    )
    user = db_query("SELECT balance, is_reseller, total_saved, is_vip, is_pro_reseller FROM users WHERE user_id=?", (user_id,), fetchone=True)
    if not prod or not user:
        return False, "Product or user not found."
    normal_price=safe_float(prod[1]); reseller_price=safe_float(prod[7]); pro_usd=safe_float(prod[13])
    tier="Pro Reseller" if bool(user[4]) else ("Reseller" if bool(user[1]) else "Regular")
    final_price, final_usd, rate=get_product_price(normal_price,reseller_price,pro_usd,tier,bool(user[3]))
    if safe_float(user[0]) < final_price:
        return False, f"Insufficient balance. Need {fmt_curr(final_price-safe_float(user[0]))} more."
    # V1 products require an Android ID and cannot be silently completed from a payment callback.
    if bool(prod[9]) and (prod[12] or "V2").upper().strip() == "V1":
        return False, "This device-bound product requires Android ID. Please open the product again after the wallet is credited."
    delivered_key=""
    key_id=None
    if bool(prod[9]):
        result=await buy_from_reseller_api(str(prod[10]),str(prod[11]))
        if not api_purchase_success(result):
            return False, result.get("message","Reseller API purchase failed.")
        delivered_key=extract_api_key(result)
        if not delivered_key:
            return False, "API confirmed the purchase but did not return a license key."
    else:
        if prod[2] <= 0:
            return False, "This product is out of stock."
        key_data=db_query("SELECT id,key_text FROM product_keys WHERE product_id=? AND is_used=0 LIMIT 1",(prod_id,),fetchone=True)
        if not key_data:
            return False, "This product is out of stock."
        key_id=key_data[0]; delivered_key=key_data[1]
    savings=normal_price-final_price
    db_query("UPDATE users SET balance=?, spent=spent+?, orders_count=orders_count+1, total_saved=total_saved+? WHERE user_id=?",(safe_float(user[0])-final_price,final_price,savings,user_id))
    if key_id is not None:
        db_query("UPDATE product_keys SET is_used=1 WHERE id=?",(key_id,))
        db_query("UPDATE products SET stock=stock-1 WHERE id=?",(prod_id,))
    product_full_name=f"{prod[6]} - {prod[8]} ({prod[0]})"
    db_query("INSERT INTO orders (user_id,product_name,price_paid,delivered_key,purchase_date) VALUES (?,?,?,?,?)",(user_id,product_full_name,final_price,delivered_key,datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    ref_row = db_query("SELECT referred_by FROM users WHERE user_id=?", (user_id,), fetchone=True)
    if ref_row and ref_row[0]:
        commission_pct = safe_float(get_setting("referral_commission_percent", str(DEFAULT_REFERRAL_COMMISSION)), DEFAULT_REFERRAL_COMMISSION)
        commission = round(final_price * commission_pct / 100.0, 2)
        if commission > 0:
            db_query("UPDATE users SET balance=balance+?, team_earnings=team_earnings+? WHERE user_id=?", (commission, commission, ref_row[0]))
            log_activity(ref_row[0], "TEAM_COMMISSION", f"From user {user_id}: {commission}")
    log_activity(user_id,"PURCHASE_SUCCESS",f"Product: {product_full_name}, Paid: {final_price}, API: {bool(prod[9])}, AutoAfterTopup: True")
    await send_advanced_notification(user_id,"ORDER",final_price,product=product_full_name,key=delivered_key,gateway="Reseller API" if prod[9] else "Local Key Vault")
    msg=(f"🎉 <b>PURCHASE SUCCESSFUL</b>\n━━━━━━━━━━━━━━━━━━\n📦 <b>Panel:</b> {prod[6]}\n📁 <b>Panel Name:</b> {prod[8]}\n⏱ <b>Package:</b> {prod[0]}\n💰 <b>Amount Deducted:</b> {fmt_curr(final_price)}\n📱 <b>Device Limit:</b> {prod[5]}\n━━━━━━━━━━━━━━━━━━\n🔑 <b>Your Exclusive Key:</b>\n<code>{delivered_key}</code>")
    if prod[3] and prod[3].startswith("http"):
        msg += f"\n\n📥 <b>APK Link:</b> <a href='{prod[3]}'>Click Here to Download</a>"
    return True,msg

async def run_payment_verification(user_id: int, order_id: str, reply_target: Any) -> None:
    """Run payment verification with FamPay."""
    txn = db_query("SELECT amount_inr, status, timestamp, qr_url, upi_id, expires_at, purpose, product_id FROM transactions WHERE order_id=?", (order_id,), fetchone=True)
    if not txn:
        err = "❌ Invalid or Fake Order ID detected in system!"
        if isinstance(reply_target, CallbackQuery): await reply_target.answer(err, show_alert=True)
        else: await reply_target.answer(err)
        return
    
    # Check if QR expired
    if txn[5] and time.time() > txn[5]:
        db_query("UPDATE transactions SET status='expired' WHERE order_id=?", (order_id,))
        err_msg = "⏳ <b>QR Code Expired!</b>\nThe 5-minute payment window has expired. Please generate a new QR."
        if isinstance(reply_target, CallbackQuery): await reply_target.message.edit_text(err_msg, reply_markup=back_kb(), parse_mode='HTML')
        else: await reply_target.answer(err_msg, reply_markup=back_kb())
        return
        
    if txn[1] == 'paid':
        msg = "✅ This payment has already been securely credited to your wallet."
        if isinstance(reply_target, CallbackQuery): await reply_target.answer(msg, show_alert=True)
        else: await reply_target.answer(msg)
        return
    elif txn[1] == 'expired':
        msg = "❌ This order has expired. Please create a new deposit request."
        if isinstance(reply_target, CallbackQuery): await reply_target.answer(msg, show_alert=True)
        else: await reply_target.answer(msg)
        return
    
    # Verify with FamPay API
    result = await verify_fampay_payment(order_id)
    
    if result.get("status") == "success":
        # Payment successful
        txn_data = result.get("data", {})
        transaction_id = txn_data.get("transaction_id")
        utr = txn_data.get("utr")
        sender_name = txn_data.get("sender_name")
        amount_received = txn_data.get("amount", txn[0])
        payment_time = txn_data.get("payment_time_ist")
        
        db_query("UPDATE transactions SET status='paid' WHERE order_id=? AND status='pending'", (order_id,))
        db_query("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount_received, user_id))
        credit_referral_commission(user_id, amount_received, f"deposit:{order_id}")
        success_msg = f"🎉 <b>PAYMENT VERIFIED!</b>\n\n✅ {fmt_curr(amount_received)} has been added to your wallet.\n🧾 UTR: <code>{utr}</code>\n👤 Sender: {sender_name}\n📅 Time: {payment_time}"
        if txn[6] == 'product_topup' and txn[7]:
            ok, purchase_msg = await complete_product_purchase(user_id, int(txn[7]))
            if ok:
                success_msg += f"\n\n{purchase_msg}"
            else:
                success_msg += f"\n\n⚠️ <b>Top-up complete.</b> {purchase_msg}\n\nYour balance remains available in the wallet."
        if isinstance(reply_target, CallbackQuery): await reply_target.message.edit_text(success_msg, reply_markup=back_kb(), parse_mode='HTML')
        else: await reply_target.answer(success_msg, reply_markup=back_kb())
        await send_advanced_notification(user_id, "DEPOSIT", amount_received, product=transaction_id, gateway="FamPay")
        log_activity(user_id, "DEPOSIT_SUCCESS", f"Amount: {amount_received}, Gateway: FamPay, Order: {order_id}, UTR: {utr}, Purpose: {txn[6]}, Product: {txn[7]}")
        
    elif result.get("status") == "error":
        # Check if transaction failed specifically
        error_msg = result.get("message", "Payment not received yet")
        if "Transaction failed" in error_msg or "not received" in error_msg:
            fail_msg = f"❌ {error_msg}\n\n<i>Please make sure you sent the exact amount to the correct UPI ID.</i>"
            if isinstance(reply_target, CallbackQuery): await reply_target.answer(fail_msg, show_alert=True)
            else: await reply_target.answer(fail_msg)
        else:
            # Still pending - show QR again with status
            pending_msg = f"⏳ <b>Payment Status: PENDING</b>\n\n{error_msg}\n\n<i>Please wait a moment and verify again.</i>"
            if isinstance(reply_target, CallbackQuery): await reply_target.answer(pending_msg, show_alert=True)
            else: await reply_target.answer(pending_msg)
    else:
        err = f"⚠️ Gateway Error: {result.get('message', 'Unknown Error')}"
        if isinstance(reply_target, CallbackQuery): await reply_target.answer(err, show_alert=True)
        else: await reply_target.answer(err)

async def auto_verify_task() -> None:
    """Auto-verify pending FamPay transactions every 30 seconds."""
    if CLIENT_MODE: return
    while True:
        await asyncio.sleep(30)  # Check every 30 seconds
        
        api_key = get_setting("fampay_api_key", "")
        if not api_key or api_key == "YOUR_FAMPAY_API_KEY":
            continue
            
        pending_txns = db_query("SELECT order_id, user_id, amount_inr, timestamp, expires_at, purpose, product_id FROM transactions WHERE status='pending'", fetchall=True)
        if not pending_txns: continue

        for txn in pending_txns:
            order_id, user_id, amount, ts, expires_at, purpose, product_id = txn
            
            # Check if expired
            if expires_at and time.time() > expires_at:
                db_query("UPDATE transactions SET status='expired' WHERE order_id=?", (order_id,))
                try: 
                    await bot.send_message(user_id, f"⏳ <b>QR Code Expired!</b>\nYour payment window for order <code>{order_id}</code> has timed out. Please generate a new QR code.", parse_mode='HTML')
                except: pass
                continue
            
            # Verify with FamPay
            result = await verify_fampay_payment(order_id)
            
            if result.get("status") == "success":
                txn_data = result.get("data", {})
                amount_received = txn_data.get("amount", amount)
                utr = txn_data.get("utr")
                sender_name = txn_data.get("sender_name")
                payment_time = txn_data.get("payment_time_ist")
                
                db_query("UPDATE transactions SET status='paid' WHERE order_id=? AND status='pending'", (order_id,))
                db_query("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount_received, user_id))
                credit_referral_commission(user_id, amount_received, f"deposit:{order_id}")
                auto_msg=f"✨ <b>AUTO-VERIFIED!</b>\n\n✅ Your payment of {fmt_curr(amount_received)} was detected successfully!\n🧾 UTR: <code>{utr}</code>\n👤 Sender: {sender_name}"
                if purpose == 'product_topup' and product_id:
                    ok,purchase_msg=await complete_product_purchase(user_id,int(product_id))
                    if ok:
                        auto_msg += f"\n\n{purchase_msg}"
                    else:
                        auto_msg += f"\n\n⚠️ <b>Top-up complete.</b> {purchase_msg}\nYour wallet balance is available for retry."
                try:
                    await bot.send_message(user_id, auto_msg, parse_mode='HTML', reply_markup=back_kb())
                except: pass
                await send_advanced_notification(user_id, "DEPOSIT", amount_received, product=order_id, gateway="FamPay Auto")
                log_activity(user_id, "DEPOSIT_AUTO_SUCCESS", f"Amount: {amount_received}, Gateway: FamPay Auto, Order: {order_id}, UTR: {utr}, Purpose: {purpose}, Product: {product_id}")

# ==============================================================================
# 10. ONBOARDING & START
# ==============================================================================
def phone_verification_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text="📱 Share Mobile Number", request_contact=True)
        ]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Tap to verify your mobile number"
    )

async def finish_start_flow(message: Message, state: FSMContext, payload: str = ""):
    """Continue /start after mobile-number verification has completed."""
    await state.clear()
    args = ["/start"] + ([payload] if payload else [])

    try:
        await message.answer_sticker(WELCOME_STICKER_ID)
    except Exception:
        pass

    if len(args) > 1 and args[1].startswith("v_"):
        order_id = args[1].split("v_", 1)[1]
        msg = await message.answer(
            "🔄 <b>Verifying your payment securely...</b>\n<i>Connecting to gateway...</i>",
            parse_mode="HTML"
        )
        await run_payment_verification(message.from_user.id, order_id, msg)
        return

    user = db_query(
        "SELECT phone, referred_by FROM users WHERE user_id=?",
        (message.from_user.id,), fetchone=True
    )
    current_username = message.from_user.username or ""
    db_query(
        "UPDATE users SET username=? WHERE user_id=?",
        (current_username, message.from_user.id)
    )

    referral_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            candidate = int(args[1].split("ref_", 1)[1])
            if candidate != message.from_user.id and db_query(
                "SELECT user_id FROM users WHERE user_id=?", (candidate,), fetchone=True
            ):
                referral_id = candidate
        except (ValueError, TypeError):
            referral_id = None

    if not user or not user[0]:
        db_query(
            "INSERT OR IGNORE INTO users (user_id, first_name, username, joined_date, referred_by) VALUES (?, ?, ?, ?, ?)",
            (
                message.from_user.id,
                message.from_user.first_name,
                current_username,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                referral_id,
            )
        )
        log_activity(
            message.from_user.id,
            "ACCOUNT_CREATED",
            f"Referred by: {referral_id or 'None'}"
        )
    elif user and user[1] is None and referral_id:
        db_query(
            "UPDATE users SET referred_by=? WHERE user_id=?",
            (referral_id, message.from_user.id)
        )

    log_activity(message.from_user.id, "CMD_START")
    await send_main_menu(message)

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    payload = ""
    args = message.text.split() if message.text else ["/start"]
    if len(args) > 1:
        payload = args[1].strip()

    # Admin/owner does not need to share a phone number.
    if message.from_user.id != ADMIN_ID:
        user = db_query(
            "SELECT phone FROM users WHERE user_id=?",
            (message.from_user.id,), fetchone=True
        )
        phone = str(user[0]).strip() if user and user[0] else ""
        if not phone:
            await state.clear()
            await state.update_data(pending_start_payload=payload)
            await message.answer(
                "📱 <b>Mobile Number Verification Required</b>\n\n"
                "Welcome! First, please verify your mobile number to continue.\n\n"
                "👇 Tap <b>Share Mobile Number</b> below. Your number will be saved securely for your account.",
                reply_markup=phone_verification_kb(),
                parse_mode="HTML"
            )
            await state.set_state(UserStates.phone_verification)
            return

    await finish_start_flow(message, state, payload)

@dp.message(UserStates.phone_verification, F.contact)
async def receive_phone_verification(message: Message, state: FSMContext):
    contact = message.contact
    if not contact or contact.user_id != message.from_user.id:
        return await message.answer(
            "❌ <b>Please share your own Telegram mobile number.</b>\n\n"
            "Tap the <b>📱 Share Mobile Number</b> button below.",
            reply_markup=phone_verification_kb(),
            parse_mode="HTML"
        )

    phone = (contact.phone_number or "").strip()
    if not phone:
        return await message.answer(
            "❌ Mobile number could not be read. Please try again.",
            reply_markup=phone_verification_kb(),
            parse_mode="HTML"
        )

    db_query(
        "INSERT OR IGNORE INTO users (user_id, first_name, username, joined_date) VALUES (?, ?, ?, ?)",
        (
            message.from_user.id,
            message.from_user.first_name,
            message.from_user.username or "",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
    )
    db_query(
        "UPDATE users SET phone=?, first_name=?, username=? WHERE user_id=?",
        (
            phone,
            message.from_user.first_name,
            message.from_user.username or "",
            message.from_user.id,
        )
    )

    data = await state.get_data()
    payload = str(data.get("pending_start_payload") or "")
    await message.answer(
        "✅ <b>Mobile Number Verified Successfully!</b>\n\n"
        "Your account is now verified. Welcome to the store!",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML"
    )
    await finish_start_flow(message, state, payload)

@dp.message(UserStates.phone_verification)
async def phone_verification_reminder(message: Message, state: FSMContext):
    await message.answer(
        "📱 <b>Verification pending</b>\n\n"
        "Please use the <b>📱 Share Mobile Number</b> button to continue.",
        reply_markup=phone_verification_kb(),
        parse_mode="HTML"
    )

def main_menu_text(user_id: int) -> str:
    row=db_query("SELECT balance FROM users WHERE user_id=?", (user_id,), fetchone=True)
    balance=safe_float(row[0] if row else 0)
    return (f"✨ <b>DARK GHOST PAID STORE</b>\n\n"
            f"💰 <b>{t(user_id,'current_balance')}:</b> {fmt_curr(balance)}\n\n"
            f"{t(user_id,'quick_amount')}\n"
            f"👇 <b>{t(user_id,'choose_product')}</b>")

async def send_main_menu(ctx: Any):
    uid=ctx.from_user.id
    text = main_menu_text(uid)
    kb = main_menu_kb(uid)
    if isinstance(ctx, Message):
        await ctx.answer(text, reply_markup=kb, parse_mode='HTML')
    else:
        await ctx.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "back_main")
async def back_main(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    log_activity(call.from_user.id, "RETURN_MAIN_MENU")
    await send_main_menu(call)

# ==============================================================================
# ==============================================================================
# 10.5 BOT BUY / BOT PROVISIONING
# ==============================================================================
def bot_buy_enabled() -> bool:
    return (not CLIENT_MODE) and get_setting("bot_buy_status", "OFF") == "ON"

def bot_price() -> float:
    return max(0.0, safe_float(get_setting("bot_buy_price", "1000.0"), 1000.0))

def bot_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def get_bot_plans(active_only=True):
    q = "SELECT id,name,price,duration_days,is_maintenance FROM bot_plans" + (" WHERE is_active=1" if active_only else "") + " ORDER BY price ASC, duration_days ASC"
    return db_query(q, fetchall=True) or []

def get_bot_plan_full(plan_id: int):
    return db_query(
        "SELECT id,name,price,duration_days,is_active,admin_panel_website_link,is_maintenance,setup_video "
        "FROM bot_plans WHERE id=?", (plan_id,), fetchone=True
    )

def format_plan_setup_video(value: str):
    value = (value or '').strip()
    if not value or value.lower() == 'none':
        return None, None
    if value.startswith('tg:'):
        return 'telegram', value[3:]
    return 'url', value

async def validate_bot_token(token: str) -> Optional[Dict[str, Any]]:
    test_bot = None
    try:
        test_bot = Bot(token=token, default=DefaultBotProperties(parse_mode="HTML"))
        me = await test_bot.get_me()
        return {"id": me.id, "username": me.username or "", "first_name": me.first_name or ""}
    except Exception as exc:
        logger.warning("Buyer bot token validation failed: %s", exc)
        return None
    finally:
        if test_bot is not None:
            try: await test_bot.session.close()
            except Exception: pass

def provision_client_bot(token: str, buyer_admin_id: int, buyer_user_id: int, price: float, bot_username: str, duration_days: int, plan_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    token_hash = bot_token_hash(token)
    bot_dir = os.path.join(CLIENT_BOT_ROOT, token_hash[:16])
    os.makedirs(bot_dir, exist_ok=True)
    os.chmod(bot_dir, 0o700)
    db_path = os.path.join(bot_dir, "Cuibcc.db")
    log_path = os.path.join(bot_dir, "bot_activity.log")
    env_file = os.path.join(bot_dir, "bot.env")
    expires_at = int(time.time()) + (int(duration_days) * 86400)
    plan_info = plan_info or {}
    admin_panel_website_link = str(plan_info.get("admin_panel_website_link", "") or "")
    setup_video = str(plan_info.get("setup_video", "None") or "None")
    with open(env_file, "w", encoding="utf-8") as f:
        f.write(
            f"BOT_TOKEN={token}\nADMIN_ID={buyer_admin_id}\nBOT_USERNAME=@{bot_username.lstrip('@')}\n"
            f"BOT_MODE=client\nBOT_DB_PATH={db_path}\nBOT_LOG_FILE={log_path}\nBOT_EXPIRES_AT={expires_at}\n"
            f"ADMIN_PANEL_WEBSITE_LINK={admin_panel_website_link}\n"
        )
    os.chmod(env_file, 0o600)
    env = os.environ.copy()
    env.update({"BOT_TOKEN": token, "ADMIN_ID": str(buyer_admin_id), "BOT_USERNAME": f"@{bot_username.lstrip('@')}", "BOT_MODE": "client", "BOT_DB_PATH": db_path, "BOT_LOG_FILE": log_path, "BOT_EXPIRES_AT": str(expires_at), "ADMIN_PANEL_WEBSITE_LINK": admin_panel_website_link})
    import subprocess, sys
    proc = subprocess.Popen([sys.executable, os.path.abspath(__file__)], cwd=os.path.dirname(os.path.abspath(__file__)), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    db_query(
        "INSERT INTO bot_sales (buyer_user_id, bot_username, bot_token_hash, bot_admin_id, price_paid, db_path, pid, status, created_at, duration_days, expires_at, demo_video, admin_panel_website_link) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?, ?, ?, ?, ?)",
        (buyer_user_id, f"@{bot_username.lstrip('@')}", token_hash, buyer_admin_id, price, db_path, proc.pid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), duration_days, expires_at, setup_video, admin_panel_website_link)
    )
    return {"pid": proc.pid, "db_path": db_path, "bot_username": f"@{bot_username.lstrip('@')}", "expires_at": expires_at}

@dp.callback_query(F.data == "menu_bot_buy")
async def menu_bot_buy(call: CallbackQuery):
    await call.answer()
    if not bot_buy_enabled(): return await call.answer("Bot Buy is currently unavailable.", show_alert=True)
    plans = get_bot_plans()
    if not plans:
        price = bot_price()
        text = f"🤖 <b>BOT BUY</b>\n\n📭 <b>No Bot Buy plans are available right now.</b>\n\nAdmin can add a plan with price and validity from the Admin Panel.\n\nCurrent fallback price: {fmt_curr(price)}"
        return await call.message.edit_text(text, reply_markup=back_kb(), parse_mode="HTML")
    text = "🤖 <b>BOT BUY</b>\n━━━━━━━━━━━━━━━━━━\n\n✨ <b>Choose your bot plan:</b>\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for plan_id, name, price, days, is_maintenance in plans:
        if int(is_maintenance or 0):
            text += f"📦 <b>{name}</b>\n🛠️ <b>MAINTENANCE</b>\n\n"
            kb.inline_keyboard.append([InlineKeyboardButton(text=f"🛠️ {name} — Maintenance", callback_data=f"botplan_{plan_id}", style="danger")])
        else:
            text += f"📦 <b>{name}</b>\n💰 {fmt_curr(price)} · ⏳ {days} days\n\n"
            kb.inline_keyboard.append([InlineKeyboardButton(text=f"🛒 {name} — {fmt_curr(price)} / {days} Days", callback_data=f"botplan_{plan_id}", style="success")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="➡️ Back to Menu", callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.regexp(r"^botplan_[0-9]+$"))
async def select_bot_plan(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if not bot_buy_enabled(): return await call.answer("Bot Buy is currently disabled.", show_alert=True)
    try: plan_id = int(call.data.split("_",1)[1])
    except Exception: return await call.answer("Invalid plan.", show_alert=True)
    plan = get_bot_plan_full(plan_id)
    if not plan or not int(plan[4] or 0): return await call.answer("This plan is no longer available.", show_alert=True)
    _, name, price, days, _active, admin_panel_website_link, is_maintenance, setup_video = plan
    if int(is_maintenance or 0):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="↩️ Back to Shop", callback_data="menu_bot_buy", style="primary"),
                InlineKeyboardButton(text="🔔 Notify Me", callback_data=f"botplan_notify_{plan_id}", style="success")
            ]
        ])
        return await call.message.edit_text(
            f"📦 <b>{name}</b>\n━━━━━━━━━━━━━━━━━━\n\n🛠️ <b>This product abhi maintenance mein hai.</b>\n\n"
            f"Jab bhi available hoga, notify karenge.\n\n👇 <b>Notify button dabao — available hote hi turant alert milega!</b>",
            reply_markup=kb, parse_mode="HTML"
        )
    user = db_query("SELECT balance FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    balance = safe_float(user[0] if user else 0)
    if balance < safe_float(price):
        deficit = safe_float(price) - balance
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"💳 Add Balance — {fmt_curr(deficit)}", callback_data="menu_add_balance", style="success")],[InlineKeyboardButton(text="➡️ Back to Plans", callback_data="menu_bot_buy", style="danger")]])
        return await call.message.edit_text(f"❌ <b>Insufficient Balance</b>\n\n📦 Plan: <b>{name}</b>\n💰 Price: <b>{fmt_curr(price)}</b>\n💳 Balance: <b>{fmt_curr(balance)}</b>\n💸 Required: <b>{fmt_curr(deficit)}</b> more.", reply_markup=kb, parse_mode="HTML")
    await state.clear(); await state.update_data(
        bot_plan_id=plan_id, bot_plan_name=name, bot_plan_price=safe_float(price), bot_plan_days=int(days),
        bot_plan_admin_panel_website_link=admin_panel_website_link or "",
        bot_plan_setup_video=setup_video or "None"
    )
    await state.set_state(UserStates.bot_buy_token)
    await call.message.edit_text(f"🤖 <b>BOT BUY — STEP 1/2</b>\n\n📦 <b>Plan:</b> {name}\n💰 <b>Price:</b> {fmt_curr(price)}\n⏳ <b>Validity:</b> {days} days\n\nSend your <b>BotFather token</b>.\n\n<i>Your token is used only to start the bot you are buying. Never share a token you do not control.</i>", reply_markup=back_kb("menu_bot_buy"), parse_mode="HTML")

@dp.message(UserStates.bot_buy_token)
async def receive_bot_buy_token(message: Message, state: FSMContext):
    if (message.text or "").strip().lower() == "/cancel":
        await state.clear(); return await message.answer("❌ Bot purchase cancelled.", reply_markup=main_menu_kb(message.from_user.id), parse_mode="HTML")
    token = (message.text or "").strip()
    try: await message.delete()
    except Exception: pass
    if len(token) < 30 or ":" not in token:
        return await message.answer("❌ Invalid BotFather token format. Please send the complete token or /cancel.", parse_mode="HTML")
    if db_query("SELECT id FROM bot_sales WHERE bot_token_hash=?", (bot_token_hash(token),), fetchone=True):
        return await message.answer("⚠️ This bot token has already been registered in the system.", parse_mode="HTML")
    await message.answer("🔎 <b>Validating BotFather token...</b>", parse_mode="HTML")
    bot_info = await validate_bot_token(token)
    if not bot_info:
        return await message.answer("❌ Token validation failed. Please send a valid BotFather token.", parse_mode="HTML")
    await state.update_data(bot_token=token, bot_username=bot_info["username"], bot_id=bot_info["id"])
    await state.set_state(UserStates.bot_buy_admin_id)
    await message.answer(f"✅ <b>Bot Token Verified</b>\n\n🤖 Bot: <b>@{bot_info['username']}</b>\n\n<b>STEP 2/2:</b> Send your Telegram <b>Admin User ID</b> (numbers only).", reply_markup=back_kb("menu_bot_buy"), parse_mode="HTML")

@dp.message(UserStates.bot_buy_admin_id)
async def receive_bot_buy_admin_id(message: Message, state: FSMContext):
    if (message.text or "").strip().lower() == "/cancel":
        await state.clear(); return await message.answer("❌ Bot purchase cancelled.", reply_markup=main_menu_kb(message.from_user.id), parse_mode="HTML")
    raw = (message.text or "").strip()
    try: await message.delete()
    except Exception: pass
    if not raw.isdigit() or int(raw) <= 0:
        return await message.answer("❌ Admin ID must contain numbers only.", parse_mode="HTML")
    buyer_admin_id = int(raw)
    data = await state.get_data(); token = data.get("bot_token", ""); bot_username = data.get("bot_username", "")
    price = safe_float(data.get("bot_plan_price", 0)); days = int(data.get("bot_plan_days", 0)); plan_id = data.get("bot_plan_id")
    if not token or not price or not days or not plan_id:
        await state.clear(); return await message.answer("❌ Bot plan session expired. Please start Bot Buy again.", reply_markup=main_menu_kb(message.from_user.id), parse_mode="HTML")
    user = db_query("SELECT balance FROM users WHERE user_id=?", (message.from_user.id,), fetchone=True)
    balance = safe_float(user[0] if user else 0)
    if balance < price:
        await state.clear(); return await message.answer(f"❌ Balance changed during setup. You need {fmt_curr(price-balance)} more.", reply_markup=main_menu_kb(message.from_user.id), parse_mode="HTML")
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor(); cur.execute("UPDATE users SET balance=balance-?, spent=spent+? WHERE user_id=? AND balance>=?", (price, price, message.from_user.id, price))
        if cur.rowcount != 1:
            conn.rollback(); await state.clear(); return await message.answer("❌ Your balance is no longer sufficient. No money was deducted.", reply_markup=main_menu_kb(message.from_user.id), parse_mode="HTML")
        conn.commit()
    finally: conn.close()
    plan_info = {
        "admin_panel_website_link": data.get("bot_plan_admin_panel_website_link", ""),
        "setup_video": data.get("bot_plan_setup_video", "None"),
    }
    try:
        info = provision_client_bot(token, buyer_admin_id, message.from_user.id, price, bot_username or str(data.get("bot_id", "bot")), days, plan_info)
    except Exception:
        db_query("UPDATE users SET balance=balance+?, spent=MAX(0, spent-?) WHERE user_id=?", (price, price, message.from_user.id)); await state.clear(); logger.exception("Bot provisioning failed")
        return await message.answer("❌ Bot launch failed. Your balance has been refunded.", reply_markup=main_menu_kb(message.from_user.id), parse_mode="HTML")
    await state.clear()
    await notify_bot_sales_channel(message.from_user.id, info["bot_username"], buyer_admin_id, price, days, info["expires_at"], data.get("bot_plan_name", "Bot Plan"))
    expiry = datetime.fromtimestamp(info["expires_at"]).strftime("%d %b %Y, %I:%M %p")
    text = ("🎉 <b>BOT PURCHASE SUCCESSFUL</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <b>Bot:</b> {info['bot_username']}\n💰 <b>Paid:</b> {fmt_curr(price)}\n⏳ <b>Validity:</b> {days} days\n📅 <b>Expires:</b> {expiry}\n👑 <b>Admin ID:</b> <code>{buyer_admin_id}</code>\n\n"
            "✅ Your standalone bot has been started.\n"
            "✅ Separate database and client configuration.\n"
            "🚫 Seller FamPay credentials are not copied.\n🚫 Seller Reseller API credentials are not copied.\n\n"
            "Use <b>/admin</b> in your bot with the Admin ID you provided to configure it.")
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    demo_type, demo_value = format_plan_setup_video(data.get("bot_plan_setup_video", "None"))
    if demo_type == "url":
        kb.inline_keyboard.append([InlineKeyboardButton(text="🎥 Bot Setup Demo Video", url=demo_value, style="primary")])
    panel_link = data.get("bot_plan_admin_panel_website_link", "")
    if panel_link:
        text += f'\n\n🌐 <b>ADMIN PANEL WEBSITE LINK:</b> <a href="{panel_link}">{panel_link}</a>'
    kb.inline_keyboard.append([InlineKeyboardButton(text="➡️ Back to Menu", callback_data="back_main", style="danger")])
    await message.answer(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
    if demo_type == "telegram":
        try:
            await message.answer_video(demo_value, caption="🎥 <b>BOT SETUP DEMO VIDEO</b>", parse_mode="HTML")
        except Exception:
            await message.answer("⚠️ Setup video is configured, but Telegram could not send it right now.", parse_mode="HTML")

async def owner_bot_sales_monitor() -> None:
    """Keep the purchased-bot dashboard status current."""
    if CLIENT_MODE: return
    while True:
        try:
            rows = db_query("SELECT id, db_path, pid, status, expires_at FROM bot_sales WHERE status='running'", fetchall=True) or []
            now=int(time.time())
            for sid, dbpath, pid, status, exp in rows:
                if exp and int(exp) <= now:
                    db_query("UPDATE bot_sales SET status='expired' WHERE id=?", (sid,))
                elif pid and not _pid_running(pid):
                    db_query("UPDATE bot_sales SET status='stopped' WHERE id=?", (sid,))
        except Exception as exc:
            logger.warning("Bot sales monitor error: %s", exc)
        await asyncio.sleep(30)

async def client_expiry_task() -> None:
    if not CLIENT_MODE: return
    raw = os.getenv("BOT_EXPIRES_AT", "0").strip()
    try: expires_at = int(raw)
    except ValueError: expires_at = 0
    if expires_at <= 0: return
    delay = max(0, expires_at - int(time.time()))
    await asyncio.sleep(delay)
    try:
        await bot.send_message(ADMIN_ID, "⏳ <b>BOT PLAN EXPIRED</b>\n\nThis bot's paid validity has ended. The bot is now shutting down.", parse_mode="HTML")
    except Exception: pass
    try: await bot.session.close()
    except Exception: pass
    bot_dir = os.path.dirname(os.path.abspath(DB_PATH))
    try:
        import shutil
        shutil.rmtree(bot_dir)
    except Exception as exc:
        logger.warning("Could not remove expired client data: %s", exc)
    os._exit(0)

# 10A. LANGUAGE SELECTOR
# ==============================================================================
@dp.callback_query(F.data == "menu_language")
async def language_menu(call: CallbackQuery):
    await call.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    codes = list(LANGUAGES.keys())
    for i in range(0, len(codes), 2):
        kb.inline_keyboard.append([InlineKeyboardButton(text=LANGUAGES[c], callback_data=f"lang_{c}", style="success") for c in codes[i:i+2]])
    kb.inline_keyboard.append([InlineKeyboardButton(text=t(call.from_user.id,"back"), callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text(t(call.from_user.id,"select_language"), reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("lang_"))
async def set_language(call: CallbackQuery):
    code=call.data.split("_",1)[1]
    if code not in I18N:
        return await call.answer("Unsupported language", show_alert=True)
    db_query("UPDATE users SET language=? WHERE user_id=?", (code, call.from_user.id))
    await call.answer("Language updated")
    await send_main_menu(call)

# ==============================================================================
# 11. ADD BALANCE
# ==============================================================================
@dp.callback_query(F.data == "menu_add_balance")
async def select_gateway_menu(call: CallbackQuery):
    await call.answer()
    log_activity(call.from_user.id, "VIEW_ADD_BALANCE")
    if CLIENT_MODE:
        return await call.message.edit_text(
            "💳 <b>ADD BALANCE</b>\n\nPayment gateway is not included in this standalone bot.\n\nThe bot owner can add wallet balance from the Admin Panel.",
            reply_markup=back_kb("back_main"), parse_mode="HTML"
        )
    text = f"{t(call.from_user.id,'add_funds')}\n\n{t(call.from_user.id,'quick_amount')}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(call.from_user.id,"upi"), callback_data="gateway_inr", icon_custom_emoji_id=get_emoji_icon("upi"), style="primary"),
         InlineKeyboardButton(text=t(call.from_user.id,"binance"), callback_data="gateway_crypto", style="primary")],
        [InlineKeyboardButton(text=t(call.from_user.id,"back"), callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

# ==============================================================================
# 12. FAMPAY UPI PAYMENT FLOW
# ==============================================================================
@dp.callback_query(F.data == "gateway_inr")
async def add_balance_inr(call: CallbackQuery):
    await call.answer()
    text = f"💵 <b>— FAMPAY UPI DEPOSIT —</b> 💵\n\n{t(call.from_user.id,'quick_amount')}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="₹50", callback_data="pay_50", style="primary"), InlineKeyboardButton(text="₹100", callback_data="pay_100", style="primary")],
        [InlineKeyboardButton(text="₹200", callback_data="pay_200", style="primary"), InlineKeyboardButton(text="₹500", callback_data="pay_500", style="primary")],
        [InlineKeyboardButton(text="₹1000", callback_data="pay_1000", style="primary"), InlineKeyboardButton(text="₹2000", callback_data="pay_2000", style="primary")],
        [InlineKeyboardButton(text=t(call.from_user.id,"custom_amount"), callback_data="custom_deposit_keypad", style="primary")],
        [InlineKeyboardButton(text=t(call.from_user.id,"back"), callback_data="menu_add_balance", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "custom_deposit_keypad")
async def show_custom_keypad(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await state.set_state(UserStates.custom_amount_input)
    await state.update_data(amount_str="0")
    await show_keypad(call.message, "0", call.from_user.id)

async def show_keypad(message: Message, amount_str: str = "0", user_id: Optional[int] = None):
    """Render the custom deposit keypad without relying on an undefined callback variable."""
    uid = user_id or getattr(getattr(message, "chat", None), "id", 0)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1", callback_data="kp_1", style="primary"),
            InlineKeyboardButton(text="2", callback_data="kp_2", style="primary"),
            InlineKeyboardButton(text="3", callback_data="kp_3", style="primary"),
        ],
        [
            InlineKeyboardButton(text="4", callback_data="kp_4", style="primary"),
            InlineKeyboardButton(text="5", callback_data="kp_5", style="primary"),
            InlineKeyboardButton(text="6", callback_data="kp_6", style="primary"),
        ],
        [
            InlineKeyboardButton(text="7", callback_data="kp_7", style="primary"),
            InlineKeyboardButton(text="8", callback_data="kp_8", style="primary"),
            InlineKeyboardButton(text="9", callback_data="kp_9", style="primary"),
        ],
        [
            InlineKeyboardButton(text="Clear", callback_data="kp_clear", style="danger"),
            InlineKeyboardButton(text="0", callback_data="kp_0", style="primary"),
            InlineKeyboardButton(text="⌫", callback_data="kp_backspace", style="danger"),
        ],
        [
            InlineKeyboardButton(
                text=f"✅ Confirm (₹{amount_str})",
                callback_data="kp_confirm",
                style="success",
            )
        ],
        [
            InlineKeyboardButton(
                text=t(uid, "back_menu"),
                callback_data="custom_keypad_back",
                icon_custom_emoji_id=get_emoji_icon("back"),
                style="danger",
            )
        ],
    ])
    keypad_text = f"{t(uid, 'enter_amount')}: ₹{amount_str}\n\n{t(uid, 'minmax')}"
    await message.edit_text(keypad_text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "custom_keypad_cancel", UserStates.custom_amount_input)
async def custom_keypad_cancel(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await show_fampay_amount_picker(call.from_user.id, call.message)


@dp.callback_query(F.data == "custom_keypad_back", UserStates.custom_amount_input)
async def custom_keypad_back(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await send_main_menu(call)


@dp.callback_query(F.data.startswith("kp_"), UserStates.custom_amount_input)
async def keypad_handler(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    amount_str = data.get("amount_str", "0")
    action = call.data.split("_")[1]
    if action == "confirm":
        if amount_str == "0":
            await call.answer("Amount cannot be zero.", show_alert=True)
            return
        try:
            amount = float(amount_str)
            if amount < 1:
                await call.answer("Minimum deposit is ₹1.", show_alert=True)
                return
            if amount > 50000:
                await call.answer("Maximum deposit is ₹50,000.", show_alert=True)
                return
            await state.clear()
            await call.message.edit_text("⏳ <b>Generating Secure QR Code...</b>", parse_mode='HTML')
            await generate_fampay_order(call.from_user.id, amount, call.message)
        except ValueError:
            await call.answer("Invalid amount.", show_alert=True)
        return
    if action == "backspace":
        if len(amount_str) > 1: amount_str = amount_str[:-1]
        else: amount_str = "0"
    elif action == "clear":
        amount_str = "0"
    else:
        if amount_str == "0": amount_str = action
        else: amount_str += action
        if len(amount_str) > 6: amount_str = amount_str[:6]
    await state.update_data(amount_str=amount_str)
    await show_keypad(call.message, amount_str, call.from_user.id)
    await call.answer()

@dp.callback_query(F.data.startswith("pay_"))
async def process_fampay_payment_callback(call: CallbackQuery):
    await call.answer()
    inr_amount = float(call.data.split("_")[1])
    await call.message.edit_text("⏳ <b>Generating Secure QR Code via FamPay...</b>", parse_mode='HTML')
    await generate_fampay_order(call.from_user.id, inr_amount, call.message)

async def generate_fampay_order(user_id: int, inr_amount: float, message_obj: Any, purpose: str = "wallet_deposit", product_id: int = None):
    if CLIENT_MODE:
        return await message_obj.edit_text("⚠️ FamPay is disabled in standalone bot mode.", reply_markup=back_kb("back_main"), parse_mode="HTML")
    """Generate the payment order, download the QR image and send it in Telegram."""
    api_key = get_setting("fampay_api_key", "")
    if not api_key or api_key == "YOUR_FAMPAY_API_KEY":
        return await message_obj.edit_text(t(user_id,"gateway_offline"), reply_markup=back_kb("gateway_inr"), parse_mode='HTML')
    upi_id = get_setting("fampay_upi_id", "")
    if not upi_id:
        return await message_obj.edit_text("⚠️ UPI ID not configured. Admin needs to set UPI ID.", reply_markup=back_kb("gateway_inr"), parse_mode='HTML')
    current_time = int(time.time())
    result = await generate_fampay_qr(user_id, inr_amount, upi_id)
    if result.get("status") != "success":
        return await message_obj.edit_text(f"❌ <b>Gateway Error:</b> {result.get('message','Unknown error')}", reply_markup=back_kb("gateway_inr"), parse_mode='HTML')
    data = result.get("data", {})
    qr_url = data.get("qr_url")
    if not qr_url:
        return await message_obj.edit_text("❌ <b>Gateway Error:</b> QR URL was not returned.", reply_markup=back_kb("gateway_inr"), parse_mode='HTML')
    order_id = data.get("order_id", f"FAMPAY{user_id}{current_time}")
    upi_id = data.get("upi_id", upi_id)
    expires_at_str = data.get("expires_at_ist") or (datetime.now()+timedelta(minutes=5)).strftime("%d-%m-%Y %H:%M:%S")
    created_at = data.get("created_at_ist") or datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    try:
        expiry_time = datetime.strptime(expires_at_str, "%d-%m-%Y %H:%M:%S")
        expires_timestamp = int(expiry_time.timestamp())
    except Exception:
        expires_timestamp = int(time.time()+300)
    db_query("INSERT OR REPLACE INTO transactions (order_id,user_id,amount_inr,status,timestamp,qr_url,upi_id,expires_at,purpose,product_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
             (order_id,user_id,inr_amount,'pending',current_time,qr_url,upi_id,expires_timestamp,purpose,product_id))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(user_id,"verify"), callback_data=f"verify_{order_id}", style="success")],
        [InlineKeyboardButton(text=t(user_id,"cancel_payment"), callback_data=f"cancel_payment_{order_id}", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")],
    ])
    caption=(f"{t(user_id,'upi_qr')}\n\n{t(user_id,'scan_pay',amount=fmt_curr(inr_amount))}\n\n"
             f"{t(user_id,'pay_after')}\n\n{t(user_id,'expires')}\n\n"
             f"🆔 <code>{order_id}</code>\n🏦 <code>{upi_id}</code>")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(qr_url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                content=await resp.read()
                ctype=resp.headers.get('Content-Type','').lower()
                if resp.status != 200 or not content or ('image' not in ctype and not qr_url.lower().endswith(('.png','.jpg','.jpeg','.webp'))):
                    raise RuntimeError(f"QR download failed: HTTP {resp.status}")
        try:
            await message_obj.delete()
        except Exception:
            pass
        await bot.send_photo(user_id, BufferedInputFile(content, filename=f"{order_id}.png"), caption=caption, reply_markup=kb, parse_mode='HTML')
    except Exception as e:
        logger.warning(f"Could not send QR image directly: {e}")
        await message_obj.edit_text(caption+f'\n\n<a href="{qr_url}">🖼 Open QR Code</a>', reply_markup=kb, parse_mode='HTML')
    log_activity(user_id, "GENERATE_INVOICE_FAMPAY", f"Amount: {inr_amount}, Order ID: {order_id}")

@dp.callback_query(F.data.startswith("cancel_payment_"))
async def cancel_fampay_payment(call: CallbackQuery):
    order_id=call.data.split("cancel_payment_",1)[1]
    txn=db_query("SELECT amount_inr,status FROM transactions WHERE order_id=? AND user_id=?", (order_id,call.from_user.id), fetchone=True)
    if not txn:
        return await call.answer(t(call.from_user.id,"deposit_order_not_found"), show_alert=True)
    if txn[1] == 'paid':
        return await call.answer("This payment is already credited and cannot be cancelled.", show_alert=True)
    db_query("UPDATE transactions SET status='cancelled' WHERE order_id=? AND user_id=? AND status='pending'", (order_id,call.from_user.id))
    await call.answer("Payment cancelled")
    amount=fmt_curr(txn[0])
    # After cancellation, always return the user to the amount-selection screen.
    # The user can choose a new amount instead of automatically reusing the old amount.
    # Delete the old QR message, then show a fresh amount-selection screen.
    try:
        await call.message.delete()
    except Exception:
        pass
    await show_fampay_amount_picker(call.from_user.id, call.from_user.id)
    log_activity(call.from_user.id,"CANCEL_PAYMENT",f"Order: {order_id}, Amount: {txn[0]}")

async def show_fampay_amount_picker(user_id: int, message_or_user_id):
    """Show a fresh UPI amount picker after cancel/back, including Custom Amount."""
    text = f"💵 <b>— FAMPAY UPI DEPOSIT —</b> 💵\\n\\n{t(user_id,'quick_amount')}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="₹50", callback_data="pay_50", style="primary"),
         InlineKeyboardButton(text="₹100", callback_data="pay_100", style="primary")],
        [InlineKeyboardButton(text="₹200", callback_data="pay_200", style="primary"),
         InlineKeyboardButton(text="₹500", callback_data="pay_500", style="primary")],
        [InlineKeyboardButton(text="₹1000", callback_data="pay_1000", style="primary"),
         InlineKeyboardButton(text="₹2000", callback_data="pay_2000", style="primary")],
        [InlineKeyboardButton(text=t(user_id,"custom_amount"), callback_data="custom_deposit_keypad", style="primary")],
        [InlineKeyboardButton(text=t(user_id,"back_menu"), callback_data="back_main",
                              icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    # message_or_user_id can be a Message/CallbackQuery message or a numeric user id.
    if hasattr(message_or_user_id, "edit_text"):
        await message_or_user_id.edit_text(text, reply_markup=kb, parse_mode='HTML')
    else:
        # Kept for compatibility with cancellation callers; they will normally pass a message.
        await bot.send_message(message_or_user_id, text, reply_markup=kb, parse_mode='HTML')


@dp.callback_query(F.data == "retry_add_balance")
async def retry_add_balance(call: CallbackQuery, state: FSMContext):
    """After a cancelled QR, reopen the amount picker."""
    await call.answer()
    await state.clear()
    if CLIENT_MODE:
        return await call.message.edit_text(
            "💳 <b>ADD BALANCE</b>\\n\\nPayment gateway is not included in this standalone bot.",
            reply_markup=back_kb("back_main"), parse_mode="HTML"
        )
    await show_fampay_amount_picker(call.from_user.id, call.message)


@dp.callback_query(F.data == "cancel_back_main")
async def cancel_back_main(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await send_main_menu(call)

@dp.callback_query(F.data.startswith("verify_"))
async def manual_verify_callback(call: CallbackQuery):
    await call.answer()
    order_id = call.data.split("_", 1)[1]
    await run_payment_verification(call.from_user.id, order_id, call)

# ==============================================================================
# 13. BINANCE CRYPTO PAYMENT
# ==============================================================================
@dp.callback_query(F.data == "gateway_crypto")
async def add_balance_crypto(call: CallbackQuery, state: FSMContext):
    await call.answer()
    address_check = db_query("SELECT value FROM settings WHERE key='binance_address'", fetchone=True)
    if not address_check or not address_check[0]:
        return await call.message.edit_text("⚠️ Binance Gateway is currently offline. Admin has not set a deposit address.", reply_markup=back_kb("menu_add_balance"), parse_mode='HTML')
    deposit_address = address_check[0]
    msg = (f"🪙 <b>— BINANCE USDT DEPOSIT —</b> 🪙\n\n💵 <b>Exchange Rate:</b> 1 USDT = ₹{USDT_TO_INR}\n⚠️ <b>Network:</b> Please send via <b>TRC20</b> or <b>BEP20</b>.\n\n👇 <b>Send your USDT to this exact address:</b>\n<code>{deposit_address}</code>\n\n━━━━━━━━━━━━━━━━━━\n✅ <b>After sending the USDT, reply to this message with your exact TxID (Transaction Hash) to instantly claim your balance.</b>")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Cancel", callback_data="menu_add_balance", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]])
    await call.message.edit_text(msg, reply_markup=kb, parse_mode='HTML')
    await state.set_state(UserStates.wait_for_crypto_txid)

@dp.message(UserStates.wait_for_crypto_txid)
async def process_crypto_txid(m: Message, state: FSMContext):
    txid = m.text.strip()
    user_id = m.from_user.id
    if len(txid) < 10: return await m.answer("❌ That doesn't look like a valid TxID. Please try again.")
    if db_query("SELECT txid FROM crypto_txns WHERE txid=?", (txid,), fetchone=True):
        return await m.answer("⚠️ This Transaction ID has already been claimed in the system!", reply_markup=back_kb("menu_add_balance"), parse_mode='HTML')
    api_key_check = db_query("SELECT value FROM settings WHERE key='binance_api'", fetchone=True)
    secret_key_check = db_query("SELECT value FROM settings WHERE key='binance_secret'", fetchone=True)
    if not api_key_check or not secret_key_check:
        return await m.answer("⚠️ Binance API is missing on the server. Contact Support.", reply_markup=back_kb("menu_add_balance"), parse_mode='HTML')
    await m.answer("🔄 <b>Verifying your TxID with Binance Blockchain...</b>\n<i>This may take up to 30 seconds...</i>", parse_mode='HTML')
    api_key = api_key_check[0]; secret_key = secret_key_check[0]
    timestamp = int(time.time() * 1000)
    query_string = f"timestamp={timestamp}"
    signature = hmac.new(secret_key.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    headers = {'X-MBX-APIKEY': api_key}
    url = f"https://api.binance.com/sapi/v1/capital/deposit/hisrec?{query_string}&signature={signature}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    try: history = await resp.json(content_type=None)
                    except: history = []
                    found = False
                    for deposit in history:
                        if deposit.get("txId") == txid and deposit.get("status") == 1:
                            found = True
                            usdt_amount = float(deposit.get("amount"))
                            inr_amount = usdt_amount * USDT_TO_INR
                            db_query("INSERT INTO crypto_txns (txid, user_id, amount_usdt, timestamp) VALUES (?, ?, ?, ?)", (txid, user_id, usdt_amount, int(time.time())))
                            db_query("UPDATE users SET balance = balance + ? WHERE user_id=?", (inr_amount, user_id))
                            await m.answer(f"🎉 <b>CRYPTO DEPOSIT SUCCESSFUL!</b>\n\n✅ We safely received <b>{usdt_amount} USDT</b>.\n💰 <b>{fmt_curr(inr_amount)}</b> has been added to your balance!", reply_markup=main_menu_kb(m.from_user.id), parse_mode='HTML')
                            await send_advanced_notification(user_id, "DEPOSIT", inr_amount, product=txid, gateway="Binance Crypto")
                            log_activity(user_id, "CRYPTO_DEPOSIT", f"TxID: {txid}, Amount: {inr_amount}")
                            await state.clear()
                            break
                    if not found: await m.answer("❌ <b>TxID Not Found or Still Pending!</b>\nMake sure the transaction is fully confirmed. Try again in 5 mins.", reply_markup=back_kb("menu_add_balance"), parse_mode='HTML')
                else: await m.answer(f"⚠️ <b>Binance Server Error:</b> HTTP {resp.status}.", reply_markup=back_kb("menu_add_balance"), parse_mode='HTML')
        except Exception as e: await m.answer(f"⚠️ <b>Connection Error:</b> {str(e)}", reply_markup=back_kb("menu_add_balance"), parse_mode='HTML')

# ==============================================================================
# 13A. MAIN MENU EXTRA BUTTONS
# ==============================================================================
@dp.callback_query(F.data == "menu_referral")
async def menu_referral(call: CallbackQuery):
    await call.answer()
    link=f"https://t.me/{BOT_USERNAME.lstrip('@')}?start=ref_{call.from_user.id}"
    text=f"{t(call.from_user.id,'referral')}\n\nShare this referral link with your friends:\n<code>{link}</code>"
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(call.from_user.id,'back'),callback_data="back_main",style="danger")]])
    await call.message.edit_text(text,reply_markup=kb,parse_mode='HTML')

@dp.callback_query(F.data == "menu_feedback")
async def menu_feedback(call: CallbackQuery):
    await call.answer()
    text=f"{t(call.from_user.id,'feedback')}\n\nPublic feedback is available from the store support channel."
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(call.from_user.id,'back'),callback_data="back_main",style="danger")]])
    await call.message.edit_text(text,reply_markup=kb,parse_mode='HTML')

def _spin_remaining_seconds(user_id: int) -> int:
    row = db_query("SELECT last_spin FROM users WHERE user_id=?", (user_id,), fetchone=True)
    if not row or not row[0]:
        return 0
    try:
        last = datetime.fromisoformat(row[0])
        cooldown = safe_float(get_setting("spin_cooldown_hours", str(SPIN_COOLDOWN_HOURS)), SPIN_COOLDOWN_HOURS) * 3600
        return max(0, int(cooldown - (datetime.now() - last).total_seconds()))
    except (ValueError, TypeError):
        return 0

def _format_remaining(seconds: int) -> str:
    hours, rem = divmod(max(0, seconds), 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}h {minutes:02d}m {secs:02d}s"

@dp.callback_query(F.data == "menu_lucky")
async def menu_lucky(call: CallbackQuery):
    await call.answer()
    uid = call.from_user.id
    remaining = _spin_remaining_seconds(uid)
    min_reward = safe_float(get_setting("spin_min_reward", str(SPIN_MIN_REWARD)), SPIN_MIN_REWARD)
    max_reward = min(safe_float(get_setting("spin_max_reward", str(SPIN_MAX_REWARD)), SPIN_MAX_REWARD), SPIN_HARD_CEILING - 1.0)
    text = (f"🎁 <b>Daily Lucky Spin Wheel</b> 🎁\n━━━━━━━━━━━━━━━━━━\n\n"
            f"🎡 Spin the wheel once every <b>24 hours</b>.\n"
            f"💰 <b>Winning Range:</b> {fmt_curr(min_reward)} to {fmt_curr(max_reward)}\n"
            f"🔒 <b>Hard Maximum:</b> {fmt_curr(SPIN_HARD_CEILING)}\n"
            f"🎯 <b>Spin Limit:</b> 1 spin per 24 hours\n\n")
    if remaining > 0:
        text += f"⏳ <b>Next spin available in:</b> {_format_remaining(remaining)}"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🔒 Locked ({_format_remaining(remaining)})", callback_data="spin_locked", style="danger")],
            [InlineKeyboardButton(text=t(uid,'back'), callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
        ])
    else:
        text += "🟢 <b>Your daily spin is ready!</b>"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎡 SPIN NOW", callback_data="spin_claim", style="success")],
            [InlineKeyboardButton(text=t(uid,'back'), callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
        ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "spin_locked")
async def spin_locked(call: CallbackQuery):
    remaining = _spin_remaining_seconds(call.from_user.id)
    await call.answer(f"⏳ Next spin in {_format_remaining(remaining)}", show_alert=True)

@dp.callback_query(F.data == "spin_claim")
async def spin_claim(call: CallbackQuery):
    uid = call.from_user.id
    remaining = _spin_remaining_seconds(uid)
    if remaining > 0:
        return await call.answer(f"⏳ Next spin in {_format_remaining(remaining)}", show_alert=True)
    min_reward = max(0.01, safe_float(get_setting("spin_min_reward", str(SPIN_MIN_REWARD)), SPIN_MIN_REWARD))
    max_reward = min(safe_float(get_setting("spin_max_reward", str(SPIN_MAX_REWARD)), SPIN_MAX_REWARD), SPIN_HARD_CEILING - 1.0)
    if max_reward < min_reward:
        max_reward = min_reward
    reward = random.randint(int(round(min_reward * 100)), int(round(max_reward * 100))) / 100.0
    now = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    db_query("UPDATE users SET balance=balance+?, last_spin=? WHERE user_id=?", (reward, now, uid))
    db_query("INSERT INTO spin_rewards (amount) VALUES (?)", (reward,))
    log_activity(uid, "DAILY_SPIN", f"Reward: {reward}")
    new_balance = db_query("SELECT balance FROM users WHERE user_id=?", (uid,), fetchone=True)
    text = (f"🎉 <b>Daily Gift Spin Winner!</b> 🎉\n━━━━━━━━━━━━━━━━━━\n\n"
            f"🎁 <b>You won:</b> {fmt_curr(reward)}\n"
            f"💰 <b>Updated Wallet:</b> {fmt_curr(safe_float(new_balance[0] if new_balance else 0))}\n\n"
            f"⏳ Come back after <b>24 hours</b> for your next spin.")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Back to Menu", callback_data="back_main", style="danger")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "menu_team")
async def menu_team(call: CallbackQuery):
    await call.answer()
    uid = call.from_user.id
    row = db_query("SELECT COUNT(*), COALESCE(SUM(team_earnings),0) FROM users WHERE referred_by=?", (uid,), fetchone=True)
    team_count = row[0] if row else 0
    earnings = db_query("SELECT team_earnings FROM users WHERE user_id=?", (uid,), fetchone=True)
    total_earnings = safe_float(earnings[0] if earnings else 0)
    commission = safe_float(get_setting("referral_commission_percent", str(DEFAULT_REFERRAL_COMMISSION)), DEFAULT_REFERRAL_COMMISSION)
    link = f"https://t.me/{BOT_USERNAME.lstrip('@')}?start=ref_{uid}"
    members = db_query("SELECT first_name, username, joined_date FROM users WHERE referred_by=? ORDER BY joined_date DESC LIMIT 10", (uid,), fetchall=True) or []
    text = (f"👥 <b>MY TEAM</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Team Members:</b> {team_count}\n"
            f"💰 <b>Team Earnings:</b> {fmt_curr(total_earnings)}\n"
            f"📊 <b>Commission:</b> {commission:.2f}%\n\n"
            f"🔗 <b>Your Invite Link:</b>\n<code>{link}</code>\n\n")
    if members:
        text += "📋 <b>Recent Team Members</b>\n"
        for name, username, joined in members:
            text += f"• {name or 'User'} {('@'+username) if username else ''} — {joined or '-'}\n"
    else:
        text += "📭 <i>No team members yet.</i>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 My Referral Link", callback_data="menu_referral", style="success")],
        [InlineKeyboardButton(text=t(uid,'back'), callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

# ==============================================================================
# 14. SHOP – with uppercase categories and new point_down emoji
# ==============================================================================
def get_account_tier(user_row) -> str:
    """Return Regular, Reseller, Pro Reseller. Supports old DBs where is_pro_reseller may be absent."""
    if not user_row:
        return "Regular"
    try:
        if len(user_row) >= 2 and bool(user_row[-1]):
            return "Pro Reseller"
    except Exception:
        pass
    return "Reseller" if bool(user_row[1]) else "Regular"

def get_product_price(prod_normal, prod_reseller, prod_pro_usd, tier, vip=False):
    rate = safe_float(get_setting("pro_usd_inr_rate", "40.0"))
    if tier == "Pro Reseller":
        usd = safe_float(prod_pro_usd)
        return usd * rate, usd, rate
    base = safe_float(prod_reseller) if tier == "Reseller" else safe_float(prod_normal)
    if vip and tier != "Pro Reseller":
        base -= base * (VIP_DISCOUNT_PERCENTAGE / 100)
    return base, None, rate

@dp.callback_query(F.data == "menu_shop")
async def view_shop_panels(call: CallbackQuery):
    await call.answer()
    legacy = {"ALL PRODUCTS", "ANDROID NON ROOT PANEL", "ANDROID ROOT PANEL", "PC PANEL"}
    rows = db_query("SELECT DISTINCT TRIM(category) FROM products WHERE is_active=1 AND category IS NOT NULL AND TRIM(category) != '' ORDER BY TRIM(category)", fetchall=True) or []
    rows = [r for r in rows if str(r[0]).strip().upper() not in legacy]
    unc = db_query("SELECT COUNT(*) FROM products WHERE is_active=1 AND (category IS NULL OR TRIM(category)='')", fetchone=True)
    unc_count = int(unc[0] or 0) if unc else 0
    total = db_query("SELECT COUNT(*) FROM products WHERE is_active=1", fetchone=True)
    total_count = int(total[0] or 0) if total else 0
    if not rows:
        if total_count == 0:
            return await call.message.edit_text(f"{get_emoji('product_store')} <b><u>PRODUCT STORE</u></b>\n━━━━━━━━━━━━━━━━━━\n\n📭 <b>No products available yet.</b>", reply_markup=back_kb(), parse_mode='HTML')
        panels = db_query("SELECT DISTINCT TRIM(panel_name) FROM products WHERE is_active=1 AND panel_name IS NOT NULL AND TRIM(panel_name) != '' ORDER BY TRIM(panel_name)", fetchall=True) or []
        kb = InlineKeyboardMarkup(inline_keyboard=[])
        text = f"{get_emoji('product_store')} <b><u>PRODUCT STORE</u></b>\n━━━━━━━━━━━━━━━━━━\n\n🎮 <b>Choose a Hack / Panel:</b>\n"
        for row in panels:
            panel = str(row[0]).strip()
            kb.inline_keyboard.append([InlineKeyboardButton(text=f"🎮 {panel}", callback_data=f"directpanel_{selector_token(panel)}", style="primary")])
        if not panels:
            prods = db_query("SELECT id, name, price_inr, stock, reseller_price, validity, device_limit, api_enabled, pro_reseller_price_usd FROM products WHERE is_active=1 ORDER BY id DESC", fetchall=True) or []
            return await show_products_for_panel(call, prods, "PRODUCTS")
        kb.inline_keyboard.append([InlineKeyboardButton(text="BACK", callback_data="back_main", style="danger")])
        return await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    text = f"{get_emoji('product_store')} <b><u>PRODUCT STORE</u></b>\n━━━━━━━━━━━━━━━━━━\n\n📂 <b>Choose a category:</b>"
    for row in rows:
        cat = str(row[0]).strip()
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"📂 {cat}", callback_data=f"cat_{selector_token(cat)}", icon_custom_emoji_id=get_category_emoji(cat), style="primary")])
    if unc_count:
        kb.inline_keyboard.append([InlineKeyboardButton(text="📦 Uncategorized Products", callback_data="cat_uncategorized", style="primary")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="BACK", callback_data="back_main", style="danger")])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("directpanel_"))
async def view_direct_panel_products(call: CallbackQuery):
    await call.answer()
    token = call.data.split("directpanel_", 1)[1]
    panel = None
    rows = db_query("SELECT DISTINCT TRIM(panel_name) FROM products WHERE is_active=1 AND panel_name IS NOT NULL AND TRIM(panel_name) != ''", fetchall=True) or []
    for row in rows:
        candidate = str(row[0]).strip()
        if selector_token(candidate) == token:
            panel = candidate
            break
    if not panel:
        return await call.answer("❌ This Hack/Panel is no longer available. Please open Product Store again.", show_alert=True)
    prods = db_query("SELECT id, name, price_inr, stock, reseller_price, validity, device_limit, api_enabled, pro_reseller_price_usd FROM products WHERE panel_name=? AND is_active=1 ORDER BY id DESC", (panel,), fetchall=True) or []
    if not prods:
        return await call.answer("📭 No products available for this Hack/Panel.", show_alert=True)
    await show_products_for_panel(call, prods, panel)

@dp.callback_query(F.data.startswith("cat_"))
async def view_panel_names(call: CallbackQuery):
    await call.answer()
    token = call.data.split("cat_", 1)[1]
    if token == "uncategorized":
        prods = db_query("SELECT id, name, price_inr, stock, reseller_price, validity, device_limit, api_enabled, pro_reseller_price_usd FROM products WHERE is_active=1 AND (category IS NULL OR TRIM(category)='') ORDER BY id DESC", fetchall=True) or []
        if not prods:
            return await call.answer("📭 No products available in this category.", show_alert=True)
        return await show_products_for_panel(call, prods, "UNCATEGORIZED PRODUCTS")
    category = resolve_category_token(token)
    if not category:
        return await call.answer("❌ This category is no longer available. Please open Product Store again.", show_alert=True)
    panel_names = db_query("SELECT DISTINCT panel_name FROM products WHERE category LIKE ? AND is_active=1 AND panel_name IS NOT NULL AND TRIM(panel_name) != ''", (category + '%',), fetchall=True) or []
    prods = db_query("SELECT id, name, price_inr, stock, reseller_price, validity, device_limit, api_enabled, pro_reseller_price_usd FROM products WHERE category LIKE ? AND is_active=1 ORDER BY id DESC", (category + '%',), fetchall=True) or []
    if not prods:
        return await call.answer("📭 No products available in this category.", show_alert=True)
    if not panel_names:
        return await show_products_for_panel(call, prods, category)
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    text = f"{get_emoji('product_store')} <b><u>{category.upper()} PANELS</u></b>\n━━━━━━━━━━━━━━━━━━\n\n{get_emoji('point_down')} <b>Choose a panel:</b>"
    for pn in panel_names:
        panel = str(pn[0]).strip()
        kb.inline_keyboard.append([InlineKeyboardButton(text=panel, callback_data=f"pnl_{selector_token(category)}_{selector_token(panel)}", icon_custom_emoji_id=get_emoji_icon("product_store"), style="primary")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="BACK TO CATEGORIES", callback_data="menu_shop", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("pnl_"))
async def view_products_for_panel(call: CallbackQuery):
    await call.answer()
    parts = call.data.split("_", 2)
    if len(parts) != 3:
        return await call.answer("❌ Invalid panel selection.", show_alert=True)
    category = resolve_category_token(parts[1])
    if not category:
        return await call.answer("❌ This category is no longer available. Please open Product Store again.", show_alert=True)
    panel_name = resolve_panel_token(category, parts[2])
    if not panel_name:
        return await call.answer("❌ This panel is no longer available. Please open Product Store again.", show_alert=True)
    prods = db_query("SELECT id, name, price_inr, stock, reseller_price, validity, device_limit, api_enabled, pro_reseller_price_usd FROM products WHERE category LIKE ? AND panel_name LIKE ? AND is_active=1 ORDER BY id DESC", (category + '%', panel_name + '%'), fetchall=True) or []
    if not prods:
        return await call.answer("📭 No products available for this panel.", show_alert=True)
    await show_products_for_panel(call, prods, f"{category} - {panel_name}")

async def show_products_for_panel(call: CallbackQuery, prods: List[Tuple], header: str):
    """Render a panel's packages. Maintenance products are hidden completely.
    If every package in the panel is under maintenance, show one clean
    product-level maintenance screen instead of exposing package names/prices.
    """
    user = db_query("SELECT is_reseller, is_vip, is_pro_reseller FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    tier = "Pro Reseller" if user and bool(user[2]) else ("Reseller" if user and bool(user[0]) else "Regular")
    is_vip = bool(user and user[1])

    # Split live and maintenance packages. Maintenance packages must never be
    # rendered as individual package buttons to the customer.
    live_prods = []
    maintenance_prods = []
    for prod in prods:
        prod_id = int(prod[0])
        maint_row = db_query("SELECT is_maintenance FROM products WHERE id=?", (prod_id,), fetchone=True)
        if maint_row and bool(maint_row[0]):
            maintenance_prods.append(prod)
        else:
            live_prods.append(prod)

    # If every package in this panel is under maintenance, show only the
    # professional maintenance page. No package name, price or validity.
    if maintenance_prods and not live_prods:
        notify_id = int(maintenance_prods[0][0])
        maintenance_text = (
            f"🛠️ <b>{html.escape(str(header))}</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "🔧 <b>This product is currently under maintenance.</b>\n\n"
            "Jab bhi available hoga, aapko notification milega.\n\n"
            "👇 <b>Notify Me</b> dabao — available hote hi turant alert milega!"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="↩️ Back to Shop", callback_data="menu_shop", style="primary"),
                InlineKeyboardButton(text="🔔 Notify Me", callback_data=f"notify_panel_{notify_id}", style="success")
            ]
        ])
        try:
            await call.message.edit_text(maintenance_text, reply_markup=kb, parse_mode="HTML")
        except Exception as exc:
            # Do not turn Telegram's harmless "message is not modified" into
            # a visible error message for the customer.
            if "message is not modified" not in str(exc).lower():
                logger.warning("Maintenance screen render failed: %s", exc)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    text = f"{get_emoji('product_store')} <b><u>{html.escape(str(header)).upper()} PACKAGES</u></b>\n━━━━━━━━━━━━━━━━━━\n\n✨ <b>Select a package:</b>\n\n"

    # Only live packages are shown. A maintained package is completely hidden.
    for prod in live_prods:
        prod_id, package_name, normal_price, stock, reseller_price, validity, device_limit, api_enabled, pro_usd = prod
        final_price, display_usd, rate = get_product_price(safe_float(normal_price), safe_float(reseller_price), safe_float(pro_usd), tier, is_vip)
        if int(stock or 0) <= 0 and not bool(api_enabled):
            text += f"📦 <b>{html.escape(str(package_name))}</b> — <i>Out of Stock</i>\n\n"
            continue
        price_text = f"${display_usd:.4f} / {fmt_curr(final_price)}" if tier == "Pro Reseller" and display_usd is not None else fmt_curr(final_price)
        text += f"⏱ <b>{html.escape(str(package_name))}</b>\n💰 <b>{price_text}</b>\n📱 {html.escape(str(device_limit))}\n\n"
        kb.inline_keyboard.append([InlineKeyboardButton(
            text=f"🛒 Buy {package_name} — {price_text}",
            callback_data=f"confirm_buy_{prod_id}",
            icon_custom_emoji_id=get_emoji_icon("product_store"),
            style="success"
        )])

    # If live products exist but are all out of stock, keep the normal shop UI.
    kb.inline_keyboard.append([InlineKeyboardButton(text="BACK TO CATEGORIES", callback_data="menu_shop", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')
    except Exception as exc:
        if "message is not modified" not in str(exc).lower():
            logger.warning("Product list render failed: %s", exc)

async def buy_from_reseller_api(product_pid: str, duration: str, android_id: str = "") -> Dict[str, Any]:
    if CLIENT_MODE:
        return {"status": "error", "message": "Reseller API is disabled in standalone bot mode."}
    """Buy one license from the configured reseller API and return its JSON response."""
    api_url = get_setting("reseller_api_url", RESELLER_API_URL).strip()
    api_key = get_setting("reseller_api_key", RESELLER_API_KEY_DEFAULT).strip()
    master_key = get_setting("reseller_master_key", RESELLER_MASTER_KEY_DEFAULT).strip()
    if not api_key or not master_key:
        return {"status": "error", "message": "Reseller API credentials are not configured."}
    if not product_pid or not duration:
        return {"status": "error", "message": "Product PID or duration is missing."}

    data = {"api_key": api_key, "action": "buy", "product_id": product_pid, "duration": duration}
    if android_id:
        data["android_id"] = android_id
    headers = {"Content-Type": "application/x-www-form-urlencoded", "x-master-key": master_key}
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(api_url, data=data, headers=headers, allow_redirects=True) as resp:
                raw = await resp.text()
                if resp.status >= 400:
                    return {"status": "error", "message": f"API HTTP {resp.status}: {raw[:300]}"}
                try:
                    result = await resp.json(content_type=None)
                except Exception:
                    return {"status": "error", "message": raw[:500] or "Invalid API response."}
                return result if isinstance(result, dict) else {"status": "error", "message": "Unexpected API response."}
    except asyncio.TimeoutError:
        return {"status": "error", "message": "Reseller API request timed out."}
    except Exception as e:
        logger.exception("Reseller API request failed")
        return {"status": "error", "message": str(e)}

def extract_api_key(result: Dict[str, Any]) -> str:
    """Accept common response shapes without assuming one undocumented field name."""
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    for obj in (result, data):
        for key in ("key", "license_key", "license", "serial", "code", "product_key"):
            value = obj.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""

def api_purchase_success(result: Dict[str, Any]) -> bool:
    status = str(result.get("status", "")).lower()
    if status in {"success", "ok", "true", "1", "completed"}:
        return True
    data = result.get("data")
    if isinstance(data, dict) and str(data.get("status", "")).lower() in {"success", "ok", "true", "1", "completed"}:
        return True
    return bool(extract_api_key(result)) and status not in {"error", "failed", "failure"}

async def send_product_demo(call: CallbackQuery, demo_value: str) -> bool:
    value = (demo_value or '').strip()
    if not value or value.lower() in {'none', 'skip', 'no'}:
        return False
    try:
        if value.startswith('tg:'):
            await call.message.answer_video(value[3:], caption="🎥 <b>PRODUCT DEMO VIDEO</b>", parse_mode='HTML')
        else:
            await call.message.answer_video(value, caption="🎥 <b>PRODUCT DEMO VIDEO</b>", parse_mode='HTML')
        return True
    except Exception as exc:
        logger.warning("Product demo video send failed: %s", exc)
        await call.answer("❌ Demo video could not be sent right now.", show_alert=True)
        return False

@dp.callback_query(F.data.startswith("product_demo_"))
async def product_demo_video(call: CallbackQuery):
    await call.answer()
    try:
        prod_id = int(call.data.split("_", 2)[2])
    except Exception:
        return await call.answer("❌ Invalid product.", show_alert=True)
    row = db_query("SELECT demo_video FROM products WHERE id=? AND is_active=1", (prod_id,), fetchone=True)
    if not row or not row[0] or str(row[0]).lower() in {'none', 'skip', 'no'}:
        return await call.answer("🎥 Demo video is not available for this product.", show_alert=True)
    await send_product_demo(call, str(row[0]))

@dp.callback_query(F.data.startswith("confirm_buy_"))
async def confirm_buy(call: CallbackQuery):
    prod_id = int(call.data.split("_", 2)[2])
    prod = db_query(
        "SELECT name, price_inr, stock, apk_link, validity, device_limit, category, reseller_price, panel_name, api_enabled, api_product_id, api_duration, api_version, pro_reseller_price_usd, demo_video FROM products WHERE id=?",
        (prod_id,), fetchone=True
    )
    user = db_query("SELECT balance, is_reseller, total_saved, is_vip, is_pro_reseller FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    if not prod or not user:
        return await call.answer("❌ Product or user not found.", show_alert=True)
    maint = db_query("SELECT is_maintenance FROM products WHERE id=?", (prod_id,), fetchone=True)
    if maint and bool(maint[0]):
        return await call.message.edit_text(
            f"🛠️ <b>{prod[0]}</b>\n━━━━━━━━━━━━━━━━━━\n\n🔧 <b>This product abhi maintenance mein hai.</b>\n\n"
            f"Jab bhi available hoga, notify karenge.\n\n"
            f"👇 <b>Notify button dabao — available hote hi turant alert milega!</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Back to Shop", callback_data="menu_shop", style="primary"),
                 InlineKeyboardButton(text="🔔 Notify Me", callback_data=f"product_notify_{prod_id}", style="success")]
            ]), parse_mode="HTML"
        )
    normal_price = safe_float(prod[1]); reseller_price = safe_float(prod[7]); pro_usd = safe_float(prod[13])
    tier = "Pro Reseller" if bool(user[4]) else ("Reseller" if bool(user[1]) else "Regular User")
    final_price, final_usd, rate = get_product_price(normal_price, reseller_price, pro_usd, tier, bool(user[3]))
    balance = safe_float(user[0])
    tier_label = "💎 Pro Reseller" if tier == "Pro Reseller" else ("👑 Reseller" if tier == "Reseller" else "👤 Regular User")
    price_line = f"${final_usd:.4f} ≈ {fmt_curr(final_price)}" if final_usd is not None else fmt_curr(final_price)
    text = (f"🛒 <b>PRODUCT DETAILS</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>Product:</b> {prod[0]}\n"
            f"🏷 <b>Category:</b> {prod[6]}\n"
            f"📁 <b>Panel:</b> {prod[8] or 'Default'}\n"
            f"⏱ <b>Validity:</b> {prod[4]}\n"
            f"📱 <b>Device Limit:</b> {prod[5]}\n"
            f"👤 <b>Account:</b> {tier_label}\n"
            f"💰 <b>Price:</b> {price_line}\n"
            f"💳 <b>Your Balance:</b> {fmt_curr(balance)}\n")
    if tier == "Pro Reseller":
        text += f"💱 <b>USD Rate:</b> ₹{rate:.2f}/$\n"
    demo_value = str(prod[14] or "None")
    has_demo = demo_value.lower() not in {"", "none", "skip", "no"}
    if balance < final_price:
        deficit = round(final_price - balance, 2)
        text += (f"\n⚠️ <b>Insufficient Balance</b>\n"
                 f"➕ <b>Need to Add:</b> {fmt_curr(deficit)}\n\n"
                 f"Tap UPI below to generate an exact QR for this purchase.")
        rows = [[InlineKeyboardButton(text=f"💳 PAY UPI — {fmt_curr(deficit)}", callback_data=f"buy_topup_{prod_id}", style="success")]]
        if has_demo:
            rows.append([InlineKeyboardButton(text="🎥 Demo Video", callback_data=f"product_demo_{prod_id}", style="primary")])
        rows.append([InlineKeyboardButton(text="↩️ Back to Plans", callback_data="menu_shop", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
    else:
        rows = [[InlineKeyboardButton(text=(f"✅ BUY NOW — ${final_usd:.4f} / {fmt_curr(final_price)}" if final_usd is not None else f"✅ BUY NOW — {fmt_curr(final_price)}"), callback_data=f"buy_{prod_id}", style="success")]]
        if has_demo:
            rows.append([InlineKeyboardButton(text="🎥 Demo Video", callback_data=f"product_demo_{prod_id}", style="primary")])
        rows.append([InlineKeyboardButton(text="↩️ Back to Plans", callback_data="menu_shop", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("buy_topup_"))
async def buy_topup_exact(call: CallbackQuery):
    prod_id = int(call.data.split("_", 2)[2])
    prod = db_query("SELECT price_inr, reseller_price, pro_reseller_price_usd FROM products WHERE id=? AND is_active=1", (prod_id,), fetchone=True)
    user = db_query("SELECT balance, is_reseller, is_vip, is_pro_reseller FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    if not prod or not user:
        return await call.answer("❌ Product or user not found.", show_alert=True)
    normal_price = safe_float(prod[0]); reseller_price = safe_float(prod[1]); pro_usd = safe_float(prod[2])
    tier = "Pro Reseller" if bool(user[3]) else ("Reseller" if bool(user[1]) else "Regular")
    final_price, final_usd, rate = get_product_price(normal_price, reseller_price, pro_usd, tier, bool(user[2]))
    deficit = round(max(0.0, final_price - safe_float(user[0])), 2)
    if deficit <= 0:
        return await call.message.edit_text("✅ Your balance is now sufficient. Tap Confirm Buy again.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🛒 Confirm Buy", callback_data=f"confirm_buy_{prod_id}", style="success")]]), parse_mode="HTML")
    text = (f"💳 <b>QUICK TOP-UP FOR THIS PURCHASE</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"💰 Product Price: <b>{(f"${final_usd:.4f} ≈ {fmt_curr(final_price)}" if final_usd is not None else fmt_curr(final_price))}</b>\n"
            f"💵 Current Balance: <b>{fmt_curr(user[0])}</b>\n"
            f"➕ Required Top-Up: <b>{fmt_curr(deficit)}</b>\n\n"
            f"Scan the QR and pay exactly <b>{fmt_curr(deficit)}</b>.\nAfter payment, verification will credit the wallet and continue the selected purchase automatically when supported.")
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🇮🇳 UPI — {fmt_curr(deficit)}", callback_data=f"buy_upi_exact_{prod_id}", style="success")],
        [InlineKeyboardButton(text="↩️ Back", callback_data=f"confirm_buy_{prod_id}", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("buy_upi_exact_"))
async def buy_upi_exact(call: CallbackQuery):
    prod_id=int(call.data.split("_",3)[3])
    prod=db_query("SELECT price_inr,reseller_price,pro_reseller_price_usd FROM products WHERE id=? AND is_active=1",(prod_id,),fetchone=True)
    user=db_query("SELECT balance,is_reseller,is_vip,is_pro_reseller FROM users WHERE user_id=?",(call.from_user.id,),fetchone=True)
    if not prod or not user: return await call.answer("❌ Product or user not found.",show_alert=True)
    normal_price=safe_float(prod[0]); reseller_price=safe_float(prod[1]); pro_usd=safe_float(prod[2])
    tier="Pro Reseller" if bool(user[3]) else ("Reseller" if bool(user[1]) else "Regular")
    final_price, final_usd, rate=get_product_price(normal_price,reseller_price,pro_usd,tier,bool(user[2]))
    deficit=round(max(0.0,final_price-safe_float(user[0])),2)
    if deficit<=0: return await call.message.edit_text("✅ Balance is sufficient. Please confirm the purchase again.",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🛒 Confirm Buy",callback_data=f"confirm_buy_{prod_id}",style="success")]]),parse_mode="HTML")
    await call.message.edit_text(f"⏳ <b>Generating exact UPI QR for {fmt_curr(deficit)}...</b>",parse_mode="HTML")
    await generate_fampay_order(call.from_user.id, deficit, call.message, purpose="product_topup", product_id=prod_id)

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(call: CallbackQuery, state: FSMContext):
    prod_id = int(call.data.split("_")[1])
    prod = db_query(
        "SELECT name, price_inr, stock, apk_link, validity, device_limit, category, reseller_price, panel_name, api_enabled, api_product_id, api_duration, api_version, pro_reseller_price_usd, demo_video FROM products WHERE id=?",
        (prod_id,), fetchone=True
    )
    user = db_query("SELECT balance, is_reseller, total_saved, is_vip, is_pro_reseller FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    if not prod or not user:
        return await call.answer("❌ Critical Error: Item or user not found.", show_alert=True)
    maint = db_query("SELECT is_maintenance FROM products WHERE id=?", (prod_id,), fetchone=True)
    if maint and bool(maint[0]):
        return await call.message.edit_text(
            f"🛠️ <b>{prod[0]}</b>\n━━━━━━━━━━━━━━━━━━\n\n🔧 <b>This product abhi maintenance mein hai.</b>\n\n"
            f"Jab bhi available hoga, notify karenge.\n\n"
            f"👇 <b>Notify button dabao — available hote hi turant alert milega!</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Back to Shop", callback_data="menu_shop", style="primary"),
                 InlineKeyboardButton(text="🔔 Notify Me", callback_data=f"product_notify_{prod_id}", style="success")]
            ]), parse_mode="HTML"
        )

    normal_price = safe_float(prod[1])
    reseller_price = safe_float(prod[7])
    is_reseller = bool(user[1]); is_vip = bool(user[3]); is_pro = bool(user[4])
    tier = "Pro Reseller" if is_pro else ("Reseller" if is_reseller else "Regular")
    final_price, final_usd, rate = get_product_price(normal_price, reseller_price, safe_float(prod[13]), tier, is_vip)
    savings = normal_price - final_price
    if user[0] < final_price:
        deficit = round(final_price - safe_float(user[0]), 2)
        return await call.message.edit_text(
            f"⚠️ <b>Insufficient Balance</b>\n\n💰 Required: <b>{fmt_curr(final_price)}</b>\n💵 Available: <b>{fmt_curr(user[0])}</b>\n➕ Need to Add: <b>{fmt_curr(deficit)}</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"💳 UPI — ADD {fmt_curr(deficit)}", callback_data=f"buy_topup_{prod_id}", style="success")],[InlineKeyboardButton(text="↩️ Back", callback_data="menu_shop", style="danger")]]),
            parse_mode="HTML"
        )

    # API products are fulfilled remotely first. Balance is only deducted after a confirmed API success.
    delivered_key = ""
    if bool(prod[9]):
        api_version = (prod[12] or "V2").upper().strip()
        await call.message.edit_text("⏳ <b>Processing Auto Delivery...</b>\n<i>Connecting to reseller API securely.</i>", parse_mode="HTML")
        if api_version == "V1":
            await call.message.edit_text(
                "📱 <b>Device-Bound Product</b>\n\nPlease send your <b>Android ID</b> (required for V1 / Device-Bound products):",
                reply_markup=back_kb("menu_shop"), parse_mode="HTML"
            )
            # Keep the purchase pending until the Android ID arrives.
            await call.message.answer("Example: <code>0b9b969bc2e7997b</code>", parse_mode="HTML")
            # State is set here and the actual API call happens in the state handler below.
            # Store the product and price context; no money has been deducted.
            # A short-lived FSM is preferable to asking for an Android ID before the user clicks Buy.
            #
            await state.update_data(api_product_id=prod_id)
            await state.set_state(UserStates.wait_for_android_id)
            return
        result = await buy_from_reseller_api(str(prod[10]), str(prod[11]))
        if not api_purchase_success(result):
            return await call.message.edit_text(
                f"❌ <b>Auto Delivery Failed</b>\n\n{result.get('message', 'The reseller API did not confirm the purchase.')}\n\n<i>Your balance was not deducted.</i>",
                reply_markup=back_kb("menu_shop"), parse_mode="HTML"
            )
        delivered_key = extract_api_key(result)
        if not delivered_key:
            return await call.message.edit_text(
                "❌ <b>Auto Delivery Failed</b>\n\nThe API reported success but did not return a license key.\n\n<i>Your balance was not deducted.</i>",
                reply_markup=back_kb("menu_shop"), parse_mode="HTML"
            )
    else:
        if prod[2] <= 0:
            return await call.answer("⚠️ This product is out of stock.", show_alert=True)
        key_data = db_query("SELECT id, key_text FROM product_keys WHERE product_id=? AND is_used=0 LIMIT 1", (prod_id,), fetchone=True)
        if not key_data:
            return await call.answer("⚠️ This product is out of stock.", show_alert=True)
        delivered_key = key_data[1]

    # Charge only after delivery has been confirmed.
    db_query("UPDATE users SET balance=?, spent=spent+?, orders_count=orders_count+1, total_saved=total_saved+? WHERE user_id=?",
             (user[0] - final_price, final_price, savings, call.from_user.id))
    if not bool(prod[9]):
        db_query("UPDATE product_keys SET is_used=1 WHERE id=?", (key_data[0],))
        db_query("UPDATE products SET stock=stock-1 WHERE id=?", (prod_id,))

    product_full_name = f"{prod[6]} - {prod[8]} ({prod[0]})"
    db_query("INSERT INTO orders (user_id, product_name, price_paid, delivered_key, purchase_date) VALUES (?, ?, ?, ?, ?)",
             (call.from_user.id, product_full_name, final_price, delivered_key, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    # Credit the referrer with configurable team commission without changing the buyer price.
    ref_row = db_query("SELECT referred_by FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    if ref_row and ref_row[0]:
        commission_pct = safe_float(get_setting("referral_commission_percent", str(DEFAULT_REFERRAL_COMMISSION)), DEFAULT_REFERRAL_COMMISSION)
        commission = round(final_price * commission_pct / 100.0, 2)
        if commission > 0:
            db_query("UPDATE users SET balance=balance+?, team_earnings=team_earnings+? WHERE user_id=?", (commission, commission, ref_row[0]))
            log_activity(ref_row[0], "TEAM_COMMISSION", f"From user {call.from_user.id}: {commission}")
    log_activity(call.from_user.id, "PURCHASE_SUCCESS", f"Product: {product_full_name}, Paid: {final_price}, API: {bool(prod[9])}")
    await send_advanced_notification(call.from_user.id, "ORDER", final_price, product=product_full_name, key=delivered_key, gateway="Reseller API" if prod[9] else "Local Key Vault")

    msg = (f"✅ <b>PURCHASE SUCCESSFUL!</b>\n━━━━━━━━━━━━━━━━━━\n📦 <b>Panel:</b> {prod[6]}\n📁 <b>Panel Name:</b> {prod[8]}\n⏱ <b>Package:</b> {prod[0]}\n💰 <b>Amount Deducted:</b> {fmt_curr(final_price)}\n📱 <b>Device Limit:</b> {prod[5]}\n━━━━━━━━━━━━━━━━━━\n")
    if prod[3] and prod[3].startswith("http"):
        msg += f"📥 <b>APK Link:</b> <a href='{prod[3]}'>Click Here to Download</a>\n\n"
    msg += f"🔑 <b>Your Exclusive Key:</b>\n<code>{delivered_key}</code>\n\n<i>For any issues or guide, tap Support or contact: {ADMIN_CONTACT}</i>"
    await call.message.edit_text(msg, reply_markup=back_kb("menu_shop"), disable_web_page_preview=True, parse_mode="HTML")

@dp.message(UserStates.wait_for_android_id)
async def process_android_id_for_api(m: Message, state: FSMContext):
    android_id = (m.text or "").strip()
    if len(android_id) < 6 or len(android_id) > 64:
        return await m.answer("❌ Invalid Android ID. Please send the exact Android ID shown by your app.")
    data = await state.get_data()
    prod_id = data.get("api_product_id")
    if not prod_id:
        await state.clear()
        return await m.answer("❌ Purchase session expired. Please select the product again.", reply_markup=main_menu_kb(m.from_user.id))
    prod = db_query("SELECT name, price_inr, stock, apk_link, validity, device_limit, category, reseller_price, panel_name, api_enabled, api_product_id, api_duration, api_version, pro_reseller_price_usd FROM products WHERE id=?", (prod_id,), fetchone=True)
    user = db_query("SELECT balance, is_reseller, total_saved, is_vip FROM users WHERE user_id=?", (m.from_user.id,), fetchone=True)
    if not prod or not user or not prod[9]:
        await state.clear()
        return await m.answer("❌ Product is no longer available.", reply_markup=main_menu_kb(m.from_user.id))
    normal_price = safe_float(prod[1]); reseller_price = safe_float(prod[7])
    base_price = reseller_price if bool(user[1]) else normal_price
    final_price = base_price - (base_price * (VIP_DISCOUNT_PERCENTAGE / 100)) if bool(user[3]) else base_price
    if user[0] < final_price:
        await state.clear()
        return await m.answer(f"❌ {t(m.from_user.id, 'deficit')}: {fmt_curr(final_price)}.", reply_markup=main_menu_kb(m.from_user.id))
    await m.answer("⏳ <b>Processing Device-Bound Auto Delivery...</b>", parse_mode="HTML")
    result = await buy_from_reseller_api(str(prod[10]), str(prod[11]), android_id)
    if not api_purchase_success(result):
        await state.clear()
        return await m.answer(f"❌ <b>Auto Delivery Failed</b>\n\n{result.get('message', 'The reseller API did not confirm the purchase.')}\n\n<i>Your balance was not deducted.</i>", reply_markup=back_kb("menu_shop"), parse_mode="HTML")
    delivered_key = extract_api_key(result)
    if not delivered_key:
        await state.clear()
        return await m.answer("❌ API reported success but no license key was returned. Your balance was not deducted.", reply_markup=back_kb("menu_shop"), parse_mode="HTML")
    savings = normal_price - final_price
    db_query("UPDATE users SET balance=?, spent=spent+?, orders_count=orders_count+1, total_saved=total_saved+? WHERE user_id=?", (user[0]-final_price, final_price, savings, m.from_user.id))
    product_full_name = f"{prod[6]} - {prod[8]} ({prod[0]})"
    db_query("INSERT INTO orders (user_id, product_name, price_paid, delivered_key, purchase_date) VALUES (?, ?, ?, ?, ?)", (m.from_user.id, product_full_name, final_price, delivered_key, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    credit_referral_commission(m.from_user.id, final_price, f"purchase:{product_full_name}")
    log_activity(m.from_user.id, "PURCHASE_SUCCESS", f"Product: {product_full_name}, Paid: {final_price}, API: V1")
    await send_advanced_notification(m.from_user.id, "ORDER", final_price, product=product_full_name, key=delivered_key, gateway="Reseller API V1")
    msg = f"✅ <b>PURCHASE SUCCESSFUL!</b>\n━━━━━━━━━━━━━━━━━━\n📦 <b>Panel:</b> {prod[6]}\n📁 <b>Panel Name:</b> {prod[8]}\n⏱ <b>Package:</b> {prod[0]}\n💰 <b>Amount Deducted:</b> {fmt_curr(final_price)}\n📱 <b>Device Limit:</b> {prod[5]}\n━━━━━━━━━━━━━━━━━━\n🔑 <b>Your Exclusive Key:</b>\n<code>{delivered_key}</code>"
    if prod[3] and prod[3].startswith("http"): msg += f"\n\n📥 <b>APK Link:</b> <a href='{prod[3]}'>Click Here to Download</a>"
    await state.clear()
    await m.answer(msg, reply_markup=back_kb("menu_shop"), disable_web_page_preview=True, parse_mode="HTML")

# ==============================================================================
# 15. USER DASHBOARD, FILES, VIP, RESELLER, ORDERS, PROFILE
# ==============================================================================

@dp.callback_query(F.data == "menu_vip_dash")
async def vip_dashboard(call: CallbackQuery):
    await call.answer()
    u = db_query("SELECT balance, is_vip, vip_since FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    is_vip = bool(u[1])
    status_str = "🟢 Active (Lifetime)" if is_vip else "🔴 Not Subscribed"
    text = get_ui_text("vip_menu", vip_status=status_str)
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    if is_vip:
        text += f"\n📅 <b>Member Since:</b> {u[2]}\n\nEnjoy your permanent 15% discount!"
    else:
        text += f"\n\n💳 <b>Your Current Balance:</b> {fmt_curr(u[0])}\n"
        if u[0] >= VIP_PRICE_INR: kb.inline_keyboard.append([InlineKeyboardButton(text=f"✅ Purchase VIP for {fmt_curr(VIP_PRICE_INR)}", callback_data="execute_vip_upgrade", style="success")])
        else:
            kb.inline_keyboard.append([InlineKeyboardButton(text=f"❌ Need {fmt_curr(VIP_PRICE_INR)} to Upgrade", callback_data="ignore_stock_click", style="danger")])
            kb.inline_keyboard.append([InlineKeyboardButton(text="💳 Add Balance Now", callback_data="menu_add_balance", style="primary")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "execute_vip_upgrade")
async def execute_vip_upgrade(call: CallbackQuery):
    u = db_query("SELECT balance, is_vip FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    if u[1]: return await call.answer("⚠️ You are already a VIP Member!", show_alert=True)
    if u[0] < VIP_PRICE_INR: return await call.answer(f"❌ Your balance dropped below {VIP_PRICE_INR}.", show_alert=True)
    new_balance = u[0] - VIP_PRICE_INR
    now_date = datetime.now().strftime("%Y-%m-%d")
    db_query("UPDATE users SET balance=?, is_vip=1, vip_since=? WHERE user_id=?", (new_balance, now_date, call.from_user.id))
    log_activity(call.from_user.id, "UPGRADED_VIP")
    try: await bot.send_message(ADMIN_ID, f"🌟 <b>NEW VIP UPGRADE</b>\n👤 User ID: <code>{call.from_user.id}</code>", parse_mode='HTML')
    except: pass
    await call.answer("🎉 Upgrade Successful! You are now a VIP Member.", show_alert=True)
    await vip_dashboard(call)

@dp.callback_query(F.data == "menu_reseller_dash")
async def reseller_dashboard(call: CallbackQuery):
    u = db_query("SELECT balance, is_reseller, reseller_since, total_saved, is_pro_reseller FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    status_check = db_query("SELECT value FROM settings WHERE key='reseller_system_status'", fetchone=True)
    system_status = status_check[0] if status_check else "ON"
    setup_fee = safe_float(get_setting("reseller_setup_fee", "200.0"))
    min_balance = safe_float(get_setting("reseller_min_balance", "500.0"))
    if u[1]:
        tier_name = "💎 PRO RESELLER" if u[4] else "👑 RESELLER"
        rate = safe_float(get_setting("pro_usd_inr_rate","40.0"))
        text = (f"{get_emoji('shield_icon')} <b><u>— {tier_name} DASHBOARD —</u></b> {get_emoji('shield_icon')}\n\n🟢 <b>Status:</b> Active\n📅 <b>Since:</b> {u[2]}\n{get_emoji('money_icon')} <b>Total Saved:</b> {fmt_curr(u[3])}\n" + (f"\n💵 <b>Pro pricing:</b> USD\n💱 <b>Conversion:</b> ₹{rate:.2f}/$1\n" if u[4] else "") + "\n🎉 You are enjoying your account-tier prices on all products!")
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]])
        await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')
        return
    if system_status == "OFF": return await call.answer("⚠️ Wholesale / Reseller registrations are currently closed by Admin.", show_alert=True)
    text = (f"⚡ <b><u>— BECOME A RESELLER —</u></b> ⚡\n\nUpgrade your account to access wholesale <b>Reseller Prices</b>!\n\n📋 <b>Requirements to Upgrade:</b>\n1️⃣ Must have a minimum balance of <b>{fmt_curr(min_balance)}</b>.\n2️⃣ A one-time setup fee of <b>{fmt_curr(setup_fee)}</b> will be deducted.\n\n💳 <b>Your Current Balance:</b> {fmt_curr(u[0])}\n")
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    if u[0] >= min_balance: kb.inline_keyboard.append([InlineKeyboardButton(text=f"✅ Pay {fmt_curr(setup_fee)} & Become Reseller", callback_data="execute_reseller_upgrade", style="success")])
    else:
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"❌ Insufficient Balance (Need {fmt_curr(min_balance)})", callback_data="ignore_stock_click", style="danger")])
        kb.inline_keyboard.append([InlineKeyboardButton(text="💳 Add Balance", callback_data="menu_add_balance", style="primary")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "execute_reseller_upgrade")
async def execute_reseller_upgrade(call: CallbackQuery):
    setup_fee = safe_float(get_setting("reseller_setup_fee", "200.0"))
    min_balance = safe_float(get_setting("reseller_min_balance", "500.0"))
    u = db_query("SELECT balance, is_reseller, is_pro_reseller FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    if u[1]: return await call.answer("⚠️ You are already a Reseller!", show_alert=True)
    if u[0] < min_balance: return await call.answer(f"❌ Your balance dropped below {fmt_curr(min_balance)}. Please top up.", show_alert=True)
    new_balance = u[0] - setup_fee
    db_query("UPDATE users SET balance=?, is_reseller=1, reseller_since=?, account_type='Reseller' WHERE user_id=?", (new_balance, datetime.now().strftime("%Y-%m-%d"), call.from_user.id))
    log_activity(call.from_user.id, "UPGRADED_RESELLER")
    try: await bot.send_message(ADMIN_ID, f"👑 <b>NEW RESELLER UPGRADE</b>\n👤 User ID: <code>{call.from_user.id}</code>", parse_mode='HTML')
    except: pass
    await call.answer("🎉 Upgrade Successful! Welcome to the Reseller tier.", show_alert=True)
    await reseller_dashboard(call)

@dp.callback_query(F.data == "menu_orders")
async def my_orders(call: CallbackQuery):
    await call.answer()
    orders = db_query("SELECT product_name, delivered_key, purchase_date, price_paid FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10", (call.from_user.id,), fetchall=True)
    if not orders: return await call.message.edit_text("🧾 You haven't made any purchases yet. Your vault is empty.", reply_markup=back_kb(), parse_mode='HTML')
    text = "🧾 <b><u>— YOUR RECENT ORDERS (LAST 10) —</u></b> 🧾\n\n"
    for o in orders: text += f"📦 <b>{o[0]}</b> ({fmt_curr(o[3])})\n🔑 <code>{o[1]}</code>\n📅 <i>{o[2]}</i>\n━━━━━━━━━━━━━━━━\n"
    await call.message.edit_text(text, reply_markup=back_kb(), parse_mode='HTML')

@dp.callback_query(F.data == "menu_profile")
async def show_profile(call: CallbackQuery):
    """Profile screen. Team, purchase history and deposit history are separate screens."""
    await call.answer()
    u = db_query(
        "SELECT user_id, first_name, account_type, balance, orders_count, spent, "
        "joined_date, is_reseller, reseller_since, total_saved, is_vip, is_pro_reseller "
        "FROM users WHERE user_id=?",
        (call.from_user.id,),
        fetchone=True,
    )
    if not u:
        return await call.message.edit_text(
            "❌ Profile not found.",
            reply_markup=back_kb("back_main"),
            parse_mode="HTML",
        )

    acc_type_display = []
    if u[11]:
        acc_type_display.append("💎 Pro Reseller")
    elif u[7]:
        acc_type_display.append(f"{get_emoji('reseller')} Reseller")
    if u[10]:
        acc_type_display.append(f"{get_emoji('vip')} VIP")
    type_str = " | ".join(acc_type_display) if acc_type_display else f"{get_emoji('regular_user')} Regular User"

    text = (
        f"{get_emoji('grid_id')} <b><u>— YOUR SECURE PROFILE —</u></b> {get_emoji('grid_id')}\n\n"
        f"{get_emoji('grid_id')} <b>Grid ID:</b> <code>{u[0]}</code>\n"
        f"{get_emoji('name')} <b>Name:</b> {u[1]}\n"
        f"{get_emoji('account_level')} <b>Account Level:</b> {type_str}\n\n"
        f"{get_emoji('wallet_left')} <b>— Wallet —</b> {get_emoji('wallet_right')}\n"
        f"{get_emoji('wallet_left')} <b>Current Balance:</b> {fmt_curr(u[3])} {get_emoji('wallet_right')}\n\n"
        f"{get_emoji('global_stats')} <b>— Global Statistics —</b>\n"
        f"{get_emoji('total_orders')} <b>Total Orders:</b> {u[4]}\n"
        f"{get_emoji('total_spent')} <b>Total Spent:</b> {fmt_curr(u[5])}\n"
        f"{get_emoji('joined_grid')} <b>Joined:</b> {u[6]}\n"
    )
    if u[7]:
        text += (
            f"\n{get_emoji('shield_icon')} <b>— RESELLER METRICS —</b>\n"
            f"{get_emoji('money_icon')} <b>Total Saved:</b> {fmt_curr(u[9])}\n"
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🧾 My History", callback_data="menu_orders", style="primary"),
            InlineKeyboardButton(text="💳 My Deposit", callback_data="menu_deposits", style="primary"),
        ],
        [
            InlineKeyboardButton(text="🎟 Redeem Now", callback_data="redeem_coupon", style="success"),
        ],
        [
            InlineKeyboardButton(
                text="BACK",
                callback_data="back_main",
                icon_custom_emoji_id=get_emoji_icon("back"),
                style="danger",
            )
        ],
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data == "menu_orders")
async def my_orders(call: CallbackQuery):
    await call.answer()
    orders = db_query(
        "SELECT product_name, delivered_key, purchase_date, price_paid "
        "FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10",
        (call.from_user.id,),
        fetchall=True,
    ) or []
    if not orders:
        text = "🧾 <b>MY HISTORY</b>\n━━━━━━━━━━━━━━━━━━\n\n📭 You haven't made any purchases yet."
    else:
        text = "🧾 <b><u>— MY HISTORY —</u></b> 🧾\n\n"
        for product_name, delivered_key, purchase_date, price_paid in orders:
            text += (
                f"📦 <b>{product_name}</b>\n"
                f"💰 {fmt_curr(safe_float(price_paid))} • 📅 {purchase_date}\n"
                f"🔑 <code>{delivered_key}</code>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
            )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Back to Profile", callback_data="menu_profile", style="primary")],
        [InlineKeyboardButton(text="BACK TO MENU", callback_data="back_main", style="danger")],
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data == "menu_deposits")
async def my_deposits(call: CallbackQuery):
    await call.answer()
    deposits = db_query(
        "SELECT order_id, amount_inr, status, timestamp "
        "FROM transactions WHERE user_id=? AND purpose='wallet_deposit' "
        "ORDER BY timestamp DESC LIMIT 10",
        (call.from_user.id,),
        fetchall=True,
    ) or []

    text = "💳 <b><u>— MY DEPOSIT —</u></b> 💳\n\n"
    if deposits:
        for order_id, amount_inr, status, ts in deposits:
            status_text = (
                "✅ PAID" if status == "paid"
                else "❌ CANCELLED" if status == "cancelled"
                else "⏳ EXPIRED" if status == "expired"
                else f"⏳ {str(status).upper()}"
            )
            try:
                date_text = datetime.fromtimestamp(int(ts)).strftime("%d-%m-%Y %H:%M")
            except (TypeError, ValueError, OSError):
                date_text = str(ts)
            text += (
                f"💰 <b>{fmt_curr(safe_float(amount_inr))}</b> • {status_text}\n"
                f"🆔 <code>{order_id}</code> • 📅 {date_text}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
            )
    else:
        text += "📭 <i>No deposits yet.</i>"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Back to Profile", callback_data="menu_profile", style="primary")],
        [InlineKeyboardButton(text="💸 Add Balance", callback_data="menu_add_balance", style="success")],
        [InlineKeyboardButton(text="BACK TO MENU", callback_data="back_main", style="danger")],
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data == "redeem_coupon")
async def redeem_coupon_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_text(
        "🎟 <b>Coupon Redeem Now</b>\n\nEnter your coupon / promo code below:",
        reply_markup=back_kb("menu_profile"), parse_mode='HTML'
    )
    await state.set_state(UserStates.wait_for_redeem)

@dp.message(UserStates.wait_for_redeem)
async def process_redeem(m: Message, state: FSMContext):
    user_id = m.from_user.id
    code = normalize_coupon_code(m.text)
    result = redeem_coupon_record(db_query, user_id, code)
    if not result["ok"]:
        if result["reason"] == "already_redeemed":
            msg = "❌ <b>Already Redeemed</b>\nYou have already used this coupon."
        elif result["reason"] == "exhausted":
            msg = "❌ <b>Coupon Exhausted</b>\nThis code has reached its usage limit."
        else:
            msg = "❌ <b>Invalid or Expired Coupon</b>\nPlease check the code and try again."
        await m.answer(msg, reply_markup=main_menu_kb(user_id), parse_mode='HTML')
        await state.clear()
        return

    amount = result["amount"]
    log_activity(user_id, "PROMO_REDEEMED", f"Code: {code}, Amount: {amount}")
    await m.answer(
        f"🎉 <b>Coupon Redeemed Successfully!</b>\n\n💰 Added to wallet: <b>{fmt_curr(amount)}</b>",
        reply_markup=main_menu_kb(user_id), parse_mode='HTML'
    )
    try:
        user_info = db_query("SELECT first_name FROM users WHERE user_id=?", (user_id,), fetchone=True)
        uname = user_info[0] if user_info else "Unknown User"
        await bot.send_message(
            ADMIN_ID,
            f"🎟 <b>COUPON REDEEMED!</b>\n👤 User: {uname} (<code>{user_id}</code>)\n🔖 Code: <b>{code}</b>\n💵 Amount: {fmt_curr(amount)}",
            parse_mode='HTML'
        )
    except Exception:
        pass
    await state.clear()

@dp.callback_query(F.data == "menu_how_to")
async def tutorial_system(call: CallbackQuery):
    await call.answer()
    video_link_query = db_query("SELECT value FROM settings WHERE key='how_to_video'", fetchone=True)
    video_link = video_link_query[0] if video_link_query and video_link_query[0] != 'None' else None
    text = (f"{get_emoji('tutorial')} <b><u>— TUTORIALS & GUIDE —</u></b> {get_emoji('tutorial')}\n\n1️⃣ Add funds via <b>Add Balance</b>\n2️⃣ Navigate to <b>Product Store</b>\n3️⃣ Choose your desired Panel and Package validity.\n4️⃣ The Key and Installation APK link will be instantly provided.")
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    if video_link: kb.inline_keyboard.append([InlineKeyboardButton(text="Watch Full Video Tutorial", url=video_link, icon_custom_emoji_id=get_emoji_icon("tutorial"), style="primary")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "menu_support")
async def support_center(call: CallbackQuery):
    await call.answer()
    telegram_link = get_setting("support_telegram", "https://t.me/YourSupport")
    whatsapp_link = get_setting("support_whatsapp", "https://wa.me/YourNumber")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Contact on Telegram", url=telegram_link, icon_custom_emoji_id=get_emoji_icon("telegram"), style="primary")],
        [InlineKeyboardButton(text="Contact on WhatsApp", url=whatsapp_link, icon_custom_emoji_id=get_emoji_icon("whatsapp"), style="primary")],
        [InlineKeyboardButton(text="🎫 Open New Ticket", callback_data="open_ticket", style="primary"), InlineKeyboardButton(text="📋 My Open Tickets", callback_data="my_tickets", style="primary")], 
        [InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await call.message.edit_text(f"{get_emoji('telegram')}{get_emoji('whatsapp')} <b><u>— PREMIUM SUPPORT CENTER —</u></b>\n\nContact us via Telegram or WhatsApp for instant help, or open a support ticket for admin assistance.", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "my_tickets")
async def view_my_tickets(call: CallbackQuery):
    await call.answer()
    tickets = db_query("SELECT id, message, status, created_at FROM tickets WHERE user_id=? ORDER BY id DESC LIMIT 5", (call.from_user.id,), fetchall=True)
    if not tickets: return await call.message.edit_text("📋 You do not have any active or previous support tickets.", reply_markup=back_kb("menu_support"), parse_mode='HTML')
    text = "📋 <b><u>— Your Recent Tickets —</u></b> 📋\n\n"
    for t in tickets:
        status_icon = "🟢" if t[2] == 'Open' else "🔴"
        text += f"🎫 <b>Ticket #{t[0]}</b> | Status: {status_icon} <b>{t[2]}</b>\n📅 <i>{t[3]}</i>\n📝 <i>{t[1][:80]}...</i>\n\n"
    await call.message.edit_text(text, reply_markup=back_kb("menu_support"), parse_mode='HTML')

@dp.callback_query(F.data == "open_ticket")
async def open_ticket_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_text("📝 <b>Please type your issue/message below in detail:</b>", reply_markup=back_kb("menu_support"), parse_mode='HTML')
    await state.set_state(UserStates.wait_for_ticket)

@dp.message(UserStates.wait_for_ticket)
async def process_ticket(m: Message, state: FSMContext):
    db_query("INSERT INTO tickets (user_id, message, created_at) VALUES (?, ?, ?)", (m.from_user.id, m.text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    await m.answer("✅ <b>Ticket Submitted Successfully!</b> Admins will reply soon.", reply_markup=main_menu_kb(m.from_user.id), parse_mode='HTML')
    try: await bot.send_message(ADMIN_ID, f"🚨 <b>NEW SUPPORT TICKET</b>\nFrom: <code>{m.from_user.id}</code>\nMsg: {m.text}", parse_mode='HTML')
    except: pass
    log_activity(m.from_user.id, "OPENED_TICKET")
    await state.clear()

# ==============================================================================
# 18. ADMIN PANEL
# ==============================================================================
@dp.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    await message.answer("🛠️ <b>STORE CONTROL CENTER</b>\n━━━━━━━━━━━━━━━━━━\n<i>Secure Admin Access • Products • Bot Sales • Settings</i>", reply_markup=admin_kb(), parse_mode='HTML')

@dp.callback_query(F.data == "admin_panel_back")
async def back_to_admin(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await call.message.edit_text("🛠️ <b>STORE CONTROL CENTER</b>\n━━━━━━━━━━━━━━━━━━\n<i>Secure Admin Access • Products • Bot Sales • Settings</i>", reply_markup=admin_kb(), parse_mode='HTML')

@dp.callback_query(F.data == "admin_toggle_vip_sys")
async def toggle_vip_sys(call: CallbackQuery):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    res = db_query("SELECT value FROM settings WHERE key='vip_status'", fetchone=True)
    current = res[0] if res else 'OFF'
    new_status = 'ON' if current == 'OFF' else 'OFF'
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES ('vip_status', ?)", (new_status,))
    await call.message.edit_reply_markup(reply_markup=admin_kb())

@dp.callback_query(F.data == "admin_user_control_start")
async def admin_user_control_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Download Full User List", callback_data="admin_download_userlist", style="success")],
        [InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await call.message.edit_text("💻 <b>User Control Terminal</b>\n\n✏️ Enter the <b>User ID</b> or <b>@Username</b> you want to investigate or manage:\n\n👇 <b>OR</b> download the full user CSV format list:", reply_markup=kb, parse_mode='HTML')
    await state.set_state(AdminStates.manage_target_user)

@dp.callback_query(F.data == "admin_download_userlist")
async def admin_download_userlist(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    users = db_query("SELECT username, user_id, phone, balance, orders_count, is_vip, is_reseller FROM users", fetchall=True)
    if not users: return await call.answer("❌ No users found in the database.", show_alert=True)
    file_content = "FULL DATABASE DUMP\n" + "="*100 + "\n"
    for u in users:
        uname = u[0] if u[0] else "No_Username"
        uid = u[1]
        phone = u[2] if u[2] else "No_Phone"
        bal = u[3]
        orders = u[4]
        vip_status = "YES" if u[5] else "NO"
        res_status = "YES" if u[6] else "NO"
        file_content += f"UID: {uid} | UNAME: {uname} | PHONE: {phone} | BAL: ₹{bal:.2f} | BUY: {orders} | VIP: {vip_status} | RES: {res_status}\n"
    doc = BufferedInputFile(file_content.encode('utf-8'), filename=f"DB_{datetime.now().strftime('%Y%m%d')}.txt")
    await call.message.answer_document(document=doc, caption="📋 <b>Database export complete.</b>", parse_mode='HTML')
    await call.answer()

@dp.message(AdminStates.manage_target_user)
async def process_user_lookup(m: Message, state: FSMContext):
    target = m.text.strip()
    if target.startswith('@'): target = target[1:]
    loader_msg = await hacker_loading(m, "Querying User Database")
    user_q = db_query("SELECT user_id, first_name, username, balance, is_reseller, orders_count, spent, joined_date, is_banned, warnings, is_vip FROM users WHERE user_id=? OR username=? COLLATE NOCASE", (target, target), fetchone=True)
    if not user_q: return await loader_msg.edit_text("❌ Target not found in the grid. Check ID/Username syntax.", reply_markup=admin_back_kb(), parse_mode='HTML')
    u_id, u_name, u_user, bal, is_res, orders, spent, joined, is_banned, warnings, is_vip = user_q
    await state.update_data(target_u_id=u_id)
    status_emoji = "🔴 BANNED" if is_banned else "🟢 ACTIVE"
    tags = []
    if is_res: tags.append("👑 Reseller")
    if is_vip: tags.append("🌟 VIP")
    type_str = " | ".join(tags) if tags else "👤 Regular"
    text = (f"🛡 <b><u>USER CONTROL TERMINAL</u></b> 🛡\n━━━━━━━━━━━━━━━━━━\n📛 <b>Name:</b> {u_name} (@{u_user})\n🆔 <b>ID:</b> <code>{u_id}</code>\n📊 <b>Status:</b> {status_emoji}\n🔰 <b>Type:</b> {type_str}\n⚠️ <b>Warnings Issued:</b> {warnings}\n━━━━━━━━━━━━━━━━━━\n💰 <b>Wallet Balance:</b> {fmt_curr(bal)}\n📦 <b>Orders:</b> {orders} | 💸 <b>Total Spent:</b> {fmt_curr(spent)}\n📅 <b>Joined:</b> {joined}")
    ban_btn_text = "Unban ✅" if is_banned else "Ban 🚫"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Add Funds ➕", callback_data=f"usrctrl_add_{u_id}", style="success"), InlineKeyboardButton(text="Minus Funds ➖", callback_data=f"usrctrl_min_{u_id}", style="danger")],
        [InlineKeyboardButton(text=ban_btn_text, callback_data=f"usrctrl_ban_{u_id}", style="danger"), InlineKeyboardButton(text="Warn User ⚠️", callback_data=f"usrctrl_warn_{u_id}", style="danger")],
        [InlineKeyboardButton(text="Give VIP 🌟" if not is_vip else "Remove VIP 🚫", callback_data=f"usrctrl_vip_{u_id}", style="success")],
        [InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await loader_msg.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("usrctrl_"))
async def handle_user_actions(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    action = call.data.split("_")[1]
    u_id = int(call.data.split("_")[2])
    await state.update_data(target_u_id=u_id)
    if action == "ban":
        current_status = db_query("SELECT is_banned FROM users WHERE user_id=?", (u_id,), fetchone=True)[0]
        if current_status == 0:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Yes, Ban", callback_data=f"confirm_ban_{u_id}", style="danger"), InlineKeyboardButton(text="❌ Cancel", callback_data="admin_user_control_start", style="danger")]
            ])
            await call.message.edit_text(f"⚠️ Are you sure you want to <b>BAN</b> user <code>{u_id}</code>?", reply_markup=kb, parse_mode='HTML')
            await state.set_state(AdminStates.confirm_ban)
        else:
            db_query("UPDATE users SET is_banned=0 WHERE user_id=?", (u_id,))
            await call.answer("✅ User unbanned successfully!", show_alert=True)
            m = call.message; m.text = str(u_id); await process_user_lookup(m, state)
    elif action == "vip":
        current_status = db_query("SELECT is_vip FROM users WHERE user_id=?", (u_id,), fetchone=True)[0]
        if current_status == 1:
            db_query("UPDATE users SET is_vip=0 WHERE user_id=?", (u_id,))
            await call.answer("✅ VIP Removed!", show_alert=True)
        else:
            db_query("UPDATE users SET is_vip=1, vip_since=? WHERE user_id=?", (datetime.now().strftime("%Y-%m-%d"), u_id))
            await call.answer("✅ VIP Granted!", show_alert=True)
        m = call.message; m.text = str(u_id); await process_user_lookup(m, state)
    elif action == "add":
        await call.message.edit_text("💰 Enter the amount to <b>ADD</b> to this user's wallet:", reply_markup=admin_back_kb(), parse_mode='HTML')
        await state.set_state(AdminStates.wait_for_add_money)
    elif action == "min":
        await call.message.edit_text("💸 Enter the amount to <b>DEDUCT</b> from this user's wallet:", reply_markup=admin_back_kb(), parse_mode='HTML')
        await state.set_state(AdminStates.wait_for_minus_money)
    elif action == "warn":
        await call.message.edit_text("⚠️ Type the strict warning message you want to send directly to this user:", reply_markup=admin_back_kb(), parse_mode='HTML')
        await state.set_state(AdminStates.wait_for_warning)

@dp.callback_query(F.data.startswith("confirm_ban_"))
async def confirm_ban(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    u_id = int(call.data.split("_")[2])
    db_query("UPDATE users SET is_banned=1 WHERE user_id=?", (u_id,))
    await call.answer("🔴 User has been banned!", show_alert=True)
    await state.clear()
    m = call.message; m.text = str(u_id); await process_user_lookup(m, state)

@dp.message(AdminStates.wait_for_add_money)
async def exec_add_money(m: Message, state: FSMContext):
    try:
        amt = float(m.text)
        data = await state.get_data()
        u_id = data['target_u_id']
        db_query("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, u_id))
        await m.answer(f"✅ Successfully added {fmt_curr(amt)} to target <code>{u_id}</code>.", reply_markup=admin_kb(), parse_mode='HTML')
        try: await bot.send_message(u_id, f"💰 <b>Wallet Top-up!</b>\nAdmin has manually added {fmt_curr(amt)} to your wallet.", parse_mode='HTML')
        except: pass
        await state.clear()
    except ValueError: await m.answer("❌ Critical Error: Input must be a valid number.")

@dp.message(AdminStates.wait_for_minus_money)
async def exec_minus_money(m: Message, state: FSMContext):
    try:
        amt = float(m.text)
        data = await state.get_data()
        u_id = data['target_u_id']
        db_query("UPDATE users SET balance = balance - ? WHERE user_id=?", (amt, u_id))
        await m.answer(f"✅ Successfully deducted {fmt_curr(amt)} from target <code>{u_id}</code>.", reply_markup=admin_kb(), parse_mode='HTML')
        await state.clear()
    except ValueError: await m.answer("❌ Critical Error: Input must be a valid number.")

@dp.message(AdminStates.wait_for_warning)
async def exec_warn_user(m: Message, state: FSMContext):
    data = await state.get_data()
    u_id = data['target_u_id']
    warn_text = m.text
    db_query("UPDATE users SET warnings = warnings + 1 WHERE user_id=?", (u_id,))
    await m.answer(f"✅ Official warning dispatched to <code>{u_id}</code>.", reply_markup=admin_kb(), parse_mode='HTML')
    try: await bot.send_message(u_id, f"⚠️ <b>OFFICIAL WARNING FROM SYSTEM ADMIN:</b>\n\n{warn_text}\n\n<i>Subsequent infractions may lead to an automated grid ban.</i>", parse_mode='HTML')
    except: pass
    await state.clear()

# ==============================================================================
# 19. ADMIN STATISTICS
# ==============================================================================
@dp.callback_query(F.data == "admin_view_stats")
async def admin_dashboard_stats(call: CallbackQuery):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    t_users = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
    t_resellers = db_query("SELECT COUNT(*) FROM users WHERE is_reseller=1", fetchone=True)[0]
    t_vip = db_query("SELECT COUNT(*) FROM users WHERE is_vip=1", fetchone=True)[0]
    t_prods = db_query("SELECT COUNT(*) FROM products", fetchone=True)[0]
    t_keys = db_query("SELECT COUNT(*) FROM product_keys WHERE is_used=0", fetchone=True)[0]
    t_rev = db_query("SELECT SUM(spent) FROM users", fetchone=True)[0] or 0.0
    today_str = datetime.now().strftime("%Y-%m-%d")
    msg = (f"📊 <b><u>GRID INTELLIGENCE DASHBOARD</u></b> 📊\n━━━━━━━━━━━━━━━━━━\n👥 <b>Total Grid Users:</b> {t_users}\n👑 <b>Wholesale Resellers:</b> {t_resellers}\n🌟 <b>Elite VIP Members:</b> {t_vip}\n━━━━━━━━━━━━━━━━━━\n📦 <b>Active Products:</b> {t_prods}\n🔑 <b>Unused Keys in Vault:</b> {t_keys}\n💰 <b>Total Gross Revenue:</b> {fmt_curr(t_rev)}\n━━━━━━━━━━━━━━━━━━")
    await call.message.edit_text(msg, reply_markup=admin_back_kb(), parse_mode='HTML')

# ==============================================================================
# 20. ADMIN PRODUCT MANAGEMENT
# ==============================================================================
@dp.callback_query(F.data == "admin_add_prod")
async def add_prod_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    existing_categories = db_query("SELECT DISTINCT TRIM(category) FROM products WHERE category IS NOT NULL AND TRIM(category) != '' ORDER BY TRIM(category)", fetchall=True) or []
    for row in existing_categories:
        cat = str(row[0]).strip()
        kb.inline_keyboard.append([InlineKeyboardButton(text=cat, callback_data=f"addprod_cat_{selector_token(cat)}", icon_custom_emoji_id=get_emoji_icon("product_store"), style="primary")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="➕ Create New Category", callback_data="addprod_custom_cat", style="success")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="📦 No Category", callback_data="addprod_no_cat", style="primary")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="Cancel", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text("<b>Step 1:</b> Choose the <b>Category</b> for this product:", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "addprod_no_cat")
async def add_prod_no_category(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    await state.update_data(cat="")
    await call.message.edit_text("<b>Step 1:</b> No category selected.\n\nNow enter <b>PANEL NAME</b> (or type None):", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.add_prod_panel_name)

@dp.callback_query(F.data == "addprod_custom_cat")
async def add_prod_custom_category(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    await call.message.edit_text("<b>Step 1:</b> Enter your <b>CUSTOM CATEGORY NAME</b>:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.add_prod_custom_category)

@dp.message(AdminStates.add_prod_custom_category)
async def save_custom_category(m: Message, state: FSMContext):
    category = (m.text or '').strip()
    if len(category) < 2:
        return await m.answer("❌ Category name is too short. Try again.")
    await state.update_data(cat=category.upper())
    await m.answer(f"✅ Category saved: <b>{category.upper()}</b>\n\nNow enter <b>PANEL NAME</b>:", parse_mode='HTML')
    await state.set_state(AdminStates.add_prod_panel_name)

@dp.callback_query(F.data.startswith("addprod_cat_"))
async def add_prod_category_selected(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    token = call.data.split("addprod_cat_", 1)[1]
    category = resolve_category_token(token)
    if not category:
        return await call.answer("❌ Category button expired. Please reopen Add Product.", show_alert=True)
    await state.update_data(cat=category)
    await call.message.edit_text(f"<b>Step 2:</b> Enter <b>PANEL NAME</b>\n(e.g., 'MST PANEL', 'DRIP PANEL'):", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.add_prod_panel_name)

@dp.message(AdminStates.add_prod_panel_name)
async def add_prod_panel_name(m: Message, state: FSMContext):
    await state.update_data(panel_name=m.text)
    await m.answer("<b>Step 3:</b> Enter <b>PACKAGE DURATION/DATE NAME</b>\n(e.g., '7 Days', '1 Month'):", parse_mode='HTML')
    await state.set_state(AdminStates.add_prod_name)

@dp.message(AdminStates.add_prod_name)
async def add_prod_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text)
    await m.answer("⏳ Enter Time Validity String (e.g., '24 Hours'):", parse_mode='HTML')
    await state.set_state(AdminStates.add_prod_validity)

@dp.message(AdminStates.add_prod_validity)
async def add_prod_validity(m: Message, state: FSMContext):
    validity = (m.text or '').strip()
    if not validity:
        return await m.answer("❌ Validity cannot be empty. Please enter something like <code>30 Days</code>.", parse_mode='HTML')
    await state.update_data(validity=validity)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 1 Device", callback_data="addprod_device_1", style="primary"),
         InlineKeyboardButton(text="📱 2 Devices", callback_data="addprod_device_2", style="primary")],
        [InlineKeyboardButton(text="✏️ Custom Device Limit", callback_data="addprod_device_custom", style="success")],
        [InlineKeyboardButton(text="BACK", callback_data="admin_panel_back", style="danger")]
    ])
    await m.answer("📱 <b>Select Device Limit</b>", reply_markup=kb, parse_mode='HTML')
    await state.set_state(AdminStates.add_prod_device_limit)

@dp.callback_query(F.data.in_({"addprod_device_1", "addprod_device_2", "addprod_device_custom"}))
async def add_prod_device_choice(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID:
        return
    if call.data == "addprod_device_custom":
        await call.message.edit_text("📱 Enter Device Limit, e.g. <code>3 Devices</code> or <code>1 Device HWID</code>:", reply_markup=admin_back_kb(), parse_mode='HTML')
        await state.set_state(AdminStates.add_prod_device_limit)
        return
    limit = "1 Device" if call.data.endswith("_1") else "2 Devices"
    await state.update_data(device_limit=limit)
    await call.message.edit_text("💰 Enter standard <b>User Price</b> in Rupees (₹), e.g. <code>500</code>:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.add_prod_price)

@dp.message(AdminStates.add_prod_device_limit)
async def add_prod_device_limit(m: Message, state: FSMContext):
    value = (m.text or '').strip()
    if not value:
        return await m.answer("❌ Device limit cannot be empty. Choose 1 Device, 2 Devices, or enter a custom value.")
    await state.update_data(device_limit=value)
    await m.answer("💰 Enter standard <b>User Price</b> in Rupees (₹), e.g. <code>500</code>:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.add_prod_price)

@dp.message(AdminStates.add_prod_price)
async def add_prod_price(m: Message, state: FSMContext):
    try:
        await state.update_data(price=float(m.text))
        await m.answer("👑 Enter wholesale **Reseller Price** in Rupees (₹) (e.g., 300):", parse_mode='HTML')
        await state.set_state(AdminStates.add_prod_reseller_price)
    except ValueError: await m.answer("❌ Invalid input datatype! Must be numerical.")

@dp.message(AdminStates.add_prod_reseller_price)
async def add_prod_reseller_price(m: Message, state: FSMContext):
    try:
        await state.update_data(reseller_price=float(m.text))
        await m.answer("💵 Enter <b>Pro Reseller Price</b> in USD (e.g., 0.03):", parse_mode='HTML')
        await state.set_state(AdminStates.add_prod_pro_reseller_price)
    except ValueError: await m.answer("❌ Invalid input datatype! Must be numerical.")

@dp.message(AdminStates.add_prod_pro_reseller_price)
async def add_prod_pro_reseller_price(m: Message, state: FSMContext):
    try:
        await state.update_data(pro_reseller_price_usd=float(m.text))
        if CLIENT_MODE:
            await state.update_data(api_enabled=0, api_product_id="", api_duration="", api_version="V2")
            await m.answer("🔗 Enter direct APK/Payload Download Link (or type 'none' to omit):", parse_mode="HTML")
            await state.set_state(AdminStates.add_prod_apk)
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔌 Enable API Auto Delivery", callback_data="addprod_api_yes", style="success")],
            [InlineKeyboardButton(text="📦 Use Local Key Vault", callback_data="addprod_api_no", style="primary")],
            [InlineKeyboardButton(text="BACK", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
        ])
        await m.answer("⚙️ <b>Product Delivery Mode</b>\n\nChoose whether this product should use the reseller API for automatic key delivery:", reply_markup=kb, parse_mode='HTML')
        await state.set_state(AdminStates.add_prod_api_enabled)
    except ValueError: await m.answer("❌ Invalid input datatype! Must be numerical.")

@dp.callback_query(F.data == "addprod_api_yes")
async def add_prod_api_yes(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    await state.update_data(api_enabled=1)
    await call.message.edit_text("🔑 <b>API Step 1/3</b>\nEnter the exact <b>Product PID</b> from the API product table:", reply_markup=admin_back_kb(), parse_mode="HTML")
    await state.set_state(AdminStates.add_prod_api_pid)

@dp.callback_query(F.data == "addprod_api_no")
async def add_prod_api_no(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    await state.update_data(api_enabled=0, api_product_id="", api_duration="", api_version="V2")
    await call.message.edit_text("🔗 Enter direct APK/Payload Download Link (or type 'none' to omit):", reply_markup=admin_back_kb(), parse_mode="HTML")
    await state.set_state(AdminStates.add_prod_apk)

@dp.message(AdminStates.add_prod_api_pid)
async def add_prod_api_pid(m: Message, state: FSMContext):
    pid = m.text.strip()
    if not pid: return await m.answer("❌ PID cannot be empty.")
    await state.update_data(api_product_id=pid)
    await m.answer("⏱ <b>API Step 2/3</b>\nEnter the exact <b>Duration Name</b> used by the API (e.g. <code>1 Day</code>, <code>7 Days</code>, <code>3 Hours</code>):", parse_mode="HTML")
    await state.set_state(AdminStates.add_prod_api_duration)

@dp.message(AdminStates.add_prod_api_duration)
async def add_prod_api_duration(m: Message, state: FSMContext):
    duration = m.text.strip()
    if not duration: return await m.answer("❌ Duration cannot be empty.")
    await state.update_data(api_duration=duration)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="V1 — Device-Bound", callback_data="addprod_api_v1", style="primary")],
        [InlineKeyboardButton(text="V2 — Direct Key", callback_data="addprod_api_v2", style="success")],
        [InlineKeyboardButton(text="BACK", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await m.answer("📱 <b>API Step 3/3</b>\nSelect the API product type:", reply_markup=kb, parse_mode="HTML")
    await state.set_state(AdminStates.add_prod_api_version)

@dp.callback_query(F.data.in_({"addprod_api_v1", "addprod_api_v2"}))
async def add_prod_api_version(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    version = "V1" if call.data.endswith("v1") else "V2"
    await state.update_data(api_version=version)
    await call.message.edit_text("🔗 Enter direct APK/Payload Download Link (or type 'none' to omit):", reply_markup=admin_back_kb(), parse_mode="HTML")
    await state.set_state(AdminStates.add_prod_apk)

@dp.message(AdminStates.add_prod_apk)
async def add_prod_apk(m: Message, state: FSMContext):
    value = (m.text or '').strip()
    await state.update_data(apk="" if value.lower() == 'none' else value)
    await m.answer("📥 <b>Vault Injection Phase</b>\n\nPaste all the license <b>Keys</b> exactly as formatted (1 key per newline):", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.add_prod_keys)

@dp.message(AdminStates.add_prod_keys)
async def add_prod_keys(m: Message, state: FSMContext):
    keys = [k.strip() for k in (m.text or '').strip().split('\n') if k.strip()]
    await state.update_data(keys=keys)
    await m.answer(
        "🎥 <b>Demo Video (Optional — Final Step)</b>\n\n"
        "Send the <b>Telegram video</b> for this product, or type <code>none</code> to skip.\n\n"
        "If added, customers will get a <b>🎥 Demo Video</b> button and the video will open directly inside Telegram.",
        reply_markup=admin_back_kb(), parse_mode='HTML'
    )
    await state.set_state(AdminStates.add_prod_demo_video)

@dp.message(AdminStates.add_prod_demo_video)
async def add_prod_demo_video(m: Message, state: FSMContext):
    demo_value = "None"
    if m.video and m.video.file_id:
        demo_value = f"tg:{m.video.file_id}"
    else:
        value = (m.text or '').strip()
        if value.lower() not in {'', 'none', 'skip', 'no'}:
            demo_value = value

    await state.update_data(demo_video=demo_value)
    data = await state.get_data()
    keys = data.get('keys', [])
    stock = len(keys)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO products (category, panel_name, name, price_inr, reseller_price, pro_reseller_price_usd, stock, apk_link, validity, device_limit, api_enabled, api_product_id, api_duration, api_version, demo_video) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (data.get('cat',''), data['panel_name'], data['name'], data['price'], data['reseller_price'], data['pro_reseller_price_usd'], stock, data['apk'], data['validity'], data['device_limit'], data.get('api_enabled', 0), data.get('api_product_id', ''), data.get('api_duration', ''), data.get('api_version', 'V2'), demo_value))
        prod_id = c.lastrowid
        for k in keys:
            c.execute("INSERT INTO product_keys (product_id, key_text) VALUES (?, ?)", (prod_id, k))
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("Product creation failed")
        return await m.answer(f"❌ <b>Product creation failed.</b>\n\n<code>{str(exc)[:300]}</code>", reply_markup=admin_kb(), parse_mode='HTML')
    finally:
        conn.close()
    demo_status = "Added" if demo_value.lower() not in {'none', 'skip', 'no', ''} else "Not Added"
    await m.answer(
        f"✅ <b>Product Created Successfully!</b>\n━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 Product ID: <code>{prod_id}</code>\n"
        f"📂 Category: <b>{data.get('cat') or 'None'}</b>\n"
        f"🎮 Hack/Product Name: <b>{data['panel_name']}</b>\n"
        f"📦 Product: <b>{data['name']}</b>\n"
        f"💰 User Price: <b>{fmt_curr(data['price'])}</b>\n"
        f"👑 Reseller Price: <b>{fmt_curr(data['reseller_price'])}</b>\n"
        f"📱 Device Limit: <b>{data['device_limit']}</b>\n"
        f"⏳ Validity: <b>{data['validity']}</b>\n"
        f"🔒 Stock: <b>{stock}</b> keys\n"
        f"🎥 Demo Video: <b>{demo_status}</b>",
        reply_markup=admin_kb(), parse_mode='HTML'
    )
    await state.clear()

@dp.callback_query(F.data == "admin_manage_prods")
async def admin_manage_prods(call: CallbackQuery):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    prods = db_query("SELECT id, name, category, panel_name, stock, is_active, is_maintenance FROM products ORDER BY category, panel_name", fetchall=True)
    if not prods: return await call.message.edit_text("📦 Store Database is completely empty.", reply_markup=admin_back_kb(), parse_mode='HTML')
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for p in prods:
        status_dot = "🟢" if p[5] else "🔴"
        panel_name = p[3] if p[3] is not None else ""
        maint_tag = " 🛠️ MAINTENANCE" if p[6] else ""
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{status_dot} [{p[2]}] {panel_name} - {p[1]} (Stock: {p[4]}){maint_tag}", callback_data=f"admin_view_p_{p[0]}", style="primary")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text("📦 <b>Database Editor: Select Node to modify</b>", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("admin_view_p_"))
async def admin_view_product(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    try:
        p_id = int(call.data.split("_")[3])
        prod = db_query("SELECT * FROM products WHERE id=?", (p_id,), fetchone=True)
        if not prod: return await call.answer("❌ Architecture fault: Node lost!", show_alert=True)
        panel_name = prod[2] if prod[2] is not None else ""
        price_inr = safe_float(prod[4])
        reseller_price = safe_float(prod[5])
        pro_price_usd = safe_float(prod[6])
        text = (f"📦 <b><u>NODE DEEP DIVE DETAILS</u></b>\n━━━━━━━━━━━━━━━━━━\n"
                f"<b>ID:</b> <code>{prod[0]}</code>\n"
                f"<b>Panel Group:</b> {prod[1]}\n"
                f"<b>Panel Name:</b> {panel_name}\n"
                f"<b>Package Date/Time:</b> {prod[3]}\n"
                f"<b>Standard Price:</b> {fmt_curr(price_inr)}\n"
                f"👑 <b>Wholesale Price:</b> {fmt_curr(reseller_price)}\n"
                f"💵 <b>Pro Reseller USD:</b> ${pro_price_usd:.4f} (≈ {fmt_curr(pro_price_usd * safe_float(get_setting('pro_usd_inr_rate','40')))})\n"
                f"<b>Vault Stock:</b> {prod[7]}\n"
                f"<b>Payload Link:</b> {prod[8] if prod[8] else 'None'}\n"
                f"<b>Time Config:</b> {prod[9]}\n"
                f"<b>HWID Limit:</b> {prod[10]}\n"
                f"<b>Visibility:</b> {'Active' if prod[11] else 'Hidden'}\n"
                f"<b>Maintenance:</b> {'ON 🛠️' if prod[12] else 'OFF 🟢'}\n━━━━━━━━━━━━━━━━━━")
        toggle_btn_text = "Hide Product 👁‍🗨" if prod[11] else "Unhide Product 👁"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Edit Panel Group 🏷️", callback_data=f"edit_p_{p_id}_cat", style="primary"), InlineKeyboardButton(text="Edit Panel Name 🏷️", callback_data=f"edit_p_{p_id}_panel_name", style="primary")],
            [InlineKeyboardButton(text="Edit Package Name ✏️", callback_data=f"edit_p_{p_id}_name", style="primary")],
            [InlineKeyboardButton(text="Edit Price 💰", callback_data=f"edit_p_{p_id}_price", style="primary"), InlineKeyboardButton(text="Edit R-Price 👑", callback_data=f"edit_p_{p_id}_rprice", style="primary")],
            [InlineKeyboardButton(text="Edit Pro USD 💵", callback_data=f"edit_p_{p_id}_proprice", style="primary")],
            [InlineKeyboardButton(text="Edit Validity ⏳", callback_data=f"edit_p_{p_id}_validity", style="primary"), InlineKeyboardButton(text="Edit Device 📱", callback_data=f"edit_p_{p_id}_device", style="primary")],
            [InlineKeyboardButton(text="Edit APK Link 🔗", callback_data=f"edit_p_{p_id}_apk", style="primary"), InlineKeyboardButton(text="Add Keys ➕", callback_data=f"edit_p_{p_id}_keys", style="success")],
            [InlineKeyboardButton(text=("🟢 Maintenance OFF" if prod[12] else "🛠️ Maintenance ON"), callback_data=f"admin_product_maint_{p_id}", style="success" if prod[12] else "danger")],
            [InlineKeyboardButton(text="Delete Key 🗑", callback_data=f"delkey_p_{p_id}", style="danger"), InlineKeyboardButton(text=toggle_btn_text, callback_data=f"toggle_p_{p_id}", style="danger")],
            [InlineKeyboardButton(text="Nuke Full Node 🗑", callback_data=f"delete_p_{p_id}", style="danger"), InlineKeyboardButton(text="BACK", callback_data="admin_manage_prods", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
        ])
        await call.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error in admin_view_product: {e}")
        await call.message.edit_text(f"❌ Error loading product: {str(e)}", reply_markup=admin_back_kb(), parse_mode='HTML')

@dp.callback_query(F.data.startswith("admin_product_maint_"))
async def admin_product_maintenance(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Admin access only.", show_alert=True)
    try:
        p_id = int(call.data.rsplit("_", 1)[1])
    except Exception:
        return await call.answer("Invalid product.", show_alert=True)
    row = db_query("SELECT is_maintenance, name FROM products WHERE id=?", (p_id,), fetchone=True)
    if not row:
        return await call.answer("Product not found.", show_alert=True)
    new_status = 0 if int(row[0] or 0) else 1
    db_query("UPDATE products SET is_maintenance=? WHERE id=?", (new_status, p_id))
    await call.answer(
        "✅ Maintenance enabled successfully" if new_status else "✅ Maintenance disabled successfully",
        show_alert=True
    )
    if new_status == 0:
        await notify_product_available(p_id, row[1])
    # Refresh the admin product screen without exposing Telegram's harmless
    # "message is not modified" exception as a red error message.
    try:
        await admin_view_product(call)
    except Exception as exc:
        if "message is not modified" not in str(exc).lower():
            logger.exception("Unable to refresh admin product screen: %s", exc)


@dp.callback_query(F.data.startswith("toggle_p_"))
async def admin_toggle_product(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    p_id = int(call.data.split("_")[2])
    current = db_query("SELECT is_active FROM products WHERE id=?", (p_id,), fetchone=True)[0]
    new_val = 0 if current == 1 else 1
    db_query("UPDATE products SET is_active=? WHERE id=?", (new_val, p_id))
    await call.answer("Visibility updated successfully!", show_alert=True)
    await admin_view_product(call)

# ==============================================================================
# FIX: Edit product field – correctly handle different data types and multi-word fields
# ==============================================================================
@dp.callback_query(F.data.startswith("edit_p_"))
async def start_edit_product(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    # Use split with maxsplit=3 to keep field name intact (may contain underscores)
    parts = call.data.split("_", 3)
    if len(parts) < 4:
        return await call.answer("Invalid callback data.", show_alert=True)
    p_id = int(parts[2])
    field = parts[3]
    await state.update_data(edit_p_id=p_id, edit_field=field)
    if field == 'keys':
        await call.message.edit_text("📥 <b>Vault Injection</b>\nPaste the <b>NEW KEYS</b> to append to the stock (1 key per line):", reply_markup=admin_back_kb(), parse_mode='HTML')
        await state.set_state(AdminStates.wait_for_add_keys)
    else:
        field_name_map = {'cat': 'New Panel Group/Category Name', 'panel_name': 'New Panel Name', 'name': 'New Package/Date Name', 'price': 'New Standard Price in ₹', 'rprice': 'New Reseller Price in ₹', 'proprice': 'New Pro Reseller Price in USD', 'validity': 'New Time Validity String', 'device': 'New HWID Limit String', 'apk': 'New Payload Link (or type "none")'}
        await call.message.edit_text(f"✏️ Input the required data for: <b>{field_name_map.get(field, field)}</b>", reply_markup=admin_back_kb(), parse_mode='HTML')
        await state.set_state(AdminStates.wait_for_new_value)

@dp.message(AdminStates.wait_for_new_value)
async def process_edit_value(m: Message, state: FSMContext):
    data = await state.get_data()
    p_id = data['edit_p_id']; field = data['edit_field']; new_val = m.text.strip()
    
    # Convert price fields to float, others remain strings
    if field in ['price', 'rprice', 'proprice']:
        try:
            new_val = float(new_val)
        except ValueError:
            return await m.answer("❌ Invalid number format. Please enter a valid price (e.g., 500).")
    elif field == 'apk':
        new_val = "" if new_val.lower() == 'none' else new_val
    # For panel_name, cat, name, validity, device – keep as string
    
    db_col_map = {'cat': 'category', 'panel_name': 'panel_name', 'name': 'name', 'price': 'price_inr', 'rprice': 'reseller_price', 'proprice': 'pro_reseller_price_usd', 'validity': 'validity', 'device': 'device_limit', 'apk': 'apk_link'}
    db_query(f"UPDATE products SET {db_col_map[field]}=? WHERE id=?", (new_val, p_id))
    await m.answer("✅ <b>Node updated gracefully!</b>", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.message(AdminStates.wait_for_add_keys)
async def process_add_keys(m: Message, state: FSMContext):
    data = await state.get_data()
    p_id = data['edit_p_id']
    keys = [k.strip() for k in m.text.strip().split('\n') if k.strip()]
    if len(keys) == 0: return await m.answer("❌ Protocol breach: Zero valid keys found.", reply_markup=admin_kb(), parse_mode='HTML')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for k in keys: c.execute("INSERT INTO product_keys (product_id, key_text) VALUES (?, ?)", (p_id, k))
    c.execute("UPDATE products SET stock = stock + ? WHERE id=?", (len(keys), p_id))
    conn.commit(); conn.close()
    await m.answer(f"✅ <b>Vault Secure!</b> {len(keys)} new keys appended and encrypted.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data.startswith("delete_p_"))
async def admin_delete_product(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    p_id = int(call.data.split("_")[2])
    db_query("DELETE FROM products WHERE id=?", (p_id,))
    db_query("DELETE FROM product_keys WHERE product_id=?", (p_id,))
    await call.answer("☢️ Nuclear wipe successful! Node and vault deleted.", show_alert=True)
    await admin_manage_prods(call)

@dp.callback_query(F.data.startswith("delkey_p_"))
async def admin_delete_key_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    p_id = int(call.data.split("_")[2])
    await state.update_data(del_p_id=p_id)
    await call.message.edit_text("🗑 Send the <b>exact string match</b> of the key you wish to purge from the vault:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_delete_key)

@dp.message(AdminStates.wait_for_delete_key)
async def process_delete_key(m: Message, state: FSMContext):
    data = await state.get_data()
    p_id = data['del_p_id']
    key_to_delete = m.text.strip()
    key_data = db_query("SELECT id, is_used FROM product_keys WHERE product_id=? AND key_text=?", (p_id, key_to_delete), fetchone=True)
    if not key_data: return await m.answer("❌ Key not found. Check logs and try again.", reply_markup=admin_back_kb(), parse_mode='HTML')
    if key_data[1] == 1: return await m.answer("⚠️ Action Blocked: This key has already been dispatched to a user.", reply_markup=admin_back_kb(), parse_mode='HTML')
    db_query("DELETE FROM product_keys WHERE id=?", (key_data[0],))
    db_query("UPDATE products SET stock = stock - 1 WHERE id=?", (p_id,))
    await m.answer(f"✅ Key <code>{key_to_delete}</code> securely purged from vault.\n📦 Database indices updated.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

# ==============================================================================
# 21. ADMIN TICKETS, BROADCAST, COUPONS
# ==============================================================================
@dp.callback_query(F.data == "admin_view_tickets")
async def admin_view_tickets(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    tickets = db_query("SELECT id, user_id, message, created_at FROM tickets WHERE status='Open' LIMIT 1", fetchall=True)
    if not tickets: return await call.answer("✅ Zero pending issues. Grid is clean!", show_alert=True)
    t = tickets[0]
    text = (f"🎫 <b><u>ACTIVE TICKET #{t[0]}</u></b>\n👤 <b>Origin UID:</b> <code>{t[1]}</code>\n📅 <b>Timestamp:</b> {t[3]}\n\n📝 <b>Payload:</b>\n{t[2]}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Formulate Reply", callback_data=f"reply_ticket_{t[0]}_{t[1]}", style="primary")],
        [InlineKeyboardButton(text="❌ Force Close Ticket", callback_data=f"close_ticket_{t[0]}", style="danger")],
        [InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("close_ticket_"))
async def close_ticket(call: CallbackQuery):
    ticket_id = call.data.split("_")[2]
    db_query("UPDATE tickets SET status='Closed' WHERE id=?", (ticket_id,))
    await call.answer("✅ Status set to Closed.", show_alert=True)
    await admin_view_tickets(call) 

@dp.callback_query(F.data.startswith("reply_ticket_"))
async def reply_ticket_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = call.data.split("_")
    ticket_id, user_id = data[2], data[3]
    await state.update_data(ticket_id=ticket_id, user_id=user_id)
    await call.message.edit_text(f"💬 Formulating reply for node <code>{user_id}</code>.\n\nType your message payload:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.ticket_reply_msg)

@dp.message(AdminStates.ticket_reply_msg)
async def send_ticket_reply(m: Message, state: FSMContext):
    data = await state.get_data()
    try:
        await bot.send_message(data['user_id'], f"📞 <b>Admin Reply (Ref #{data['ticket_id']}):</b>\n\n{m.text}", parse_mode='HTML')
        db_query("UPDATE tickets SET status='Closed' WHERE id=?", (data['ticket_id'],))
        await m.answer("✅ Payload delivered and connection closed successfully.", reply_markup=admin_kb(), parse_mode='HTML')
    except Exception as e: await m.answer(f"❌ Transmission Error: {e}", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_broadcast_btn")
async def admin_broadcast_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    await call.message.edit_text("📢 <b>Mass Broadcast Protocol</b>\n\nSend the rich message payload you wish to transmit globally across the grid:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.broadcast_msg)

@dp.message(AdminStates.broadcast_msg)
async def admin_broadcast_send(message: Message, state: FSMContext):
    users = db_query("SELECT user_id FROM users", fetchall=True)
    sent, failed = 0, 0
    m = await message.answer("⏳ Broadcast protocol initiated... Do not interrupt.", parse_mode='HTML')
    for u in users:
        try:
            await message.send_copy(chat_id=u[0])
            sent += 1
        except Exception: failed += 1
        await asyncio.sleep(0.06) 
    await m.edit_text(f"✅ <b>Global Broadcast Complete!</b>\n\n🟢 Nodes reached: {sent}\n🔴 Nodes failed/blocked: {failed}", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_create_coupon")
async def admin_create_coupon_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    await call.message.edit_text("🎟 Enter a highly secure alphanumeric sequence for the Promo Code:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.add_coupon_code)

@dp.message(AdminStates.add_coupon_code)
async def admin_coupon_code(m: Message, state: FSMContext):
    code = normalize_coupon_code(m.text)
    if not code or not code.isalnum():
        return await m.answer("❌ Coupon code must contain letters/numbers only, e.g. <code>11</code>, <code>22</code>, <code>WELCOME10</code>.", parse_mode='HTML')
    await state.update_data(code=code)
    await m.answer("💰 Enter the monetary reward payload in <b>RUPEES (₹)</b>:", parse_mode='HTML')
    await state.set_state(AdminStates.add_coupon_amount)

@dp.message(AdminStates.add_coupon_amount)
async def admin_coupon_amount(m: Message, state: FSMContext):
    try:
        await state.update_data(amount=float(m.text)) 
        await m.answer("👥 Enter the exact maximum threshold uses for this code:", parse_mode='HTML')
        await state.set_state(AdminStates.add_coupon_uses)
    except ValueError: await m.answer("❌ Enter a valid numeric amount, e.g. <code>50</code> or <code>100.50</code>. Try again.", parse_mode='HTML')

@dp.message(AdminStates.add_coupon_uses)
async def admin_coupon_uses(m: Message, state: FSMContext):
    try:
        uses = int(m.text)
        data = await state.get_data()
        code = create_coupon_record(db_query, data['code'], data['amount'], uses)
        await m.answer(f"✅ <b>Coupon Created Successfully</b>\n\n🎟 Code: <code>{code}</code>\n💰 Reward: {fmt_curr(data['amount'])}\n👥 Maximum Uses: <b>{uses}</b>", reply_markup=admin_kb(), parse_mode='HTML')
        await state.clear()
    except ValueError as exc:
        await m.answer(f"❌ {exc}\n\nPlease enter a valid value and try again.", reply_markup=admin_back_kb(), parse_mode='HTML')

# ==============================================================================
# 22. ADMIN RESELLER & SPIN SETTINGS
# ==============================================================================
@dp.callback_query(F.data == "admin_reseller_menu")
async def admin_reseller_menu(call: CallbackQuery):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    status_check = db_query("SELECT value FROM settings WHERE key='reseller_system_status'", fetchone=True)
    sys_status = status_check[0] if status_check else "ON"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Grant Reseller Rights", callback_data="reseller_make", style="success"), InlineKeyboardButton(text="➖ Revoke Reseller", callback_data="reseller_remove", style="danger")],
        [InlineKeyboardButton(text="💎 Grant Pro Reseller", callback_data="pro_reseller_make", style="success"), InlineKeyboardButton(text="↩️ Revoke Pro", callback_data="pro_reseller_remove", style="danger")],
        [InlineKeyboardButton(text="📋 Audit Active Resellers", callback_data="reseller_view", style="primary")],
        [InlineKeyboardButton(text=f"{'🟢' if sys_status == 'ON' else '🔴'} Auto-Upgrade System: {sys_status}", callback_data="admin_toggle_reseller_sys", style="success" if sys_status == 'ON' else "danger")], 
        [InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await call.message.edit_text("👑 <b>Wholesale Reseller Protocols</b>\nSelect administrative action:", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "admin_toggle_reseller_sys")
async def toggle_reseller_sys(call: CallbackQuery):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    res = db_query("SELECT value FROM settings WHERE key='reseller_system_status'", fetchone=True)
    current = res[0] if res else 'ON'
    new_status = 'OFF' if current == 'ON' else 'ON'
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES ('reseller_system_status', ?)", (new_status,))
    await admin_reseller_menu(call)

@dp.callback_query(F.data.in_(["reseller_make", "reseller_remove", "pro_reseller_make", "pro_reseller_remove"]))
async def reseller_prompt_id(call: CallbackQuery, state: FSMContext):
    await call.answer()
    action = call.data
    await state.update_data(reseller_action=action)
    await call.message.edit_text("👤 Identify target node. Input <b>User ID</b> or <b>@username</b>:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.reseller_manage_id)

@dp.message(AdminStates.reseller_manage_id)
async def process_reseller_manage(m: Message, state: FSMContext):
    data = await state.get_data()
    target = m.text.strip()
    if target.startswith('@'): target = target[1:]
    user_q = db_query("SELECT user_id, first_name FROM users WHERE user_id=? OR username=? COLLATE NOCASE", (target, target), fetchone=True)
    if not user_q: return await m.answer("❌ Target completely ghosted. Not in database.", reply_markup=admin_back_kb(), parse_mode='HTML')
    u_id, u_name = user_q[0], user_q[1]
    if data['reseller_action'] == "pro_reseller_make":
        db_query("UPDATE users SET is_reseller=1, is_pro_reseller=1, reseller_since=?, account_type='Pro Reseller' WHERE user_id=?", (datetime.now().strftime("%Y-%m-%d"), u_id))
        await m.answer(f"💎 <b>{u_name}</b> (<code>{u_id}</code>) is now Pro Reseller.", reply_markup=admin_kb(), parse_mode='HTML')
    elif data['reseller_action'] == "pro_reseller_remove":
        db_query("UPDATE users SET is_pro_reseller=0, is_reseller=1, account_type='Reseller' WHERE user_id=?", (u_id,))
        await m.answer(f"↩️ Pro Reseller removed. <b>{u_name}</b> is now standard Reseller.", reply_markup=admin_kb(), parse_mode='HTML')
    elif data['reseller_action'] == "reseller_make":
        db_query("UPDATE users SET is_reseller=1, is_pro_reseller=0, reseller_since=?, account_type='Reseller' WHERE user_id=?", (datetime.now().strftime("%Y-%m-%d"), u_id))
        await m.answer(f"✅ Credentials upgraded. <b>{u_name}</b> (<code>{u_id}</code>) has reseller rights.", reply_markup=admin_kb(), parse_mode='HTML')
    else:
        db_query("UPDATE users SET is_reseller=0, is_pro_reseller=0, account_type='Regular' WHERE user_id=?", (u_id,))
        await m.answer(f"✅ Credentials revoked. <b>{u_name}</b> (<code>{u_id}</code>) is back to regular user.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "reseller_view")
async def reseller_view(call: CallbackQuery):
    await call.answer()
    resellers = db_query("SELECT user_id, first_name, username, is_pro_reseller FROM users WHERE is_reseller=1", fetchall=True)
    if not resellers: return await call.message.edit_text("📋 Zero active resellers found.", reply_markup=admin_back_kb(), parse_mode='HTML')
    text = "👑 <b><u>ACTIVE RESELLER AUDIT LOG</u></b> 👑\n━━━━━━━━━━━━━━━━━━\n"
    for r in resellers:
        uname = f"(@{r[2]})" if r[2] else ""
        tier = "💎 Pro Reseller" if r[3] else "👑 Reseller"
        text += f"{tier}\n👤 {r[1]} {uname}\n🆔 <code>{r[0]}</code>\n\n"
    await call.message.edit_text(text, reply_markup=admin_back_kb(), parse_mode='HTML')


def _client_bot_token_from_sale(db_path: str) -> Optional[str]:
    try:
        env_path = os.path.join(os.path.dirname(db_path), "bot.env")
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("BOT_TOKEN="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        return None
    return None

def _pid_running(pid: Optional[int]) -> bool:
    try:
        return bool(pid) and os.path.exists(f"/proc/{int(pid)}")
    except Exception:
        return False

def _sync_bot_sale_status(row):
    sale_id, db_path, pid, status, expires_at = row
    if status == "running" and expires_at and int(expires_at) <= int(time.time()):
        db_query("UPDATE bot_sales SET status='expired' WHERE id=?", (sale_id,))
        return "expired"
    if status == "running" and pid and not _pid_running(pid):
        db_query("UPDATE bot_sales SET status='stopped' WHERE id=?", (sale_id,))
        return "stopped"
    return status

@dp.callback_query(F.data == "admin_managed_bots")
async def admin_managed_bots(call: CallbackQuery):
    await call.answer()
    if CLIENT_MODE or call.from_user.id != ADMIN_ID: return
    sales = db_query("SELECT id, buyer_user_id, bot_username, bot_admin_id, price_paid, pid, status, created_at, duration_days, expires_at, db_path FROM bot_sales ORDER BY id DESC", fetchall=True) or []
    text = "🤖 <b>MANAGED BOTS</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    if not sales:
        text += "📭 <b>No purchased bots found.</b>"
    else:
        for r in sales:
            sid,buyer,uname,badmin,price,pid,status,created,days,exp,dbpath=r
            status=_sync_bot_sale_status((sid,dbpath,pid,status,exp))
            exp_txt = datetime.fromtimestamp(exp).strftime("%d %b %Y, %I:%M %p") if exp else "—"
            text += f"<b>#{sid} {uname or 'Unknown Bot'}</b>\n👤 Buyer: <code>{buyer}</code>\n🛡 Admin ID: <code>{badmin}</code>\n💰 {fmt_curr(price)} · ⏳ {days} days\n📌 Status: <b>{status.upper()}</b>\n⏰ Expires: {exp_txt}\n\n"
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Call Bot Admins", callback_data="admin_bot_broadcast", style="success")],
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="admin_managed_bots", style="primary")],
        [InlineKeyboardButton(text="⬅️ Back to Admin", callback_data="admin_panel_back", style="danger")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "admin_bot_broadcast")
async def admin_bot_broadcast_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if CLIENT_MODE or call.from_user.id != ADMIN_ID: return
    await state.set_state(AdminStates.bot_admin_broadcast_msg)
    await call.message.edit_text(
        "📨 <b>MESSAGE ALL PURCHASED BOTS</b>\n\nSend the message you want delivered through each active purchased bot to its configured Admin ID.\n\n<i>This sends only to the admin IDs saved for purchased bots; it does not broadcast to your main-store users.</i>",
        reply_markup=admin_back_kb(), parse_mode="HTML"
    )

@dp.message(AdminStates.bot_admin_broadcast_msg)
async def admin_bot_broadcast_send(message: Message, state: FSMContext):
    """Send an owner message through EVERY active purchased bot to that bot's Admin ID.

    The important distinction is that the purchased bot itself sends the message,
    not the main store bot. This makes the notification appear as coming from
    each purchased bot. The same Admin ID can own multiple purchased bots, so we
    intentionally do NOT deduplicate by Admin ID.
    """
    if CLIENT_MODE or message.from_user.id != ADMIN_ID:
        return

    sales = db_query(
        "SELECT id, bot_admin_id, db_path, status, expires_at, bot_username "
        "FROM bot_sales ORDER BY id DESC", fetchall=True
    ) or []

    sent = failed = 0
    progress = await message.answer(
        "⏳ <b>Calling all purchased Bot Admins...</b>", parse_mode="HTML"
    )

    for sid, badmin, dbpath, status, exp, bot_username in sales:
        if status != "running" or not badmin or (exp and int(exp) <= int(time.time())):
            continue

        token = _client_bot_token_from_sale(dbpath)
        if not token:
            failed += 1
            continue

        client_bot = None
        try:
            client_bot = Bot(token=token, default=DefaultBotProperties(parse_mode="HTML"))
            await _send_owner_message_through_client_bot(client_bot, badmin, message)
            sent += 1
        except Exception as exc:
            logger.warning("Failed to call purchased bot admin for %s (%s): %s", bot_username, badmin, exc)
            failed += 1
        finally:
            if client_bot:
                try:
                    await client_bot.session.close()
                except Exception:
                    pass
        await asyncio.sleep(0.08)

    await progress.edit_text(
        "✅ <b>BOT ADMIN CALL COMPLETE</b>\n\n"
        f"🟢 Sent through purchased bots: <b>{sent}</b>\n"
        f"🔴 Failed/Offline: <b>{failed}</b>",
        reply_markup=admin_kb(), parse_mode="HTML"
    )
    await state.clear()


async def _send_owner_message_through_client_bot(client_bot: Bot, chat_id: int, source: Message) -> None:
    """Relay common Telegram message types through a purchased bot.

    Text/captions are sent directly. For media, the main bot downloads the file
    and the purchased bot uploads it, because Telegram file IDs are bot-specific.
    """
    if source.text:
        await client_bot.send_message(chat_id=chat_id, text=source.text, entities=source.entities)
        return

    if source.photo:
        f = await bot.get_file(source.photo[-1].file_id)
        data = await bot.download_file(f.file_path)
        payload = BufferedInputFile(data.read(), filename="owner_photo.jpg")
        await client_bot.send_photo(chat_id=chat_id, photo=payload, caption=source.caption or "", caption_entities=source.caption_entities)
        return

    if source.video:
        f = await bot.get_file(source.video.file_id)
        data = await bot.download_file(f.file_path)
        payload = BufferedInputFile(data.read(), filename="owner_video.mp4")
        await client_bot.send_video(chat_id=chat_id, video=payload, caption=source.caption or "", caption_entities=source.caption_entities)
        return

    if source.document:
        f = await bot.get_file(source.document.file_id)
        data = await bot.download_file(f.file_path)
        filename = source.document.file_name or "owner_document"
        payload = BufferedInputFile(data.read(), filename=filename)
        await client_bot.send_document(chat_id=chat_id, document=payload, caption=source.caption or "", caption_entities=source.caption_entities)
        return

    if source.audio:
        f = await bot.get_file(source.audio.file_id)
        data = await bot.download_file(f.file_path)
        payload = BufferedInputFile(data.read(), filename="owner_audio.mp3")
        await client_bot.send_audio(chat_id=chat_id, audio=payload, caption=source.caption or "", caption_entities=source.caption_entities)
        return

    if source.voice:
        f = await bot.get_file(source.voice.file_id)
        data = await bot.download_file(f.file_path)
        payload = BufferedInputFile(data.read(), filename="owner_voice.ogg")
        await client_bot.send_voice(chat_id=chat_id, voice=payload, caption=source.caption or "", caption_entities=source.caption_entities)
        return

    if source.animation:
        f = await bot.get_file(source.animation.file_id)
        data = await bot.download_file(f.file_path)
        payload = BufferedInputFile(data.read(), filename="owner_animation.gif")
        await client_bot.send_animation(chat_id=chat_id, animation=payload, caption=source.caption or "", caption_entities=source.caption_entities)
        return

    if source.sticker:
        # Sticker file IDs cannot be reused across bots, so download and upload it.
        f = await bot.get_file(source.sticker.file_id)
        data = await bot.download_file(f.file_path)
        ext = ".webm" if source.sticker.is_video else (".tgs" if source.sticker.is_animated else ".webp")
        payload = BufferedInputFile(data.read(), filename="owner_sticker" + ext)
        await client_bot.send_sticker(chat_id=chat_id, sticker=payload)
        return

    # Fallback: send a readable notification if the message type is not supported.
    await client_bot.send_message(chat_id=chat_id, text="📢 Owner sent a message, but this message type could not be relayed.")

async def _save_panel_notification(call: CallbackQuery, product_id: int):
    base = db_query(
        "SELECT category, panel_name, is_active, is_maintenance FROM products WHERE id=?",
        (product_id,), fetchone=True
    )
    if not base or not int(base[2] or 0):
        return await call.answer("❌ This product is no longer available.", show_alert=True)
    if not int(base[3] or 0):
        return await call.answer("🟢 This product is available now. You can buy it.", show_alert=True)

    category = str(base[0] or "")
    panel_name = str(base[1] or "")
    rows = db_query(
        "SELECT id FROM products WHERE category LIKE ? AND panel_name LIKE ? AND is_active=1 AND is_maintenance=1",
        (category + "%", panel_name + "%"), fetchall=True
    ) or []
    if not rows:
        return await call.answer("🟢 This product is available now. You can buy it.", show_alert=True)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for row in rows:
        db_query(
            "INSERT OR IGNORE INTO product_maintenance_notifications (product_id,user_id,created_at) VALUES (?,?,?)",
            (int(row[0]), call.from_user.id, now)
        )

    await call.answer("🔔 Notification saved successfully!", show_alert=True)

@dp.callback_query(F.data.startswith("notify_panel_"))
async def notify_panel_me(call: CallbackQuery):
    try:
        product_id = int(call.data.rsplit("_", 1)[1])
        await _save_panel_notification(call, product_id)
    except Exception as exc:
        logger.exception("Panel Notify Me failed: %s", exc)
        try:
            await call.answer("⚠️ Could not save notification. Please try again.", show_alert=True)
        except Exception:
            pass

@dp.callback_query(F.data.startswith("panel_notify_"))
async def panel_notify_me(call: CallbackQuery):
    try:
        product_id = int(call.data.rsplit("_", 1)[1])
        await _save_panel_notification(call, product_id)
    except Exception as exc:
        logger.exception("Legacy Panel Notify Me failed: %s", exc)
        try:
            await call.answer("⚠️ Could not save notification. Please try again.", show_alert=True)
        except Exception:
            pass

@dp.callback_query(F.data.startswith("product_notify_"))
async def product_notify_me(call: CallbackQuery):
    await call.answer()
    try:
        product_id = int(call.data.rsplit("_", 1)[1])
    except Exception:
        return await call.answer("Invalid product.", show_alert=True)
    product = db_query("SELECT id,name,is_active,is_maintenance FROM products WHERE id=?", (product_id,), fetchone=True)
    if not product or not int(product[2] or 0):
        return await call.answer("This product is no longer available.", show_alert=True)
    if not int(product[3] or 0):
        return await call.answer("🟢 This product is available now. You can buy it.", show_alert=True)
    db_query(
        "INSERT OR IGNORE INTO product_maintenance_notifications (product_id,user_id,created_at) VALUES (?,?,?)",
        (product_id, call.from_user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    await call.answer("🔔 Done! Available hote hi aapko notification milega.", show_alert=True)


async def notify_product_available(product_id: int, product_name: str):
    subscribers = db_query(
        "SELECT user_id FROM product_maintenance_notifications WHERE product_id=?",
        (product_id,), fetchall=True
    ) or []
    if not subscribers:
        return
    text = (
        f"🟢 <b>{product_name}</b> ab available hai!\n\n"
        f"🛒 Product Store open karke ab ise purchase kar sakte hain."
    )
    for row in subscribers:
        try:
            await bot.send_message(
                chat_id=int(row[0]),
                text=text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🛒 Open Shop", callback_data="menu_shop", style="success")
                ]]),
                parse_mode="HTML"
            )
        except Exception as exc:
            logger.warning("Product maintenance notification failed for user %s: %s", row[0], exc)
    db_query("DELETE FROM product_maintenance_notifications WHERE product_id=?", (product_id,))


@dp.callback_query(F.data.startswith("botplan_notify_"))
async def botplan_notify_me(call: CallbackQuery):
    """Save Notify Me for a maintenance Bot Buy plan and give instant feedback."""
    # Answer the callback immediately so Telegram never leaves the button
    # spinning silently while the database/message update is being processed.
    try:
        await call.answer("🔔 Saving your notification request...", show_alert=True)
    except Exception:
        pass

    try:
        parts = call.data.rsplit("_", 1)
        plan_id = int(parts[1])
    except Exception:
        try:
            await call.answer("❌ Invalid product.", show_alert=True)
        except Exception:
            pass
        return

    try:
        plan = db_query(
            "SELECT id,name,is_active,is_maintenance FROM bot_plans WHERE id=?",
            (plan_id,), fetchone=True
        )
        if not plan or not int(plan[2] or 0):
            await call.message.answer("❌ This product is no longer available.")
            return

        if not int(plan[3] or 0):
            await call.message.answer(
                f"🟢 <b>{plan[1]}</b> is available now. You can purchase it from Bot Buy.",
                parse_mode="HTML"
            )
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db_query(
            "INSERT OR IGNORE INTO bot_plan_maintenance_notifications "
            "(plan_id,user_id,created_at) VALUES (?,?,?)",
            (plan_id, call.from_user.id, now)
        )

        # Replace the maintenance page with a clear saved state. No price or
        # purchase details are shown while the product remains in maintenance.
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="↩️ Back to Shop", callback_data="menu_bot_buy", style="primary")
        ]])
        saved_text = (
            f"🔔 <b>NOTIFICATION SAVED</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 <b>{plan[1]}</b>\n\n"
            f"🛠️ <b>This product is currently under maintenance.</b>\n\n"
            f"✅ <b>Your notification has been saved successfully.</b>\n\n"
            f"🔔 Maintenance खत्म होते ही आपको Telegram पर तुरंत message मिलेगा."
        )
        try:
            await call.message.edit_text(saved_text, reply_markup=kb, parse_mode="HTML")
        except Exception as exc:
            # Do not show Telegram's raw "message is not modified" error.
            # The subscription is already saved, so send a normal confirmation.
            logger.info("Bot Buy notify page refresh skipped: %s", exc)
            try:
                await call.message.answer(saved_text, reply_markup=kb, parse_mode="HTML")
            except Exception as send_exc:
                logger.warning("Unable to send Bot Buy notify confirmation: %s", send_exc)

    except Exception as exc:
        logger.exception("Bot Buy Notify Me failed for user %s: %s", call.from_user.id, exc)
        try:
            await call.message.answer(
                "⚠️ <b>Notification save failed.</b>\n\nPlease try the Notify Me button again.",
                parse_mode="HTML"
            )
        except Exception:
            pass


async def notify_bot_plan_available(plan_id: int, plan_name: str):
    """Notify every saved subscriber when a Bot Buy plan leaves maintenance.

    Successful deliveries are removed from the queue. Failed deliveries remain
    saved so a temporary Telegram/API failure does not lose the subscription.
    """
    subscribers = db_query(
        "SELECT user_id FROM bot_plan_maintenance_notifications WHERE plan_id=?",
        (plan_id,), fetchall=True
    ) or []
    if not subscribers:
        return

    text = (
        f"🟢 <b>{plan_name}</b> is now available!\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"🎉 Maintenance has ended.\n\n"
        f"🤖 You can now open <b>Bot Buy</b> and purchase this plan."
    )
    for row in subscribers:
        user_id = int(row[0])
        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🛒 Open Bot Buy", callback_data="menu_bot_buy", style="success")
                ]]),
                parse_mode="HTML"
            )
            db_query(
                "DELETE FROM bot_plan_maintenance_notifications WHERE plan_id=? AND user_id=?",
                (plan_id, user_id)
            )
        except Exception as exc:
            logger.warning("Bot plan maintenance notification failed for user %s: %s", user_id, exc)


@dp.callback_query(F.data == "admin_bot_plans")
async def admin_bot_plans(call: CallbackQuery):
    """Admin Bot Buy plan manager: price/details plus per-product maintenance."""
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Admin access only.", show_alert=True)
    await call.answer()
    plans = get_bot_plans(False)
    text = "🤖 <b>BOT BUY PLANS</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    if not plans:
        text += "📭 <b>No plans created yet.</b>\n\n"
    for pid, name, price, days, _plan_maintenance in plans:
        row = db_query("SELECT is_active,admin_panel_website_link,is_maintenance FROM bot_plans WHERE id=?", (pid,), fetchone=True)
        active = bool(row and row[0])
        panel = bool(row and row[1])
        maintenance = bool(row and row[2])
        status = "🟢" if active else "🔴"
        maint = "🛠️ MAINTENANCE" if maintenance else "🟢 LIVE"
        text += f"{status} <b>#{pid} {name}</b>\n"
        text += f"   💰 {fmt_curr(price)} · ⏳ {days} days · {maint}\n"
        text += f"   🌐 {'Panel attached' if panel else 'No panel link'}\n\n"
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"{status} #{pid} {name}", callback_data=f"admin_botplan_toggle_{pid}", style="success" if active else "danger"),
            InlineKeyboardButton(text=("🛠️ OFF" if maintenance else "🛠️ Maintenance"), callback_data=f"admin_botplan_maint_{pid}", style="danger" if not maintenance else "success"),
            InlineKeyboardButton(text="🗑", callback_data=f"admin_botplan_delete_{pid}", style="danger")
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="➕ Add Plan", callback_data="admin_botplan_add", style="success")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", style="danger")])
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "admin_botplan_add")
async def admin_botplan_add(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Admin access only.", show_alert=True)
    await call.answer()
    await state.clear()
    await state.set_state(AdminStates.bot_plan_name)
    await call.message.edit_text(
        "📦 <b>ADD BOT BUY PLAN — STEP 1/4</b>\n\n"
        "Enter <b>Plan Name / Capability</b>.\n"
        "Example: <code>Premium Panel Bot</code>",
        reply_markup=admin_back_kb(), parse_mode="HTML"
    )

@dp.message(AdminStates.bot_plan_name)
async def admin_botplan_name(message: Message, state: FSMContext):
    name = (message.text or '').strip()
    if len(name) < 2:
        return await message.answer("❌ Plan Name / Capability is too short.", parse_mode="HTML")
    await state.update_data(bot_plan_name_admin=name)
    await state.set_state(AdminStates.bot_plan_price)
    await message.answer(
        "💰 <b>STEP 2/4 — PRICE</b>\n\nEnter the selling price in Rupees.\nExample: <code>499</code>",
        reply_markup=admin_back_kb(), parse_mode="HTML"
    )

@dp.message(AdminStates.bot_plan_price)
async def admin_botplan_price(message: Message, state: FSMContext):
    try:
        price = float((message.text or '').strip())
    except ValueError:
        return await message.answer("❌ Enter a valid numeric price.", parse_mode="HTML")
    if price <= 0:
        return await message.answer("❌ Price must be greater than ₹0.", parse_mode="HTML")
    await state.update_data(bot_plan_price_admin=price)
    await state.set_state(AdminStates.bot_plan_days)
    await message.answer(
        "⏳ <b>STEP 3/4 — EXPIRE / VALIDITY</b>\n\nEnter validity in days.\nExample: <code>30</code>",
        reply_markup=admin_back_kb(), parse_mode="HTML"
    )

@dp.message(AdminStates.bot_plan_days)
async def admin_botplan_days(message: Message, state: FSMContext):
    try:
        days = int((message.text or '').strip())
    except ValueError:
        return await message.answer("❌ Enter whole number days only.", parse_mode="HTML")
    if days < 1:
        return await message.answer("❌ Validity must be at least 1 day.", parse_mode="HTML")
    await state.update_data(bot_plan_days_admin=days)
    await state.set_state(AdminStates.bot_plan_admin_panel_website_link)
    await message.answer(
        "🌐 <b>STEP 4/4 — ADMIN PANEL WEBSITE</b>\n\n"
        "Send the Admin Panel Website Link.\n"
        "Type <code>None</code> if there is no panel link.",
        reply_markup=admin_back_kb(), parse_mode="HTML"
    )

@dp.message(AdminStates.bot_plan_admin_panel_website_link)
async def admin_botplan_admin_panel_website_link(message: Message, state: FSMContext):
    value = (message.text or '').strip()
    if value.lower() == 'none':
        value = ''
    elif not value.startswith(('http://', 'https://')):
        return await message.answer("❌ Send a valid http/https website link or <code>None</code>.", parse_mode="HTML")
    await state.update_data(bot_plan_admin_panel_website_link_admin=value)
    data = await state.get_data()
    panel = value or 'Not added'
    preview = (
        "📋 <b>CONFIRM BOT BUY PLAN</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 <b>Plan / Capability:</b> {data.get('bot_plan_name_admin','')}\n"
        f"💰 <b>Price:</b> {fmt_curr(data.get('bot_plan_price_admin',0))}\n"
        f"⏳ <b>Expire:</b> {data.get('bot_plan_days_admin',0)} days\n"
        f"🌐 <b>Admin Panel:</b> {panel}\n\n"
        "Maintenance will be <b>OFF</b> by default. You can turn it ON/OFF from the plan screen.\n\n"
        "Press <b>Confirm & Add</b> to save this plan."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Confirm & Add", callback_data="admin_botplan_confirm", style="success")],
        [InlineKeyboardButton(text="✏️ Start Again", callback_data="admin_botplan_add", style="primary"),
         InlineKeyboardButton(text="❌ Cancel", callback_data="admin_bot_plans", style="danger")]
    ])
    await message.answer(preview, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)

@dp.callback_query(F.data == "admin_botplan_confirm")
async def admin_botplan_confirm(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Admin access only.", show_alert=True)
    data = await state.get_data()
    required = ('bot_plan_name_admin','bot_plan_price_admin','bot_plan_days_admin')
    if not all(k in data for k in required):
        await state.clear()
        return await call.answer("Plan session expired. Please add the plan again.", show_alert=True)
    db_query(
        "INSERT INTO bot_plans (name,price,duration_days,is_active,created_at,admin_panel_website_link,is_maintenance,setup_video) VALUES (?,?,?,?,?,?,?,?)",
        (data['bot_plan_name_admin'], data['bot_plan_price_admin'], data['bot_plan_days_admin'], 1,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         data.get('bot_plan_admin_panel_website_link_admin',''), 0, 'None')
    )
    await state.clear()
    await admin_bot_plans(call)

@dp.callback_query(F.data.startswith("admin_botplan_maint_"))
async def admin_botplan_maintenance(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("⛔ Admin access only.", show_alert=True)
    try:
        pid = int(call.data.rsplit('_', 1)[1])
    except Exception:
        return await call.answer("Invalid plan.", show_alert=True)
    row = db_query("SELECT is_maintenance,name FROM bot_plans WHERE id=?", (pid,), fetchone=True)
    if not row:
        return await call.answer("Plan not found.", show_alert=True)
    new_status = 0 if int(row[0] or 0) else 1
    db_query("UPDATE bot_plans SET is_maintenance=? WHERE id=?", (new_status, pid))
    await call.answer("🛠️ Maintenance ON" if new_status else "🟢 Maintenance OFF", show_alert=True)
    if new_status == 0:
        await notify_bot_plan_available(pid, row[1])
    await admin_bot_plans(call)

@dp.callback_query(F.data.startswith("admin_botplan_toggle_"))
async def admin_botplan_toggle(call: CallbackQuery):
    await call.answer()
    if CLIENT_MODE or call.from_user.id != ADMIN_ID: return
    pid=int(call.data.rsplit('_',1)[1]); row=db_query("SELECT is_active FROM bot_plans WHERE id=?",(pid,),fetchone=True)
    if not row: return await call.answer("Plan not found.", show_alert=True)
    db_query("UPDATE bot_plans SET is_active=? WHERE id=?", (0 if row[0] else 1, pid))
    await admin_bot_plans(call)

@dp.callback_query(F.data.startswith("admin_botplan_delete_"))
async def admin_botplan_delete(call: CallbackQuery):
    await call.answer()
    if CLIENT_MODE or call.from_user.id != ADMIN_ID: return
    pid=int(call.data.rsplit('_',1)[1]); db_query("DELETE FROM bot_plans WHERE id=?",(pid,))
    await admin_bot_plans(call)

@dp.callback_query(F.data == "admin_set_bot_sales_channel")
async def admin_set_bot_sales_channel(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if CLIENT_MODE or call.from_user.id != ADMIN_ID: return
    current = get_setting("bot_sales_channel_id", "") or "Not configured"
    await call.message.edit_text(
        f"📣 <b>BOT SALES PROOF CHANNEL</b>\n\nCurrent: <code>{current}</code>\n\nSend your Telegram Channel ID, for example <code>-1001234567890</code>.\n\nThe bot must be an <b>Administrator</b> in that channel.\nType <code>OFF</code> to disable purchase notifications.",
        reply_markup=admin_back_kb(), parse_mode="HTML"
    )
    await state.set_state(AdminStates.bot_sales_channel_id)

@dp.message(AdminStates.bot_sales_channel_id)
async def admin_save_bot_sales_channel(message: Message, state: FSMContext):
    if CLIENT_MODE or message.from_user.id != ADMIN_ID: return
    value = (message.text or '').strip()
    if value.lower() == 'off':
        value = ''
    elif not (value.lstrip('-').isdigit() or value.startswith('@')):
        return await message.answer("❌ Send a valid channel ID like <code>-1001234567890</code>, @channelusername, or OFF.", parse_mode="HTML")
    set_setting("bot_sales_channel_id", value)
    await state.clear()
    await message.answer("✅ <b>Bot Sales Proof Channel updated.</b>\n\nNew bot purchases will be posted there automatically.", reply_markup=admin_kb(), parse_mode="HTML")

async def notify_bot_sales_channel(buyer_user_id: int, bot_username: str, buyer_admin_id: int, price: float, duration_days: int, expires_at: int, plan_name: str = "Bot Plan"):
    channel_id = (get_setting("bot_sales_channel_id", "") or '').strip()
    if not channel_id or CLIENT_MODE:
        return
    try:
        buyer = db_query("SELECT first_name, username FROM users WHERE user_id=?", (buyer_user_id,), fetchone=True)
        name = buyer[0] if buyer and buyer[0] else "Unknown"
        username = f"@{buyer[1]}" if buyer and buyer[1] else "—"
        expiry = datetime.fromtimestamp(expires_at).strftime("%d %b %Y, %I:%M %p")
        text = ("🤖 <b>TELEGRAM BOT SALE PROOF</b>\n━━━━━━━━━━━━━━━━━━\n\n"
                f"👤 <b>Buyer:</b> {name} ({username})\n"
                f"🆔 <b>Buyer ID:</b> <code>{buyer_user_id}</code>\n"
                f"🤖 <b>Bot:</b> {bot_username}\n"
                f"📦 <b>Plan:</b> {plan_name}\n"
                f"💰 <b>Price Paid:</b> {fmt_curr(price)}\n"
                f"⏳ <b>Validity:</b> {duration_days} days\n"
                f"📅 <b>Expires:</b> {expiry}\n"
                f"👑 <b>Bot Admin ID:</b> <code>{buyer_admin_id}</code>\n\n"
                "✅ <b>Bot created and started successfully.</b>\n"
                "🔐 Bot token is hidden for security.")
        await bot.send_message(channel_id, text, parse_mode="HTML")
    except Exception as exc:
        logger.warning("Bot sales channel notification failed: %s", exc)

@dp.callback_query(F.data == "admin_set_bot_demo")
async def admin_set_bot_demo(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if CLIENT_MODE or call.from_user.id != ADMIN_ID: return
    current=get_setting("bot_buy_demo_video","None")
    await call.message.edit_text(f"🎥 <b>BOT SETUP DEMO VIDEO</b>\n\nCurrent: <code>{current}</code>\n\nSend a direct Telegram/YouTube video URL.\nType <code>None</code> to remove it.", reply_markup=admin_back_kb(), parse_mode="HTML")
    await state.set_state(AdminStates.bot_demo_video)

@dp.message(AdminStates.bot_demo_video)
async def admin_save_bot_demo(message: Message, state: FSMContext):
    value=(message.text or '').strip()
    if value.lower() == 'none': value='None'
    elif not (value.startswith('http://') or value.startswith('https://')):
        return await message.answer("❌ Please send a valid http/https video URL or None.")
    set_setting("bot_buy_demo_video", value)
    await state.clear(); await message.answer("✅ <b>Bot Setup Demo Video updated.</b>", reply_markup=admin_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "admin_toggle_bot_buy")
async def admin_toggle_bot_buy(call: CallbackQuery):
    await call.answer()
    if CLIENT_MODE or call.from_user.id != ADMIN_ID: return
    current = get_setting("bot_buy_status", "OFF"); new_status = "OFF" if current == "ON" else "ON"
    set_setting("bot_buy_status", new_status)
    await call.message.edit_reply_markup(reply_markup=admin_kb())

@dp.callback_query(F.data == "admin_set_bot_buy_price")
async def admin_set_bot_buy_price_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if CLIENT_MODE or call.from_user.id != ADMIN_ID: return
    await call.message.edit_text(f"💰 <b>BOT BUY PRICE</b>\n\nCurrent price: <b>{fmt_curr(bot_price())}</b>\n\nEnter the new selling price in Rupees:", reply_markup=admin_back_kb(), parse_mode="HTML")
    await state.set_state(AdminStates.bot_buy_price)

@dp.message(AdminStates.bot_buy_price)
async def admin_save_bot_buy_price(message: Message, state: FSMContext):
    if CLIENT_MODE or message.from_user.id != ADMIN_ID: return
    try:
        price = float((message.text or "").strip())
        if price <= 0: raise ValueError
    except ValueError:
        return await message.answer("❌ Enter a valid price greater than ₹0.", parse_mode="HTML")
    set_setting("bot_buy_price", f"{price:.2f}"); await state.clear()
    await message.answer(f"✅ Bot Buy price updated to <b>{fmt_curr(price)}</b>.", reply_markup=admin_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "admin_toggle_bot")
async def toggle_bot(call: CallbackQuery):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    res = db_query("SELECT value FROM settings WHERE key='bot_status'", fetchone=True)
    current = res[0] if res else 'ON'
    new_status = 'OFF' if current == 'ON' else 'ON'
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES ('bot_status', ?)", (new_status,))
    await call.message.edit_reply_markup(reply_markup=admin_kb())


@dp.callback_query(F.data == "admin_set_video")
async def admin_set_video_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    await call.message.edit_text("📹 Input direct streaming / YouTube Link for Tutorial system:\n<i>(Or type 'None' to clear registry):</i>", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_howto_video)

@dp.message(AdminStates.wait_for_howto_video)
async def exec_set_video(m: Message, state: FSMContext):
    link = m.text.strip()
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES ('how_to_video', ?)", (link,))
    await m.answer("✅ Routing complete. Video linked.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()


@dp.callback_query(F.data == "admin_edit_emojis")
async def admin_edit_emojis(call: CallbackQuery):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    rows = db_query("SELECT key, value FROM settings WHERE key LIKE 'emoji_%' ORDER BY key", fetchall=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for row in rows:
        key = row[0]
        slot = key.replace("emoji_", "")
        current_id = row[1] if row[1] else "Not set"
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{slot} (ID: {current_id})", callback_data=f"edit_emoji_{slot}", style="primary")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text("🎨 <b>Edit All Emojis</b>\nChoose an emoji slot to change its ID:", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("edit_emoji_"))
async def admin_edit_emoji_prompt(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    slot = call.data.split("edit_emoji_", 1)[1]
    await state.update_data(emoji_slot=slot)
    current = get_setting(f"emoji_{slot}", "Not set")
    await call.message.edit_text(f"✏️ Enter new emoji ID for <b>{slot}</b>:\nCurrent: {current}\n(Leave empty to reset to default)", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_emoji_slot)

@dp.message(AdminStates.wait_for_emoji_slot)
async def save_emoji_slot(m: Message, state: FSMContext):
    data = await state.get_data()
    slot = data['emoji_slot']
    new_id = m.text.strip()
    if new_id == "":
        db_query("DELETE FROM settings WHERE key=?", (f"emoji_{slot}",))
        await m.answer(f"✅ Reset emoji for '{slot}' to default.", reply_markup=admin_kb(), parse_mode='HTML')
    else:
        if not new_id.isdigit():
            await m.answer("❌ Invalid ID! Must be numeric.", reply_markup=admin_kb(), parse_mode='HTML')
            return
        set_setting(f"emoji_{slot}", new_id)
        await m.answer(f"✅ Emoji for '{slot}' updated to ID {new_id}.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_edit_ui_menu")
async def admin_edit_ui_menu(call: CallbackQuery):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Edit Start Menu Text", callback_data="edit_ui_start", style="primary")],
        [InlineKeyboardButton(text="Edit VIP Menu Text", callback_data="edit_ui_vip", style="primary")],
        [InlineKeyboardButton(text="Edit Add Balance Text", callback_data="edit_ui_add_balance", style="primary")],
        [InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await call.message.edit_text("✏️ <b>Edit User Interface Texts</b>\nSelect which text you want to modify:", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("edit_ui_"))
async def admin_edit_ui_prompt(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    ui_key = call.data.split("_")[2]
    await state.update_data(ui_key=ui_key)
    current_text = get_ui_text(ui_key)
    await call.message.edit_text(f"📝 Send the new text for <b>{ui_key.upper()}</b> menu.\n\nCurrent text:\n{current_text}", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.edit_ui_text)

@dp.message(AdminStates.edit_ui_text)
async def admin_save_ui_text(m: Message, state: FSMContext):
    data = await state.get_data()
    ui_key = data['ui_key']
    new_text = m.text
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f"ui_{ui_key}", new_text))
    await m.answer(f"✅ UI text <b>{ui_key}</b> updated successfully!", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_edit_reseller_price")
async def admin_edit_reseller_price_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    prods = db_query("SELECT id, name, category, panel_name, reseller_price FROM products ORDER BY category, panel_name", fetchall=True)
    if not prods: return await call.message.edit_text("No products to edit.", reply_markup=admin_back_kb(), parse_mode='HTML')
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for p in prods:
        panel_name = p[3] if p[3] is not None else ""
        r_price = safe_float(p[4])
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{p[2]} - {panel_name} - {p[1]} (₹{r_price:.2f})", callback_data=f"edit_reseller_{p[0]}", style="primary")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text("👑 <b>Edit Reseller Price per Product</b>\nSelect a product to change its wholesale price:", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("edit_reseller_"))
async def admin_edit_reseller_price_prompt(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    prod_id = int(call.data.split("_")[2])
    await state.update_data(edit_reseller_prod_id=prod_id)
    await call.message.edit_text("💰 Enter the new <b>Reseller Price</b> in Rupees (₹) for this product:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.edit_reseller_price)

@dp.message(AdminStates.edit_reseller_price)
async def admin_save_reseller_price(m: Message, state: FSMContext):
    try:
        new_price = float(m.text)
        data = await state.get_data()
        prod_id = data['edit_reseller_prod_id']
        db_query("UPDATE products SET reseller_price=? WHERE id=?", (new_price, prod_id))
        await m.answer(f"✅ Reseller price updated to {fmt_curr(new_price)} for product ID {prod_id}.", reply_markup=admin_kb(), parse_mode='HTML')
        await state.clear()
    except ValueError: await m.answer("❌ Invalid number. Please enter a valid price.")

@dp.callback_query(F.data == "admin_set_reseller_fee")
async def admin_set_reseller_fee(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    await call.message.edit_text("💰 Enter the new <b>Reseller Setup Fee</b> in Rupees (₹):\nCurrent: " + get_setting("reseller_setup_fee", "200.0"), reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_reseller_setup_fee)

@dp.message(AdminStates.wait_for_reseller_setup_fee)
async def admin_save_reseller_fee(m: Message, state: FSMContext):
    try:
        fee = float(m.text)
        set_setting("reseller_setup_fee", str(fee))
        await m.answer(f"✅ Reseller setup fee updated to {fmt_curr(fee)}.", reply_markup=admin_kb(), parse_mode='HTML')
        await state.clear()
    except ValueError: await m.answer("❌ Invalid number. Please enter a valid amount.")

@dp.callback_query(F.data == "admin_set_reseller_min")
async def admin_set_reseller_min(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    await call.message.edit_text("💳 Enter the new <b>Minimum Balance</b> required to become reseller (₹):\nCurrent: " + get_setting("reseller_min_balance", "500.0"), reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_reseller_min_balance)

@dp.message(AdminStates.wait_for_reseller_min_balance)
async def admin_save_reseller_min(m: Message, state: FSMContext):
    try:
        min_bal = float(m.text)
        set_setting("reseller_min_balance", str(min_bal))
        await m.answer(f"✅ Minimum reseller balance updated to {fmt_curr(min_bal)}.", reply_markup=admin_kb(), parse_mode='HTML')
        await state.clear()
    except ValueError: await m.answer("❌ Invalid number. Please enter a valid amount.")

@dp.callback_query(F.data == "admin_set_support_links")
async def admin_set_support_links(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📞 Set Telegram Link", callback_data="admin_set_telegram", style="primary")],
        [InlineKeyboardButton(text="📱 Set WhatsApp Link", callback_data="admin_set_whatsapp", style="primary")],
        [InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await call.message.edit_text("📌 <b>Support Contact Links</b>\nSet the URLs for Telegram and WhatsApp support:", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "admin_set_telegram")
async def admin_set_telegram(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    await call.message.edit_text("✈️ Enter the Telegram contact URL (e.g., https://t.me/YourSupport):", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_support_telegram)

@dp.message(AdminStates.wait_for_support_telegram)
async def save_telegram_link(m: Message, state: FSMContext):
    link = m.text.strip()
    set_setting("support_telegram", link)
    await m.answer("✅ Telegram support link updated!", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_set_whatsapp")
async def admin_set_whatsapp(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    await call.message.edit_text("📱 Enter the WhatsApp contact URL (e.g., https://wa.me/1234567890):", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_support_whatsapp)

@dp.message(AdminStates.wait_for_support_whatsapp)
async def save_whatsapp_link(m: Message, state: FSMContext):
    link = m.text.strip()
    set_setting("support_whatsapp", link)
    await m.answer("✅ WhatsApp support link updated!", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_set_category_emojis")
async def admin_set_category_emojis(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    categories = db_query("SELECT DISTINCT TRIM(category) FROM products WHERE category IS NOT NULL AND TRIM(category) != '' ORDER BY TRIM(category)", fetchall=True) or []
    for row in categories:
        cat = str(row[0]).strip()
        current = get_setting(f"cat_emoji_{cat}", "Not set")
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{cat} (ID: {current})", callback_data=f"set_cat_emoji_{cat}", style="primary")])
    if not categories:
        await call.message.edit_text("📭 No categories have been created yet.", reply_markup=admin_back_kb(), parse_mode='HTML')
        return
    kb.inline_keyboard.append([InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text("🎨 <b>Set Category Emojis</b>\nChoose a category to set its custom emoji ID:", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("set_cat_emoji_"))
async def admin_set_category_emoji_prompt(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    category = call.data.split("set_cat_emoji_", 1)[1]
    await state.update_data(cat_emoji_category=category)
    await call.message.edit_text(f"🎨 Enter the emoji ID for <b>{category}</b>:\n(Leave empty to reset to default)", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_category_emoji)

@dp.message(AdminStates.wait_for_category_emoji)
async def save_category_emoji(m: Message, state: FSMContext):
    data = await state.get_data()
    category = data['cat_emoji_category']
    emoji_id = m.text.strip()
    if emoji_id == "":
        db_query("DELETE FROM settings WHERE key=?", (f"cat_emoji_{category}",))
        await m.answer(f"✅ Reset emoji for {category} to default.", reply_markup=admin_kb(), parse_mode='HTML')
    else:
        if not emoji_id.isdigit():
            await m.answer("❌ Invalid ID! Must be numeric.", reply_markup=admin_kb(), parse_mode='HTML')
            return
        set_setting(f"cat_emoji_{category}", emoji_id)
        await m.answer(f"✅ Emoji set for {category} successfully!", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_set_panel_emojis")
async def admin_set_panel_emojis(call: CallbackQuery):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    panels = db_query("SELECT DISTINCT panel_name FROM products WHERE panel_name != '' ORDER BY panel_name", fetchall=True)
    if not panels:
        await call.message.edit_text("No panel names found in products.", reply_markup=admin_back_kb(), parse_mode='HTML')
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for p in panels:
        panel = p[0]
        current = get_setting(f"panel_emoji_{panel}", "Not set")
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{panel} (ID: {current})", callback_data=f"set_panel_emoji_{panel}", style="primary")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text("🖼 <b>Set Panel Emojis</b>\nChoose a panel name to set its custom emoji ID:", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("set_panel_emoji_"))
async def admin_set_panel_emoji_prompt(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    panel_name = call.data.split("set_panel_emoji_", 1)[1]
    await state.update_data(panel_emoji_name=panel_name)
    await call.message.edit_text(f"🎨 Enter the emoji ID for panel <b>{panel_name}</b>:\n(Leave empty to reset to default)", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_panel_emoji_id)

@dp.message(AdminStates.wait_for_panel_emoji_id)
async def save_panel_emoji(m: Message, state: FSMContext):
    data = await state.get_data()
    panel_name = data['panel_emoji_name']
    emoji_id = m.text.strip()
    if emoji_id == "":
        db_query("DELETE FROM settings WHERE key=?", (f"panel_emoji_{panel_name}",))
        await m.answer(f"✅ Reset emoji for panel '{panel_name}'.", reply_markup=admin_kb(), parse_mode='HTML')
    else:
        if not emoji_id.isdigit():
            await m.answer("❌ Invalid ID! Must be numeric.", reply_markup=admin_kb(), parse_mode='HTML')
            return
        set_setting(f"panel_emoji_{panel_name}", emoji_id)
        await m.answer(f"✅ Emoji set for panel '{panel_name}'!", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

# ==============================================================================
# ADMIN RESELLER API SETUP (3 STEPS)
# ==============================================================================
@dp.callback_query(F.data == "admin_setup_reseller_api")
async def setup_reseller_api_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if CLIENT_MODE: return await call.answer("Reseller API is disabled in standalone bot mode.", show_alert=True)
    if call.from_user.id != ADMIN_ID: return
    await call.message.edit_text(
        "🔐 <b>RESELLER API SETUP — STEP 1/3</b>\n\nEnter <b>API URL</b>:",
        reply_markup=admin_back_kb(), parse_mode='HTML'
    )
    await state.set_state(AdminStates.wait_for_reseller_api_url)

@dp.message(AdminStates.wait_for_reseller_api_url)
async def setup_reseller_api_url(m: Message, state: FSMContext):
    if m.text.strip().lower() == '/cancel':
        await state.clear(); return await m.answer("❌ Cancelled.", reply_markup=admin_kb())
    await state.update_data(reseller_api_url=m.text.strip())
    await m.answer("🔑 <b>RESELLER API SETUP — STEP 2/3</b>\n\nEnter <b>API KEY</b>:", parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_reseller_api_key)

@dp.message(AdminStates.wait_for_reseller_api_key)
async def setup_reseller_api_key(m: Message, state: FSMContext):
    if m.text.strip().lower() == '/cancel':
        await state.clear(); return await m.answer("❌ Cancelled.", reply_markup=admin_kb())
    await state.update_data(reseller_api_key=m.text.strip())
    await m.answer("🛡 <b>RESELLER API SETUP — STEP 3/3</b>\n\nEnter <b>X-Master-Key</b>:", parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_reseller_master_key)

@dp.message(AdminStates.wait_for_reseller_master_key)
async def setup_reseller_master_key(m: Message, state: FSMContext):
    if m.text.strip().lower() == '/cancel':
        await state.clear(); return await m.answer("❌ Cancelled.", reply_markup=admin_kb())
    data = await state.get_data()
    set_setting('reseller_api_url', data.get('reseller_api_url',''))
    set_setting('reseller_api_key', data.get('reseller_api_key',''))
    set_setting('reseller_master_key', m.text.strip())
    await m.answer("✅ <b>Reseller API configured.</b>\n\n1. API URL: saved\n2. API Key: saved\n3. X-Master-Key: saved", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_pro_pricing")
async def admin_pro_pricing(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    rate = safe_float(get_setting('pro_usd_inr_rate','40.0'))
    await call.message.edit_text(f"💵 <b>PRO RESELLER CALCULATOR</b>\n\nCurrent rate: <b>₹{rate:.2f} / $1</b>\nExample: <b>$0.03 = {fmt_curr(0.03*rate)}</b>\n\nEnter new USD → INR rate:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_pro_usd_rate)

@dp.message(AdminStates.wait_for_pro_usd_rate)
async def save_pro_usd_rate(m: Message, state: FSMContext):
    try:
        rate=float(m.text.strip())
        if rate<=0: raise ValueError
        set_setting('pro_usd_inr_rate', f'{rate:.6f}')
        await m.answer(f"✅ Pro Reseller rate saved: ₹{rate:.2f} / $1\n$0.03 = {fmt_curr(0.03*rate)}", reply_markup=admin_kb(), parse_mode='HTML')
        await state.clear()
    except ValueError:
        await m.answer('❌ Enter a valid positive number, e.g. 40')

# ==============================================================================
# 23. ADMIN FAMPAY SETUP
# ==============================================================================
@dp.callback_query(F.data == "admin_setup_fampay")
async def setup_fampay_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if CLIENT_MODE: return await call.answer("FamPay is disabled in standalone bot mode.", show_alert=True)
    if call.from_user.id != ADMIN_ID: return
    current_api = get_setting("fampay_api_key", "Not set")
    current_upi = get_setting("fampay_upi_id", "Not set")
    await call.message.edit_text(
        f"⚙️ <b>FAMPAY SECURITY DEPLOYMENT</b>\n\n"
        f"🔑 Current API Key: {current_api[:8] if current_api != 'Not set' else 'Not set'}... (hidden)\n"
        f"🏦 Current UPI ID: {current_upi}\n\n"
        f"Send new <b>FamPay API Key</b>:\n<i>(Type /cancel to abort)</i>",
        reply_markup=admin_back_kb(), parse_mode='HTML'
    )
    await state.set_state(AdminStates.wait_for_fampay_api)

@dp.message(AdminStates.wait_for_fampay_api)
async def setup_fampay_api(m: Message, state: FSMContext):
    if m.text == '/cancel':
        await state.clear()
        return await m.answer("Sequence killed.", reply_markup=admin_kb(), parse_mode='HTML')
    api_key = m.text.strip()
    set_setting("fampay_api_key", api_key)
    await m.answer("🔑 FamPay API Key saved!\n\nNow enter the <b>UPI ID</b> to receive payments (e.g., example@okhdfcbank):", parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_fampay_upi)

@dp.message(AdminStates.wait_for_fampay_upi)
async def setup_fampay_upi(m: Message, state: FSMContext):
    upi_id = m.text.strip()
    if '@' not in upi_id:
        return await m.answer("❌ Invalid UPI ID! Must contain '@'. Example: example@okhdfcbank", parse_mode='HTML')
    set_setting("fampay_upi_id", upi_id)
    await m.answer(f"✅ <b>FamPay Gateway configured successfully!</b>\n\n🏦 UPI ID: {upi_id}\n🔑 API Key: Saved\n\nGateway is now ready for payments.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

# ==============================================================================
# 24. ADMIN BINANCE SETUP
# ==============================================================================
@dp.callback_query(F.data == "admin_setup_binance")
async def setup_binance_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.from_user.id != ADMIN_ID: return
    await call.message.edit_text("🪙 <b>CRYPTO NODE INIT: Step 1/3</b>\nInput Master <b>Binance API Key</b>:\n<i>(Type /cancel to halt protocol)</i>", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_binance_api)

@dp.message(AdminStates.wait_for_binance_api)
async def setup_binance_api(m: Message, state: FSMContext):
    if m.text == '/cancel':
        await state.clear()
        return await m.answer("Sequence aborted.", reply_markup=admin_kb(), parse_mode='HTML')
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES ('binance_api', ?)", (m.text.strip(),))
    await m.answer("🪙 <b>CRYPTO NODE INIT: Step 2/3</b>\nNow inject the highly secure <b>Binance Secret Key</b>:", parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_binance_secret)

@dp.message(AdminStates.wait_for_binance_secret)
async def setup_binance_secret(m: Message, state: FSMContext):
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES ('binance_secret', ?)", (m.text.strip(),))
    await m.answer("🪙 <b>CRYPTO NODE INIT: Step 3/3</b>\nFinal variable: Set the public <b>USDT Deposit Address (TRC20/BEP20)</b>\nUsers will broadcast to this ledger:", parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_binance_address)

@dp.message(AdminStates.wait_for_binance_address)
async def setup_binance_address(m: Message, state: FSMContext):
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES ('binance_address', ?)", (m.text.strip(),))
    await m.answer("✅ <b>Blockchain node synchronized.</b> Crypto gateway is fully armed.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

# ==============================================================================
# GLOBAL CALLBACK FALLBACK
# ==============================================================================
@dp.callback_query()
async def unhandled_callback(call: CallbackQuery):
    logger.warning("Unhandled callback_data=%r from user=%s", call.data, call.from_user.id)
    await call.answer("⚠️ This button is no longer active. Please open the menu again.", show_alert=True)

# ==============================================================================
# 25. BOOTSTRAPPING & MAIN
# ==============================================================================
async def main() -> None:
    init_db()
    logger.info("Initializing DB structure...")
    migrate_categories()
    if not CLIENT_MODE:
        asyncio.create_task(auto_verify_task())
        asyncio.create_task(owner_bot_sales_monitor())
        logger.info("FamPay Auto-Verifier Daemon Running in Background.")
    else:
        logger.info("Standalone client bot mode: FamPay/Reseller API disabled.")
        asyncio.create_task(client_expiry_task())
    logger.info("🚀 CORE SYSTEM IS FULLY OPERATIONAL...")
    try:
        await dp.start_polling(bot)
    except Exception as err:
        logger.error(f"Critical System Failure in Polling: {err}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("System shutting down gracefully. Goodbye.")