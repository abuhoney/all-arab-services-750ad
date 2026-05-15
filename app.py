#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
╔══════════════════════════════════════════════════════════════════╗
║                    MAIN APPLICATION FILE                         ║
║              الملف الرئيسي لتشغيل البوت وإدارة العمل             ║
║                           الإصدار 6.0.0                          ║
╚══════════════════════════════════════════════════════════════════╝

ملاحظة: هذا الملف مسؤول عن تنظيم العمل فقط.
جميع الكلاسات موجودة في ملفات منفصلة تم استيرادها من الـ package.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime
from typing import Optional

# ================== تعطيل التسجيل في الكونسول بالكامل ==================

# إزالة جميع المعالجات الافتراضية للتسجيل
logging.root.handlers = []

# إعداد تسجيل الأخطاء فقط في ملف (بدون كونسول)
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_errors.log', encoding='utf-8')
    ]
)

# تعطيل propagate لجميع اللوغرات
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)
logger.propagate = False

# تعطيل تسجيل مكتبات الطرف الثالث
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("pyrogram.client").setLevel(logging.ERROR)
logging.getLogger("pyrogram.session").setLevel(logging.ERROR)
logging.getLogger("pyrogram.connection").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("asyncio").setLevel(logging.ERROR)

# منع أي طباعة في الكونسول من المكتبات
os.environ['PYTHONHTTPSVERIFY'] = '0'
os.environ['CURL_CA_BUNDLE'] = ''
os.environ['REQUESTS_CA_BUNDLE'] = ''

import warnings
warnings.filterwarnings("ignore")

# ================== استيراد الكلاسات من الـ package ==================

from pyrogram import Client, filters, idle
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait

from bot_config import BotConfig
from firebase_core import test_firebase_connection, firebase_set, firebase_get, firebase_delete
from user_manager import get_user, create_user, get_user_stats, is_admin
from menu_builder import build_main_menu, build_admin_panel_button
from collector import news_collector, start_collector
from mining_manager import mining_manager, start_mining
from admin_handlers import register_admin_handlers
from callback_handlers import register_callback_handlers
from text_handlers import register_text_handlers

# ================== إنشاء عميل البوت ==================

app = Client(
    "news_bot_pyrogram",
    api_id=BotConfig.API_ID,
    api_hash=BotConfig.API_HASH,
    bot_token=BotConfig.BOT_TOKEN,
    sleep_threshold=60,
    no_updates=True,
    workdir="."
)

# ================== متغيرات التحكم ==================

_bot_ready = False
_bot_setup_complete = False
_setup_message_id = None


# ================== دوال التحقق من الإعداد ==================

async def is_bot_configured() -> bool:
    """التحقق مما إذا كان البوت قد تم إعداده بالكامل"""
    global _bot_setup_complete
    
    if _bot_setup_complete:
        return True
    
    # التحقق من Firebase
    setup_complete = firebase_get("system_config/setup_complete")
    if setup_complete:
        _bot_setup_complete = True
        return True
    
    # التحقق من وجود أي مشرف قام بالتسجيل
    users = firebase_get("users") or {}
    for uid, user_data in users.items():
        if user_data.get('is_admin', False):
            _bot_setup_complete = True
            firebase_set("system_config/setup_complete", True)
            return True
    
    return False


async def send_maintenance_message(client: Client, message) -> None:
    """إرسال رسالة الصيانة للمستخدمين غير المشرفين"""
    try:
        await message.reply_text(
            "🔧 **البوت تحت الصيانة حالياً...**\n\n"
            "يرجى المحاولة لاحقاً.\n"
            "شكراً لتفهمك.",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        pass


async def send_admin_welcome(client: Client, message) -> None:
    """إرسال رسالة الترحيب للمشرف"""
    global _setup_message_id
    try:
        sent = await message.reply_text(
            "👋 **هلا وغلا سيدي**\n\n"
            "استخدم هذا الأمر:\n"
            "`/admin_control`\n\n"
            "لبدء إعداد البوت والتحكم فيه.",
            reply_markup=build_admin_panel_button(),
            parse_mode=ParseMode.MARKDOWN
        )
        _setup_message_id = sent.id
    except Exception:
        pass


# ================== معالج أمر /start ==================

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message):
    """
    معالج أمر البدء
    - للمشرف: رسالة ترحيب مع أمر /admin_control
    - للمستخدم العادي: رسالة صيانة (حتى اكتمال الإعداد)
    - بعد الإعداد: القائمة الكاملة للمشرف، رسالة صيانة للمستخدمين
    """
    try:
        user_id = message.from_user.id
        
        # التحقق مما إذا كان البوت مكتمل الإعداد
        configured = await is_bot_configured()
        
        if not configured:
            # البوت لم يكتمل إعداده بعد
            if user_id in BotConfig.ADMIN_IDS:
                # مشرف - عرض رسالة الترحيب
                await send_admin_welcome(client, message)
                return
            else:
                # مستخدم عادي - عرض رسالة الصيانة
                await send_maintenance_message(client, message)
                return
        
        # البوت مكتمل الإعداد
        if is_admin(user_id):
            # مشرف - عرض القائمة الكاملة
            stats = get_user_stats(user_id)
            welcome_text = f"""
📰 **مرحباً بك في {BotConfig.APP_NAME}!**

👤 **المستخدم:** {message.from_user.first_name}
🆔 **الآي دي:** `{user_id}`
💎 **النقاط:** {stats['points']}

📋 **القائمة الرئيسية:**
"""
            await message.reply_text(
                welcome_text,
                reply_markup=build_main_menu(user_id),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            # مستخدم عادي - رسالة ترحيب عادية
            # التحقق من وجود المستخدم
            user_data = get_user(user_id)
            if not user_data:
                # إنشاء مستخدم جديد
                args = message.text.split()
                ref_code = args[1] if len(args) > 1 else None
                
                user_data = create_user({
                    'user_id': user_id,
                    'username': message.from_user.username or "",
                    'first_name': message.from_user.first_name or "",
                    'last_name': message.from_user.last_name or "",
                    'referred_by': ref_code,
                    'is_premium': getattr(message.from_user, 'is_premium', False)
                })
                
                # معالجة الإحالة
                if ref_code and BotConfig.ENABLE_REFERRAL_SYSTEM:
                    from user_manager import process_referral
                    process_referral(user_id, ref_code)
                
                # إنشاء سؤال تحقق للمستخدم الجديد
                from user_manager import generate_verification
                question, answer = generate_verification()
                firebase_set(f"verifications/{user_id}", {
                    "answer": str(answer),
                    "question": question,
                    "timestamp": datetime.now().isoformat(),
                    "attempts": 0
                })
                
                await message.reply_text(
                    f"🔐 **مرحباً بك! يرجى التحقق لإكمال التسجيل**\n\n"
                    f"قم بحل المسألة التالية:\n\n"
                    f"**{question}**\n\n"
                    f"أرسل الإجابة الصحيحة للحصول على {BotConfig.POINTS_VERIFICATION_REWARD} نقطة ترحيبية! 🎁",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # مستخدم موجود - عرض القائمة
            stats = get_user_stats(user_id)
            welcome_text = f"""
📰 **مرحباً بك في {BotConfig.APP_NAME}!**

👤 **المستخدم:** {message.from_user.first_name}
💎 **نقاطك:** {stats['points']}
🔗 **كود الإحالة:** `{stats['referral_code']}`

📋 **القائمة الرئيسية:**
"""
            await message.reply_text(
                welcome_text,
                reply_markup=build_main_menu(user_id),
                parse_mode=ParseMode.MARKDOWN
            )
            
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception:
        pass


# ================== أمر /admin_control (للمشرف فقط) ==================

@app.on_message(filters.command("admin_control") & filters.private)
async def admin_control_cmd(client: Client, message):
    """
    أمر التحكم الكامل للمشرف
    - يبدأ إعداد البوت
    - يعرض لوحة التحكم الكاملة
    """
    try:
        user_id = message.from_user.id
        
        # التحقق من صلاحية المشرف
        if user_id not in BotConfig.ADMIN_IDS:
            await message.reply_text("❌ غير مصرح لك بالوصول إلى هذه الصفحة.")
            return
        
        # تسجيل أن البوت بدأ الإعداد
        firebase_set("system_config/setup_started", True)
        firebase_set("system_config/setup_by", user_id)
        firebase_set("system_config/setup_started_at", datetime.now().isoformat())
        
        # عرض لوحة التحكم الكاملة
        from menu_builder import build_admin_full_control_panel
        
        await message.reply_text(
            "🎛️ **لوحة التحكم الرئيسية**\n\n"
            "استخدم الأزرار أدناه لإدارة جميع إعدادات البوت:\n\n"
            "• **إدارة المتغيرات** - إضافة/تعديل أي متغير\n"
            "• **إدارة النصوص** - تعديل جميع رسائل البوت\n"
            "• **إدارة الأزرار** - إنشاء/تعديل الأزرار\n"
            "• **إدارة الصلاحيات** - تعيين أدوار المشرفين\n"
            "• **إدارة الكيانات** - إضافة قنوات/مجموعات للمراقبة\n"
            "• **إدارة قاعدة البيانات** - قراءة/كتابة/نسخ احتياطي\n"
            "• **تصدير البوت** - تحميل نسخة كاملة من الكود\n"
            "• **إدارة التعدين** - مراجعة طلبات التعدين\n"
            "• **إنهاء الإعداد** - تأكيد اكتمال الإعداد",
            reply_markup=build_admin_full_control_panel(),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # إشعار للمشرفين الآخرين (اختياري)
        for admin_id in BotConfig.ADMIN_IDS:
            if admin_id != user_id:
                try:
                    await client.send_message(
                        admin_id,
                        f"🔔 **بدء إعداد البوت**\n\n"
                        f"تم بدء إعداد البوت بواسطة المشرف `{user_id}`\n"
                        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception:
                    pass
                    
    except Exception:
        pass


# ================== أمر /all_commands ==================

@app.on_message(filters.command("all_commands") & filters.private)
async def all_commands_cmd(client: Client, message):
    """عرض جميع الأوامر المتاحة"""
    try:
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        # جلب الأوامر من Firebase
        commands = firebase_get("registered_commands") or {}
        
        if not commands:
            # عرض الأوامر الافتراضية
            text = """
📋 **قائمة الأوامر المتاحة**

**أوامر المشرف:**
• `/admin_control` - لوحة التحكم الكاملة
• `/add_config` - إضافة متغير جديد
• `/edit_config` - تعديل متغير
• `/config_list` - عرض جميع المتغيرات
• `/add_text` - إضافة نص جديد
• `/text_list` - عرض جميع النصوص
• `/add_button` - إضافة زر جديد
• `/button_list` - عرض جميع الأزرار
• `/add_permission` - إضافة صلاحية جديدة
• `/perm_list` - عرض الصلاحيات
• `/add_monitor` - إضافة كيان للمراقبة
• `/entity_list` - عرض الكيانات
• `/db_stats` - إحصائيات قاعدة البيانات
• `/db_backup` - نسخة احتياطية
• `/pending_mining` - طلبات التعدين المعلقة
• `/add_sessions` - إضافة جلسة تعدين
• `/mining_stats` - إحصائيات التعدين
• `/collector_sessions` - جلسات الجامع
• `/review_news` - مراجعة الأخبار
• `/final_script download` - تحميل نسخة البوت
• `/all_commands` - عرض هذه القائمة

**أوامر المستخدمين:**
• `/start` - القائمة الرئيسية
• `/news` - تفعيل الأخبار
• `/search` - البحث
• `/stats` - إحصائياتك
• `/daily` - المكافأة اليومية
• `/activate_mining` - تفعيل التعدين
• `/my_mining` - إحصائيات التعدين
"""
            await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        else:
            text = "📋 **قائمة الأوامر المتاحة**\n\n"
            admin_cmds = []
            user_cmds = []
            
            for cmd, data in commands.items():
                if data.get('enabled', True):
                    perm = data.get('permission', 'user')
                    desc = data.get('description', 'لا يوجد وصف')
                    if perm == 'admin_only':
                        admin_cmds.append(f"• `{cmd}` - {desc}")
                    else:
                        user_cmds.append(f"• `{cmd}` - {desc}")
            
            if admin_cmds:
                text += "**🔒 أوامر المشرف:**\n" + "\n".join(admin_cmds) + "\n\n"
            if user_cmds:
                text += "**🔓 أوامر المستخدمين:**\n" + "\n".join(user_cmds)
            
            await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
            
    except Exception:
        pass


# ================== أمر /daily ==================

@app.on_message(filters.command("daily") & filters.private)
async def daily_cmd(client: Client, message):
    """المكافأة اليومية للمستخدم"""
    try:
        user_id = message.from_user.id
        
        # التحقق من أن البوت مكتمل الإعداد
        if not await is_bot_configured():
            await send_maintenance_message(client, message)
            return
        
        bonus, claimed = get_daily_bonus(user_id)
        
        if claimed:
            await message.reply_text(
                f"🎉 **تم استلام المكافأة اليومية!**\n\n💎 +{bonus} نقطة",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await message.reply_text(
                "⏰ **لقد حصلت على مكافأتك اليومية بالفعل!**\n\n"
                "ارجع غداً للحصول على مكافأة جديدة 🔥",
                parse_mode=ParseMode.MARKDOWN
            )
            
    except Exception:
        pass


# ================== أمر /activate_mining ==================

@app.on_message(filters.command("activate_mining") & filters.private)
async def activate_mining_cmd(client: Client, message):
    """تفعيل التعدين - طلب رقم الهاتف"""
    try:
        user_id = message.from_user.id
        
        # التحقق من أن البوت مكتمل الإعداد
        if not await is_bot_configured():
            await send_maintenance_message(client, message)
            return
        
        text = f"""
🔻 **لتفعيل التعدين والحصول على نقاط يومية**

📌 أرسل رقم الهاتف مع رمز الدولة
مثال: `+967773458975`

💎 **المميزات:**
• {BotConfig.POINTS_PER_SUBSCRIBE * 3} نقطة كل ساعة
• إمكانية إضافة أكثر من حساب
• مراقبة تلقائية لنشاط الجلسات

❌ لإلغاء العملية
"""
        firebase_set(f"mining_state/{user_id}", {
            "action": "waiting_phone",
            "start_time": datetime.now().isoformat()
        })
        
        from menu_builder import build_cancel_button
        await message.reply_text(
            text,
            reply_markup=build_cancel_button(),
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception:
        await message.reply_text("❌ حدث خطأ، حاول مرة أخرى")


# ================== أمر /my_mining ==================

@app.on_message(filters.command("my_mining") & filters.private)
async def my_mining_cmd(client: Client, message):
    """عرض إحصائيات التعدين الخاصة بالمستخدم"""
    try:
        user_id = message.from_user.id
        
        # التحقق من أن البوت مكتمل الإعداد
        if not await is_bot_configured():
            await send_maintenance_message(client, message)
            return
        
        stats = await mining_manager.get_session_stats(user_id)
        
        if stats['total_sessions'] == 0:
            await message.reply_text(
                f"📭 **ليس لديك جلسات تعدين نشطة**\n\n"
                f"استخدم `/activate_mining` لتفعيل تعدين على رقم هاتفك\n"
                f"💎 ستحصل على {BotConfig.MINING_POINTS_PER_HOUR} نقطة كل ساعة!",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        sessions_text = ""
        for session in stats['sessions']:
            status = "✅ نشط" if session.get('is_active') else "❌ معطل"
            points = session.get('total_points_earned', 0)
            phone = session.get('phone', 'غير معروف')
            sessions_text += f"📱 `{phone}` | {status} | 💎 {points} نقطة\n"
        
        await message.reply_text(
            f"📊 **إحصائيات التعدين الخاصة بك**\n\n"
            f"📱 عدد الجلسات: {stats['total_sessions']}\n"
            f"✅ النشطة: {stats['active_sessions']}\n"
            f"💰 إجمالي النقاط: {stats['total_points_earned']}\n\n"
            f"**جلساتك:**\n{sessions_text}\n"
            f"💡 كل جلسة نشطة تمنحك {BotConfig.MINING_POINTS_PER_HOUR} نقطة كل ساعة",
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception:
        await message.reply_text("❌ حدث خطأ")


# ================== أمر /search ==================

@app.on_message(filters.command("search") & filters.private)
async def search_cmd(client: Client, message):
    """البحث في الأخبار"""
    try:
        user_id = message.from_user.id
        
        # التحقق من أن البوت مكتمل الإعداد
        if not await is_bot_configured():
            await send_maintenance_message(client, message)
            return
        
        query = message.text.replace("/search", "").strip()
        if not query:
            await message.reply_text(
                "🔍 **الرجاء إدخال نص البحث**\nمثال: `/search اقتصاد`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        await message.reply_text(f"🔍 **جاري البحث عن: {query}**...", parse_mode=ParseMode.MARKDOWN)
        
        results = search_news(query)
        
        if not results:
            await message.reply_text(
                f"🔍 لا توجد نتائج لـ: {query}",
                reply_markup=build_back_button(),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        text = f"🔍 **نتائج البحث عن: {query}**\n\n"
        buttons = []
        
        for i, news in enumerate(results[:5], 1):
            title = news.get('title', 'خبر')[:50]
            cat_id = news.get('category_id', 'general')
            cat_name = firebase_get(f"categories/{cat_id}/name") or 'عام'
            text += f"{i}. **{title}**\n   📂 {cat_name} | 👁 {news.get('views', 0)}\n\n"
            buttons.append([InlineKeyboardButton(f"{i}. {title[:40]}", callback_data=f"view_news_{news['id']}")])
        
        buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
        
        await message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception:
        pass


# ================== أمر /stats ==================

@app.on_message(filters.command("stats") & filters.private)
async def stats_cmd(client: Client, message):
    """عرض إحصائيات المستخدم"""
    try:
        user_id = message.from_user.id
        
        # التحقق من أن البوت مكتمل الإعداد
        if not await is_bot_configured():
            await send_maintenance_message(client, message)
            return
        
        stats = get_user_stats(user_id)
        
        text = f"""
📊 **إحصائيات حسابك**

💎 **النقاط الحالية:** {stats['points']}
🏆 **إجمالي النقاط:** {stats['total_points']}
📡 **المشتركين:** {stats['subscriptions']}
🤝 **الإحالات:** {stats['referrals']}
🔥 **الأيام المتتالية:** {stats['streak']}
⭐ **بريميوم:** {'نعم' if stats['is_premium'] else 'لا'}
🔗 **كود الإحالة:** `{stats['referral_code']}`

**كيفية كسب النقاط:**
• تفعيل قناة/مجموعة: +{BotConfig.POINTS_PER_SUBSCRIBE}
• مكافأة يومية: +{BotConfig.POINTS_DAILY_BONUS}
• مشاركة خبر: +{BotConfig.POINTS_PER_NEWS_SHARE}
• إحالة مستخدم: +{BotConfig.POINTS_PER_REFERRAL}
"""
        await message.reply_text(
            text,
            reply_markup=build_back_button(),
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception:
        pass


# ================== أمر /news ==================

@app.on_message(filters.command("news") & filters.private)
async def news_cmd(client: Client, message):
    """تعليمات تفعيل الأخبار"""
    try:
        user_id = message.from_user.id
        
        # التحقق من أن البوت مكتمل الإعداد
        if not await is_bot_configured():
            await send_maintenance_message(client, message)
            return
        
        activation_text = f"""
🔔 **لتفعيل الأخبار في قناتك أو مجموعتك مجاناً**

**الخطوات:**
1️⃣ أضف البوت كمشرف في قناتك/مجموعتك
`{BotConfig.BOT_USERNAME}`

2️⃣ ثم أرسل رابط القناة/المجموعة هنا 👇
مثال: `@channel_name` أو `https://t.me/channel_name`

💎 **ستحصل على {BotConfig.POINTS_PER_SUBSCRIBE} نقاط** عند التفعيل!
"""
        await message.reply_text(activation_text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception:
        await message.reply_text("❌ حدث خطأ")


# ================== تسجيل جميع المعالجات ==================

def register_all_handlers():
    """تسجيل جميع معالجات الأزرار والنصوص والأوامر"""
    register_callback_handlers(app)
    register_text_handlers(app)
    register_admin_handlers(app)


# ================== بدء تشغيل البوت ==================

async def main():
    """
    الدالة الرئيسية لتشغيل البوت
    - اختبار الاتصال بـ Firebase
    - تسجيل جميع المعالجات
    - بدء المهام الخلفية (جامع الأخبار، التعدين)
    - بدء تشغيل البوت
    """
    
    # ========== 1. اختبار الاتصال بـ Firebase ==========
    if not test_firebase_connection():
        # فشل الاتصال - تسجيل في الملف فقط
        logger.error("FATAL: Firebase connection failed")
        return
    
    # ========== 2. التحقق من وجود المشرفين في قاعدة البيانات ==========
    for admin_id in BotConfig.ADMIN_IDS:
        if not get_user(admin_id):
            create_user({
                'user_id': admin_id,
                'username': 'admin',
                'first_name': 'Admin',
                'last_name': '',
                'points': 1000,
                'is_premium': True,
                'is_admin': True
            })
    
    # ========== 3. تسجيل جميع المعالجات ==========
    register_all_handlers()
    
    # ========== 4. بدء المهام الخلفية ==========
    # تشغيل جامع الأخبار
    asyncio.create_task(start_collector())
    
    # تشغيل نظام التعدين
    asyncio.create_task(start_mining())
    
    # ========== 5. إضافة الجلسة الرئيسية للجامع (إذا كانت متوفرة) ==========
    # ملاحظة: هذه الجلسة اختيارية - يمكن للمشرف إضافتها لاحقاً عبر الأمر
    #YOUR_SESSION_STRING = "BAG08iEATdMNVilKG2JCVKGq3JPdwQqvgAnre6YDFHHKDDMVnEdzLZHizqk9hnWkeMXpX5O8K0tkEYU20fPw6FwRXxyWAu8LnuJBT4WszjIECCPO7KWGpjjJNAIErQhZPyE9b-1CMEr_5m8wE-sqPgpK4nwBfg_l_4wbRccs3bnXC95hLQwwXr-pGYjvftef5_MUmtk6uRGVSK5r9YMKkmYunxLFB6b9jQlRlDRFm0WfHjgYQ3FYI2z10AeVlBY_6FHaXRFBecNPwzxDBJ3bQXtmBNWV46gHbr2-L5wb1nRbkZL2RN1Xv1f0GeamkiwcTy1_ZiTRl6IYBrscKFi6pbGfL8Y1zQAAAAGLsSjtAA"
    #success, msg = await news_collector.add_session(YOUR_SESSION_STRING, BotConfig.ADMIN_IDS[0])
    
    # ========== 6. بدء تشغيل البوت ==========
    try:
        await app.start()
        await idle()
    except Exception as e:
        logger.error(f"Bot runtime error: {e}")
    finally:
        if app.is_initialized:
            await app.stop()
        await news_collector.stop_collecting()
        await mining_manager.stop_mining()


# ================== نقطة الدخول ==================

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        pass