#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
╔══════════════════════════════════════════════════════════════════╗
║                  CLASS: AdminHandlers                           ║
║              معالجات أوامر المشرف المتقدمة                      ║
║              يدعم إدارة المتغيرات، النصوص، الأزرار، الصلاحيات   ║
║              الكيانات، قاعدة البيانات، التصدير، والطلبات المعلقة ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import time
import hashlib
import tempfile
import os
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait

from bot_config import BotConfig
from firebase_core import firebase_get, firebase_set, firebase_update, firebase_delete, firebase_push
from user_manager import is_admin, get_user, get_user_stats, add_points, update_user
from news_manager import get_news_list, get_pending_news, approve_news, reject_news, delete_news, get_system_stats
from menu_builder import (
    build_admin_menu, build_back_button, build_cancel_button, 
    build_confirm_menu, build_admin_full_control_panel
)
from collector import news_collector
from mining_manager import mining_manager


def register_admin_handlers(app: Client):
    """تسجيل جميع معالجات أوامر المشرف"""
    
    # ==================== الأوامر الأساسية ====================
    
    @app.on_message(filters.command("admin") & filters.private)
    async def admin_cmd(client: Client, message: Message):
        """لوحة المشرف الأساسية"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك بالوصول إلى لوحة المشرف")
            return
        
        stats = get_system_stats()
        admin_text = f"""
📊 **إحصائيات المنظومة الإخبارية**

📰 إجمالي الأخبار: {stats['total_news']}
✅ الأخبار المنشورة: {stats['approved_news']}
⏳ قيد المراجعة: {stats['pending_news']}
👥 المشتركين النشطين: {stats['total_subscribers']}
👤 إجمالي المستخدمين: {stats['total_users']}

📡 **جامع الأخبار:**
👥 الجلسات النشطة: {await get_active_sessions_count()}
📁 الكيانات المراقبة: {await get_monitored_entities_count()}
📰 آخر استخراج: {await get_last_extraction_time()}

💰 **نظام التعدين:**
📋 طلبات معلقة: {await get_pending_mining_count()}
💎 إجمالي النقاط الممنوحة: {await get_total_mining_points()}
"""
        await message.reply_text(
            admin_text,
            reply_markup=build_admin_menu(stats['pending_news']),
            parse_mode=ParseMode.MARKDOWN
        )
    
    @app.on_message(filters.command("admin_control") & filters.private)
    async def admin_control_cmd(client: Client, message: Message):
        """لوحة التحكم الكاملة للمشرف"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك بالوصول إلى هذه الصفحة")
            return
        
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
    
    # ==================== إدارة المتغيرات ====================
    
    @app.on_message(filters.command("add_config") & filters.private)
    async def add_config_cmd(client: Client, message: Message):
        """إضافة متغير تكوين جديد"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        args = message.text.split(maxsplit=1)
        
        if len(args) < 2:
            await message.reply_text(
                "❌ **الاستخدام:**\n"
                "`/add_config [اسم_المتغير]`\n\n"
                "📝 **مثال:**\n"
                "`/add_config POINTS_PER_REFERRAL`\n\n"
                "📋 **لرؤية المتغيرات الموجودة:** `/config_list`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        var_name = args[1].upper()
        
        # التحقق من وجود المتغير مسبقاً
        existing = firebase_get(f"system_registry/variables/{var_name}")
        if existing:
            await message.reply_text(
                f"⚠️ **المتغير موجود مسبقاً**\n\n"
                f"`{var_name}` = `{existing.get('value', 'N/A')}`\n\n"
                f"للتعديل استخدم: `/edit_config {var_name}`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # حفظ حالة المشرف لانتظار القيمة
        firebase_set(f"admin_state/{user_id}", {
            "action": "waiting_config_value",
            "var_name": var_name,
            "step": 1
        })
        
        await message.reply_text(
            f"📝 **إضافة متغير:** `{var_name}`\n\n"
            f"**أدخل قيمة المتغير:**\n"
            f"(مثال: `50` للنصوص، `true` للقيم المنطقية، `\"نص\"` للنصوص)\n\n"
            f"📌 يمكنك استخدام الأزرار أدناه لتحديد النوع:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔢 رقم (int)", callback_data="config_type_int")],
                [InlineKeyboardButton("📝 نص (str)", callback_data="config_type_str")],
                [InlineKeyboardButton("✅ صح/خطأ (bool)", callback_data="config_type_bool")],
                [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_action")]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )
    
    @app.on_message(filters.command("edit_config") & filters.private)
    async def edit_config_cmd(client: Client, message: Message):
        """تعديل متغير تكوين موجود"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        args = message.text.split(maxsplit=1)
        
        if len(args) < 2:
            await message.reply_text(
                "❌ **الاستخدام:**\n"
                "`/edit_config [اسم_المتغير]`\n\n"
                "📝 **مثال:** `/edit_config POINTS_PER_REFERRAL`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        var_name = args[1].upper()
        
        # التحقق من وجود المتغير
        existing = firebase_get(f"system_registry/variables/{var_name}")
        if not existing:
            await message.reply_text(
                f"❌ **المتغير غير موجود**\n\n"
                f"`{var_name}`\n\n"
                f"لإضافته استخدم: `/add_config {var_name}`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # حفظ حالة المشرف لانتظار القيمة الجديدة
        firebase_set(f"admin_state/{user_id}", {
            "action": "waiting_edit_config_value",
            "var_name": var_name,
            "old_value": existing.get('value'),
            "old_type": existing.get('type', 'str')
        })
        
        await message.reply_text(
            f"✏️ **تعديل متغير:** `{var_name}`\n\n"
            f"📌 **القيمة الحالية:** `{existing.get('value', 'N/A')}`\n"
            f"📌 **النوع:** `{existing.get('type', 'str')}`\n\n"
            f"**أدخل القيمة الجديدة:**\n"
            f"(اتركه فارغاً للإبقاء على القيمة الحالية)",
            reply_markup=build_cancel_button(),
            parse_mode=ParseMode.MARKDOWN
        )
    
    @app.on_message(filters.command("config_list") & filters.private)
    async def config_list_cmd(client: Client, message: Message):
        """عرض جميع المتغيرات والإعدادات"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        variables = firebase_get("system_registry/variables") or {}
        
        if not variables:
            await message.reply_text(
                "📋 **لا توجد متغيرات مضافة حالياً**\n\n"
                "لإضافة متغير: `/add_config [اسم_المتغير]`",
                reply_markup=build_back_button("admin_control"),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        text = "📊 **المتغيرات والإعدادات**\n\n"
        
        # ترتيب المتغيرات حسب الفئة
        categories = {}
        for var_name, var_data in variables.items():
            category = var_data.get('category', 'عام')
            if category not in categories:
                categories[category] = []
            categories[category].append((var_name, var_data))
        
        for category, items in categories.items():
            text += f"**📂 {category}**\n"
            for var_name, var_data in items[:15]:  # حد 15 لكل فئة
                value = var_data.get('value', 'N/A')
                text += f"• `{var_name}` = `{value}`\n"
            text += "\n"
        
        if len(variables) > 30:
            text += f"\n📊 **إجمالي المتغيرات:** {len(variables)}"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة متغير", callback_data="admin_add_variable")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_control")]
        ])
        
        await message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    
    @app.on_message(filters.command("delete_config") & filters.private)
    async def delete_config_cmd(client: Client, message: Message):
        """حذف متغير تكوين"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        args = message.text.split(maxsplit=1)
        
        if len(args) < 2:
            await message.reply_text(
                "❌ **الاستخدام:**\n`/delete_config [اسم_المتغير]`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        var_name = args[1].upper()
        
        # التحقق من وجود المتغير
        existing = firebase_get(f"system_registry/variables/{var_name}")
        if not existing:
            await message.reply_text(f"❌ المتغير `{var_name}` غير موجود", parse_mode=ParseMode.MARKDOWN)
            return
        
        # طلب تأكيد الحذف
        firebase_set(f"admin_state/{user_id}", {
            "action": "confirm_delete_config",
            "var_name": var_name
        })
        
        await message.reply_text(
            f"⚠️ **تأكيد حذف المتغير**\n\n"
            f"`{var_name}` = `{existing.get('value', 'N/A')}`\n\n"
            f"هل أنت متأكد من رغبتك في حذف هذا المتغير؟",
            reply_markup=build_confirm_menu("delete_config", var_name),
            parse_mode=ParseMode.MARKDOWN
        )
    
    # ==================== إدارة النصوص ====================
    
    @app.on_message(filters.command("text_list") & filters.private)
    async def text_list_cmd(client: Client, message: Message):
        """عرض جميع النصوص القابلة للتعديل"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        texts = firebase_get("system_registry/texts") or {}
        
        if not texts:
            await message.reply_text(
                "📝 **لا توجد نصوص مضافة حالياً**\n\n"
                "لإضافة نص: `/add_text [معرف_النص]`",
                reply_markup=build_back_button("admin_control"),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        text = "📝 **النصوص القابلة للتعديل**\n\n"
        for text_id, text_data in list(texts.items())[:25]:
            desc = text_data.get('description', '')
            lang_ar = text_data.get('ar', '')[:50]
            text += f"• `{text_id}`\n   📌 {desc}\n   🇸🇦 {lang_ar}...\n\n"
        
        if len(texts) > 25:
            text += f"\n📊 **إجمالي النصوص:** {len(texts)}"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة نص", callback_data="admin_add_text")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_control")]
        ])
        
        await message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    
    @app.on_message(filters.command("add_text") & filters.private)
    async def add_text_cmd(client: Client, message: Message):
        """إضافة نص جديد"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        args = message.text.split(maxsplit=1)
        
        if len(args) < 2:
            await message.reply_text(
                "❌ **الاستخدام:**\n"
                "`/add_text [معرف_النص]`\n\n"
                "📝 **مثال:** `/add_text welcome_message`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        text_id = args[1]
        
        # التحقق من وجود النص مسبقاً
        existing = firebase_get(f"system_registry/texts/{text_id}")
        if existing:
            await message.reply_text(
                f"⚠️ **النص موجود مسبقاً**\n\n"
                f"`{text_id}`\n\n"
                f"للتعديل استخدم: `/edit_text {text_id}`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # حفظ حالة المشرف لانتظار المحتوى
        firebase_set(f"admin_state/{user_id}", {
            "action": "waiting_text_content",
            "text_id": text_id,
            "step": 1
        })
        
        await message.reply_text(
            f"📝 **إضافة نص:** `{text_id}`\n\n"
            f"**أدخل محتوى النص (باللغة العربية):**\n\n"
            f"📌 يمكنك استخدام Markdown و {{{{#VAR_NAME}}}} للقيم الديناميكية\n\n"
            f"مثال: `مرحباً {{{{#user.first_name}}}}! نقاطك: {{{{#points}}}}`",
            reply_markup=build_cancel_button(),
            parse_mode=ParseMode.MARKDOWN
        )
    
    @app.on_message(filters.command("edit_text") & filters.private)
    async def edit_text_cmd(client: Client, message: Message):
        """تعديل نص موجود"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        args = message.text.split(maxsplit=1)
        
        if len(args) < 2:
            await message.reply_text(
                "❌ **الاستخدام:**\n`/edit_text [معرف_النص]`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        text_id = args[1]
        
        # التحقق من وجود النص
        existing = firebase_get(f"system_registry/texts/{text_id}")
        if not existing:
            await message.reply_text(
                f"❌ **النص غير موجود**\n\n"
                f"`{text_id}`\n\n"
                f"لإضافته استخدم: `/add_text {text_id}`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        firebase_set(f"admin_state/{user_id}", {
            "action": "waiting_edit_text_content",
            "text_id": text_id,
            "old_content": existing.get('ar', '')
        })
        
        await message.reply_text(
            f"✏️ **تعديل نص:** `{text_id}`\n\n"
            f"📌 **المحتوى الحالي:**\n```\n{existing.get('ar', '')[:200]}```\n\n"
            f"**أدخل المحتوى الجديد:**\n(اتركه فارغاً للإبقاء على المحتوى الحالي)",
            reply_markup=build_cancel_button(),
            parse_mode=ParseMode.MARKDOWN
        )
    
    # ==================== إدارة الأزرار ====================
    
    @app.on_message(filters.command("button_list") & filters.private)
    async def button_list_cmd(client: Client, message: Message):
        """عرض جميع الأزرار الديناميكية"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        buttons = firebase_get("dynamic_buttons") or {}
        
        if not buttons:
            await message.reply_text(
                "🔘 **لا توجد أزرار مضافة**\n\n"
                "لإضافة زر: `/add_button`",
                reply_markup=build_back_button("admin_control"),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        text = "🔘 **الأزرار الديناميكية**\n\n"
        for btn_id, btn_data in list(buttons.items())[:20]:
            btn_text = btn_data.get('text_ar', 'زر')
            is_hidden = btn_data.get('is_hidden', False)
            status = "👁️ مخفي" if is_hidden else "👁️ ظاهر"
            text += f"• `{btn_id}` - {btn_text} ({status})\n"
        
        if len(buttons) > 20:
            text += f"\n📊 **إجمالي الأزرار:** {len(buttons)}"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة زر", callback_data="admin_add_button")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_control")]
        ])
        
        await message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    
    @app.on_message(filters.command("add_button") & filters.private)
    async def add_button_cmd(client: Client, message: Message):
        """إضافة زر ديناميكي جديد"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        firebase_set(f"admin_state/{user_id}", {
            "action": "waiting_btn_name",
            "step": 1
        })
        
        await message.reply_text(
            "🔘 **إضافة زر جديد**\n\n"
            "**أدخل النص الذي سيظهر على الزر:**\n"
            "مثال: `💰 تمويل القناة`",
            reply_markup=build_cancel_button(),
            parse_mode=ParseMode.MARKDOWN
        )
    
    @app.on_message(filters.command("edit_button") & filters.private)
    async def edit_button_cmd(client: Client, message: Message):
        """تعديل زر موجود"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        args = message.text.split(maxsplit=1)
        
        if len(args) < 2:
            await message.reply_text(
                "❌ **الاستخدام:**\n`/edit_button [button_id]`\n\n"
                "لرؤية الأزرار الموجودة: `/button_list`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        btn_id = args[1]
        
        # التحقق من وجود الزر
        existing = firebase_get(f"dynamic_buttons/{btn_id}")
        if not existing:
            await message.reply_text(f"❌ الزر `{btn_id}` غير موجود", parse_mode=ParseMode.MARKDOWN)
            return
        
        firebase_set(f"admin_state/{user_id}", {
            "action": "waiting_edit_btn",
            "btn_id": btn_id,
            "btn_data": existing
        })
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 تعديل النص", callback_data="edit_btn_text")],
            [InlineKeyboardButton("📄 تعديل المحتوى", callback_data="edit_btn_msg")],
            [InlineKeyboardButton("👁️ إخفاء/إظهار", callback_data="toggle_btn_visibility")],
            [InlineKeyboardButton("🗑️ حذف", callback_data="delete_btn")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_action")]
        ])
        
        await message.reply_text(
            f"✏️ **تعديل زر:** `{btn_id}`\n\n"
            f"📌 **النص الحالي:** {existing.get('text_ar', 'N/A')}\n"
            f"📌 **الحالة:** {'مخفي' if existing.get('is_hidden') else 'ظاهر'}\n\n"
            f"اختر الإجراء المطلوب:",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    
    @app.on_message(filters.command("delete_button") & filters.private)
    async def delete_button_cmd(client: Client, message: Message):
        """حذف زر"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        args = message.text.split(maxsplit=1)
        
        if len(args) < 2:
            await message.reply_text(
                "❌ **الاستخدام:**\n`/delete_button [button_id]`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        btn_id = args[1]
        
        # التحقق من وجود الزر
        existing = firebase_get(f"dynamic_buttons/{btn_id}")
        if not existing:
            await message.reply_text(f"❌ الزر `{btn_id}` غير موجود", parse_mode=ParseMode.MARKDOWN)
            return
        
        firebase_set(f"admin_state/{user_id}", {
            "action": "confirm_delete_button",
            "btn_id": btn_id
        })
        
        await message.reply_text(
            f"⚠️ **تأكيد حذف الزر**\n\n"
            f"`{btn_id}` - {existing.get('text_ar', 'زر')}\n\n"
            f"هل أنت متأكد من رغبتك في حذف هذا الزر؟",
            reply_markup=build_confirm_menu("delete_button", btn_id),
            parse_mode=ParseMode.MARKDOWN
        )
    
    # ==================== إدارة الصلاحيات ====================
    
    @app.on_message(filters.command("perm_list") & filters.private)
    async def perm_list_cmd(client: Client, message: Message):
        """عرض جميع الصلاحيات"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        permissions = firebase_get("system_registry/permissions") or {}
        
        if not permissions:
            await message.reply_text(
                "🔐 **لا توجد صلاحيات مضافة**\n\n"
                "الصلاحيات الافتراضية:\n"
                "• `admin_only` - للمشرفين فقط\n"
                "• `premium_only` - للمستخدمين المميزين فقط",
                reply_markup=build_back_button("admin_control"),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        text = "🔐 **الصلاحيات المتاحة**\n\n"
        for perm_id, perm_data in permissions.items():
            desc = perm_data.get('description', '')
            roles = ', '.join(perm_data.get('roles', []))
            text += f"• `{perm_id}`\n   📌 {desc}\n   👥 {roles}\n\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة صلاحية", callback_data="admin_add_permission")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_control")]
        ])
        
        await message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    
    @app.on_message(filters.command("add_permission") & filters.private)
    async def add_permission_cmd(client: Client, message: Message):
        """إضافة صلاحية جديدة"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        firebase_set(f"admin_state/{user_id}", {
            "action": "waiting_perm_id",
            "step": 1
        })
        
        await message.reply_text(
            "🔐 **إضافة صلاحية جديدة**\n\n"
            "**أدخل معرف الصلاحية:**\n"
            "مثال: `premium_only` أو `points_required_100`",
            reply_markup=build_cancel_button(),
            parse_mode=ParseMode.MARKDOWN
        )
    
    # ==================== إدارة الكيانات ====================
    
    @app.on_message(filters.command("entity_list") & filters.private)
    async def entity_list_cmd(client: Client, message: Message):
        """عرض جميع الكيانات المدارة"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        monitored = firebase_get("monitored_entities") or {}
        
        if not monitored:
            await message.reply_text(
                "📡 **لا توجد كيانات مراقبة**\n\n"
                "لإضافة كيان: `/add_monitor [@username] [category_id]`",
                reply_markup=build_back_button("admin_control"),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        text = "📡 **الكيانات المراقبة**\n\n"
        categories = firebase_get("categories") or {}
        
        for entity_id, entity_data in list(monitored.items())[:20]:
            username = entity_data.get('username', 'N/A')
            cat_id = entity_data.get('category_id', 'general')
            cat_name = categories.get(cat_id, {}).get('name', cat_id)
            status = "✅" if entity_data.get('status') == 'active' else "❌"
            text += f"{status} `{entity_id}`\n   📡 {username}\n   📂 {cat_name}\n\n"
        
        if len(monitored) > 20:
            text += f"\n📊 **إجمالي الكيانات:** {len(monitored)}"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة كيان", callback_data="admin_add_entity")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_control")]
        ])
        
        await message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    
    @app.on_message(filters.command("add_monitor") & filters.private)
    async def add_monitor_cmd(client: Client, message: Message):
        """إضافة كيان للمراقبة"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        args = message.text.split()
        
        if len(args) < 3:
            await message.reply_text(
                "❌ **الاستخدام:**\n"
                "`/add_monitor [@username] [category_id]`\n\n"
                "📝 **مثال:** `/add_monitor @news_channel politics`\n\n"
                "📋 **الفئات المتاحة:** general, politics, economy, sports, technology, health",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        username = args[1]
        category_id = args[2]
        
        # التحقق من الفئة
        categories = firebase_get("categories") or {}
        if category_id not in categories and category_id not in ['general', 'politics', 'economy', 'sports', 'technology', 'health']:
            await message.reply_text(f"❌ الفئة `{category_id}` غير موجودة", parse_mode=ParseMode.MARKDOWN)
            return
        
        await message.reply_text(
            f"⏳ **جاري التحقق من الكيان** `{username}`...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            # محاولة الحصول على معلومات الكيان
            chat = await client.get_chat(username)
            entity_id = str(chat.id)
            access_hash = getattr(chat, 'access_hash', None)
            name = chat.title or username
            
            # إضافة الكيان للمراقبة
            success = await news_collector.add_monitored_entity(
                entity_id=entity_id,
                username=username,
                category_id=category_id,
                access_hash=str(access_hash) if access_hash else None,
                name=name
            )
            
            if success:
                await message.reply_text(
                    f"✅ **تم إضافة الكيان للمراقبة**\n\n"
                    f"📡 **الكيان:** {name}\n"
                    f"🆔 **المعرف:** `{entity_id}`\n"
                    f"📂 **الفئة:** {category_id}\n"
                    f"🔑 **Access Hash:** `{access_hash}`\n\n"
                    f"📰 سيتم جلب جميع رسائل هذا الكيان كأخبار.",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await message.reply_text("❌ فشل إضافة الكيان للمراقبة", parse_mode=ParseMode.MARKDOWN)
                
        except Exception as e:
            await message.reply_text(
                f"❌ **فشل الوصول للكيان**\n\n"
                f"تأكد من:\n"
                f"• صحة @username\n"
                f"• أن البوت لديه صلاحية الوصول\n"
                f"• أن الكيان عام أو البوت مضاف كمشرف\n\n"
                f"**الخطأ:** {str(e)[:100]}",
                parse_mode=ParseMode.MARKDOWN
            )
    
    @app.on_message(filters.command("remove_monitor") & filters.private)
    async def remove_monitor_cmd(client: Client, message: Message):
        """إزالة كيان من المراقبة"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        args = message.text.split()
        
        if len(args) < 2:
            await message.reply_text(
                "❌ **الاستخدام:**\n"
                "`/remove_monitor [entity_id]`\n\n"
                "لرؤية الكيانات المراقبة: `/entity_list`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        entity_id = args[1]
        
        success = await news_collector.remove_monitored_entity(entity_id)
        
        if success:
            await message.reply_text(f"✅ تم إزالة الكيان `{entity_id}` من المراقبة", parse_mode=ParseMode.MARKDOWN)
        else:
            await message.reply_text(f"❌ فشل إزالة الكيان `{entity_id}`", parse_mode=ParseMode.MARKDOWN)
    
    # ==================== إدارة قاعدة البيانات ====================
    
    @app.on_message(filters.command("db_stats") & filters.private)
    async def db_stats_cmd(client: Client, message: Message):
        """إحصائيات قاعدة البيانات"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        # جلب إحصائيات من Firebase
        users_count = len(firebase_get("users") or {})
        news_count = len(firebase_get("news") or {})
        subscribers_count = len(firebase_get("subscribers") or {})
        sessions_count = len(firebase_get("sessions") or {})
        buttons_count = len(firebase_get("dynamic_buttons") or {})
        variables_count = len(firebase_get("system_registry/variables") or {})
        
        text = f"""
🗄️ **إحصائيات قاعدة البيانات**

📊 **المجموعات:**
• 👤 المستخدمين: `{users_count}`
• 📰 الأخبار: `{news_count}`
• 📡 المشتركين: `{subscribers_count}`
• 🔑 الجلسات: `{sessions_count}`
• 🔘 الأزرار: `{buttons_count}`
• 📊 المتغيرات: `{variables_count}`

📅 **آخر تحديث:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💾 إنشاء نسخة احتياطية", callback_data="db_backup")],
            [InlineKeyboardButton("🔄 استعادة نسخة", callback_data="db_restore")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_control")]
        ])
        
        await message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    
    @app.on_message(filters.command("db_backup") & filters.private)
    async def db_backup_cmd(client: Client, message: Message):
        """إنشاء نسخة احتياطية من قاعدة البيانات"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        await message.reply_text("⏳ **جاري إنشاء النسخة الاحتياطية...**", parse_mode=ParseMode.MARKDOWN)
        
        try:
            # جمع جميع البيانات
            backup_data = {
                "backup_time": datetime.now().isoformat(),
                "created_by": user_id,
                "version": BotConfig.APP_VERSION,
                "data": {
                    "users": firebase_get("users") or {},
                    "news": firebase_get("news") or {},
                    "subscribers": firebase_get("subscribers") or {},
                    "sessions": firebase_get("sessions") or {},
                    "dynamic_buttons": firebase_get("dynamic_buttons") or {},
                    "categories": firebase_get("categories") or {},
                    "monitored_entities": firebase_get("monitored_entities") or {},
                    "system_registry": firebase_get("system_registry") or {},
                    "mining_sessions": firebase_get("mining_sessions") or {}
                }
            }
            
            # حفظ في Firebase
            backup_id = f"backup_{int(time.time())}"
            firebase_set(f"backups/{backup_id}", backup_data)
            
            # إنشاء ملف JSON للتحميل
            json_data = json.dumps(backup_data, ensure_ascii=False, indent=2, default=str)
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
                f.write(json_data)
                temp_path = f.name
            
            # إرسال الملف للمشرف
            await client.send_document(
                user_id,
                temp_path,
                caption=f"💾 **نسخة احتياطية**\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n🆔 `{backup_id}`",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # تنظيف الملف المؤقت
            os.unlink(temp_path)
            
            await message.reply_text(
                f"✅ **تم إنشاء النسخة الاحتياطية بنجاح!**\n\n"
                f"🆔 المعرف: `{backup_id}`\n"
                f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            await message.reply_text(f"❌ فشل إنشاء النسخة الاحتياطية: {str(e)[:100]}", parse_mode=ParseMode.MARKDOWN)
    
    # ==================== إدارة التعدين ====================
    
    @app.on_message(filters.command("pending_mining") & filters.private)
    async def pending_mining_cmd(client: Client, message: Message):
        """عرض طلبات التعدين المعلقة"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        pending = await mining_manager.get_pending_approvals()
        
        if not pending:
            await message.reply_text(
                "📋 **لا توجد طلبات تعدين معلقة**",
                reply_markup=build_back_button("admin_control"),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        text = "📋 **طلبات التعدين المعلقة**\n\n"
        for p in pending:
            text += f"🆔 `{p['approval_id']}`\n"
            text += f"📱 {p['phone']}\n"
            text += f"👤 المستخدم: `{p['user_id']}`\n"
            text += f"👤 الاسم: {p['first_name']}\n"
            text += f"🕐 الطلب: {p['created_at'][:19]}\n\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_control")]
        ])
        
        await message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    
    @app.on_message(filters.command("add_sessions") & filters.private)
    async def add_sessions_cmd(client: Client, message: Message):
        """
        إضافة جلسة تعدين مباشرة (للمشرف فقط)
        الاستخدام: /add_sessions [session_string]
        """
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        args = message.text.split(maxsplit=1)
        
        if len(args) < 2:
            await message.reply_text(
                "❌ **الاستخدام:**\n"
                "`/add_sessions [session_string]`\n\n"
                "📝 **ملاحظة:** يتم إرسال session_string تلقائياً عند الموافقة على طلب التعدين.\n\n"
                "لرؤية الطلبات المعلقة: `/pending_mining`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        session_string = args[1]
        
        await message.reply_text(
            "⏳ **جاري التحقق من الجلسة وإضافتها...**",
            parse_mode=ParseMode.MARKDOWN
        )
        
        success, msg = await mining_manager.add_session_directly(session_string, user_id, client)
        
        await message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    
    @app.on_message(filters.command("mining_stats") & filters.private)
    async def mining_stats_cmd(client: Client, message: Message):
        """إحصائيات نظام التعدين"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        stats = mining_manager.stats
        
        text = f"""
💰 **إحصائيات نظام التعدين**

📊 **الجلسات:**
• إجمالي الجلسات: `{stats.get('total_sessions', 0)}`
• النشطة حالياً: `{stats.get('active_mining', 0)}`
• طلبات معلقة: `{stats.get('pending_approvals', 0)}`

💎 **النقاط:**
• إجمالي النقاط الممنوحة: `{stats.get('total_points_earned', 0)}`

⏱ **آخر تشغيل:** {stats.get('last_mining_run', 'لم يبدأ بعد')[:19] if stats.get('last_mining_run') else 'لم يبدأ بعد'}
"""
        
        await message.reply_text(text, reply_markup=build_back_button("admin_control"), parse_mode=ParseMode.MARKDOWN)
    
    # ==================== إدارة جلسات الجامع ====================
    
    @app.on_message(filters.command("collector_sessions") & filters.private)
    async def collector_sessions_cmd(client: Client, message: Message):
        """عرض جلسات جامع الأخبار"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        stats = await news_collector.get_collector_stats()
        
        text = f"""
📡 **جلسات جامع الأخبار**

👥 **الجلسات النشطة:** {stats.get('active_sessions', 0)}

📊 **إحصائيات الجامع:**
• إجمالي المستخرج: `{stats.get('total_extracted', 0)}`
• إجمالي المسوح: `{stats.get('total_scanned', 0)}`
• الأخطاء: `{stats.get('total_errors', 0)}`
• الكيانات المراقبة: `{stats.get('monitored_entities', 0)}`

🕐 **آخر مسح:** {stats.get('last_scan', 'لم يتم بعد')[:19] if stats.get('last_scan') else 'لم يتم بعد'}
"""
        
        sessions_info = stats.get('session_details', {})
        if sessions_info:
            text += "\n📋 **تفاصيل الجلسات:**\n"
            for sid, info in sessions_info.items():
                text += f"• {info.get('first_name', 'N/A')} (@{info.get('username', 'N/A')}) - {info.get('total_extracted', 0)} خبر\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="refresh_collector")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_control")]
        ])
        
        await message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    
    # ==================== أوامر المراجعة ====================
    
    @app.on_message(filters.command("review_news") & filters.private)
    async def review_news_cmd(client: Client, message: Message):
        """مراجعة الأخبار المعلقة"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        pending = get_pending_news(limit=20)
        
        if not pending:
            await message.reply_text(
                "✅ **لا توجد أخبار قيد المراجعة**",
                reply_markup=build_back_button("admin_panel"),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # حفظ قائمة الأخبار للمراجعة
        firebase_set(f"review_navigation/{user_id}", {
            "news_list": pending,
            "current_index": 0,
            "total": len(pending)
        })
        
        await show_review_news(client, message, pending, 0)
    
    # ==================== أوامر التصدير ====================
    
    @app.on_message(filters.command("final_script") & filters.private)
    async def final_script_cmd(client: Client, message: Message):
        """تصدير كود البوت الكامل"""
        user_id = message.from_user.id
        
        if not is_admin(user_id):
            await message.reply_text("❌ غير مصرح لك")
            return
        
        args = message.text.split()
        
        if len(args) < 2:
            await message.reply_text(
                "📦 **إدارة كود البوت**\n\n"
                "• `/final_script download` - تحميل نسخة كاملة من الكود\n"
                "• `/final_script info` - معلومات النسخة الحالية\n"
                "• `/final_script backups` - عرض النسخ الاحتياطية",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        action = args[1].lower()
        
        if action == "download":
            await export_bot_script(client, message)
        elif action == "info":
            await script_info_cmd(client, message)
        elif action == "backups":
            await list_backups_cmd(client, message)
        else:
            await message.reply_text("❌ أمر غير معروف. استخدم /final_script لعرض المساعدة")
    
    # ==================== دوال مساعدة ====================
    
    async def show_review_news(client: Client, message: Message, news_list: List[Dict], index: int):
        """عرض خبر واحد للمراجعة"""
        if index >= len(news_list):
            await message.reply_text(
                "✅ **تمت مراجعة جميع الأخبار**",
                reply_markup=build_back_button("admin_panel"),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        news = news_list[index]
        categories = firebase_get("categories") or {}
        cat_name = categories.get(news.get('category_id', 'general'), {}).get('name', 'عام')
        
        text = f"""
📋 **مراجعة خبر {index + 1}/{len(news_list)}**

**العنوان:** {news.get('title', 'بدون عنوان')}

**المحتوى:**
{news.get('content', 'لا يوجد محتوى')[:500]}{'...' if len(news.get('content', '')) > 500 else ''}

**المصدر:** {news.get('source_name', 'غير معروف')}
**الفئة:** {cat_name}
**التاريخ:** {news.get('created_at', datetime.now().isoformat())[:10]}
"""
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ موافقة", callback_data=f"approve_news_{news['id']}"),
                InlineKeyboardButton("❌ رفض", callback_data=f"reject_news_{news['id']}")
            ],
            [
                InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_news_{news['id']}")
            ],
            [
                InlineKeyboardButton("◀️ السابق", callback_data=f"review_prev_{index}"),
                InlineKeyboardButton(f"{index + 1}/{len(news_list)}", callback_data="none"),
                InlineKeyboardButton("التالي ▶️", callback_data=f"review_next_{index}")
            ],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
        ])
        
        await message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    
    async def export_bot_script(client: Client, message: Message):
        """تصدير كود البوت الكامل"""
        user_id = message.from_user.id
        
        await message.reply_text(
            "🔽 **جاري تصدير كود البوت...**\n\n"
            "📂 جمع البيانات والإعدادات...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            # جمع جميع البيانات الديناميكية
            script_data = {
                "export_time": datetime.now().isoformat(),
                "exported_by": user_id,
                "version": BotConfig.APP_VERSION,
                "config": {
                    "BOT_TOKEN": BotConfig.BOT_TOKEN[:10] + "...",
                    "API_ID": BotConfig.API_ID,
                    "ADMIN_IDS": BotConfig.ADMIN_IDS,
                    "FIREBASE_URL": BotConfig.FIREBASE_URL,
                },
                "registry": {
                    "variables": firebase_get("system_registry/variables") or {},
                    "texts": firebase_get("system_registry/texts") or {},
                    "buttons": firebase_get("dynamic_buttons") or {},
                    "permissions": firebase_get("system_registry/permissions") or {},
                },
                "entities": firebase_get("monitored_entities") or {},
                "subscribers": firebase_get("subscribers") or {},
                "categories": firebase_get("categories") or {},
                "stats": {
                    "total_users": len(firebase_get("users") or {}),
                    "total_news": len(firebase_get("news") or {}),
                    "total_subscribers": len(firebase_get("subscribers") or {})
                }
            }
            
            # تحويل إلى JSON
            json_data = json.dumps(script_data, ensure_ascii=False, indent=2, default=str)
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
                f.write(json_data)
                temp_path = f.name
            
            # إرسال الملف
            await client.send_document(
                user_id,
                temp_path,
                caption=f"📦 **نسخة تصدير البوت**\n\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n📌 الإصدار: {BotConfig.APP_VERSION}",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # تنظيف
            os.unlink(temp_path)
            
            # تسجيل الحدث
            firebase_push("export_history", {
                "user_id": user_id,
                "timestamp": datetime.now().isoformat(),
                "version": BotConfig.APP_VERSION
            })
            
        except Exception as e:
            await message.reply_text(f"❌ فشل التصدير: {str(e)[:100]}", parse_mode=ParseMode.MARKDOWN)
    
    async def script_info_cmd(client: Client, message: Message):
        """عرض معلومات النسخة الحالية"""
        user_id = message.from_user.id
        
        # جلب آخر تصدير
        exports = firebase_get("export_history") or {}
        last_export = None
        for exp_id, exp_data in exports.items():
            if not last_export or exp_data.get('timestamp', '') > last_export.get('timestamp', ''):
                last_export = exp_data
        
        text = f"""
📦 **معلومات البوت الحالي**

📌 **الإصدار:** {BotConfig.APP_VERSION}
🕐 **آخر تحديث:** {last_export.get('timestamp', 'غير معروف')[:19] if last_export else 'غير معروف'}
👤 **آخر مُصدِّر:** {last_export.get('user_id', 'غير معروف') if last_export else 'غير معروف'}

📊 **الإحصائيات:**
• عدد المتغيرات: {len(firebase_get('system_registry/variables') or {})}
• عدد النصوص: {len(firebase_get('system_registry/texts') or {})}
• عدد الأزرار: {len(firebase_get('dynamic_buttons') or {})}
• عدد الكيانات المراقبة: {len(firebase_get('monitored_entities') or {})}
• عدد المستخدمين: {len(firebase_get('users') or {})}
"""
        
        await message.reply_text(text, reply_markup=build_back_button("admin_control"), parse_mode=ParseMode.MARKDOWN)
    
    async def list_backups_cmd(client: Client, message: Message):
        """عرض قائمة النسخ الاحتياطية"""
        user_id = message.from_user.id
        
        backups = firebase_get("backups") or {}
        
        if not backups:
            await message.reply_text(
                "📋 **لا توجد نسخ احتياطية**",
                reply_markup=build_back_button("admin_control"),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        text = "💾 **النسخ الاحتياطية المتاحة**\n\n"
        for backup_id, backup_data in list(backups.items())[-10:]:
            timestamp = backup_data.get('backup_time', backup_data.get('timestamp', ''))[:19]
            created_by = backup_data.get('created_by', 'غير معروف')
            text += f"• `{backup_id}`\n   📅 {timestamp}\n   👤 {created_by}\n\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_control")]
        ])
        
        await message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    
    # ==================== دوال إحصائيات مساعدة ====================
    
    async def get_active_sessions_count() -> int:
        """عدد الجلسات النشطة"""
        sessions = firebase_get("sessions") or {}
        return sum(1 for s in sessions.values() if s.get('is_active', False))
    
    async def get_monitored_entities_count() -> int:
        """عدد الكيانات المراقبة"""
        return len(firebase_get("monitored_entities") or {})
    
    async def get_last_extraction_time() -> str:
        """وقت آخر استخراج"""
        stats = firebase_get("collector_stats") or {}
        return stats.get('last_scan', 'لم يتم بعد')[:19] if stats.get('last_scan') else 'لم يتم بعد'
    
    async def get_pending_mining_count() -> int:
        """عدد طلبات التعدين المعلقة"""
        pending = await mining_manager.get_pending_approvals()
        return len(pending)
    
    async def get_total_mining_points() -> int:
        """إجمالي نقاط التعدين الممنوحة"""
        return mining_manager.stats.get('total_points_earned', 0)


# ==================== تسجيل المعالجات ====================

def register_admin_handlers(app: Client):
    """تسجيل جميع معالجات أوامر المشرف - تم تنفيذها أعلاه"""
    # جميع الدوال مسجلة بالفعل داخل هذا الـ function
    pass