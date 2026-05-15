#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
╔══════════════════════════════════════════════════════════════════╗
║                    CLASS: MenuBuilder                           ║
║              بناء جميع لوحات المفاتيح والأزرار                  ║
╚══════════════════════════════════════════════════════════════════╝
"""

from typing import Dict, List, Optional
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

from bot_config import BotConfig
from firebase_core import firebase_get
from user_manager import is_admin


def build_main_menu(user_id: int) -> InlineKeyboardMarkup:
    """بناء القائمة الرئيسية"""
    buttons = []
    
    # الأزرار الأساسية
    buttons.append([InlineKeyboardButton("📰 آخر الأخبار", callback_data="latest_news")])
    buttons.append([InlineKeyboardButton("🔍 فئات الأخبار", callback_data="categories")])
    buttons.append([InlineKeyboardButton("🔔 تفعيل الأخبار", callback_data="activate_news")])
    buttons.append([InlineKeyboardButton("💎 نقاطي", callback_data="my_stats")])
    
    # الأزرار الديناميكية من Firebase
    dynamic_btns = firebase_get("dynamic_buttons") or {}
    for btn_id, btn_data in dynamic_btns.items():
        if not btn_data.get('is_deleted') and not btn_data.get('is_hidden'):
            btn_text = btn_data.get('text_ar', btn_data.get('name', 'زر'))
            buttons.append([InlineKeyboardButton(btn_text, callback_data=f"dyn_{btn_id}")])
    
    buttons.append([InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings")])
    buttons.append([InlineKeyboardButton("❓ مساعدة", callback_data="help")])
    
    if is_admin(user_id):
        buttons.append([InlineKeyboardButton("👑 لوحة المشرف", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(buttons)


def build_admin_full_control_panel() -> InlineKeyboardMarkup:
    """بناء لوحة التحكم الكاملة للمشرف"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 المتغيرات والإعدادات", callback_data="admin_variables")],
        [InlineKeyboardButton("📝 إدارة النصوص", callback_data="admin_texts")],
        [InlineKeyboardButton("🔘 إدارة الأزرار", callback_data="admin_buttons")],
        [InlineKeyboardButton("🔐 إدارة الصلاحيات", callback_data="admin_permissions")],
        [InlineKeyboardButton("📡 إدارة الكيانات", callback_data="admin_entities")],
        [InlineKeyboardButton("🗄️ إدارة قاعدة البيانات", callback_data="admin_database")],
        [InlineKeyboardButton("📦 تصدير البوت", callback_data="admin_export")],
        [InlineKeyboardButton("⚡ الأحداث والعمليات", callback_data="admin_events")],
        [InlineKeyboardButton("🎁 الهدايا والمكافآت", callback_data="admin_gifts")],
        [InlineKeyboardButton("✅ إنهاء الإعداد", callback_data="admin_complete_setup")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ])


def build_admin_menu(pending_count: int = 0) -> InlineKeyboardMarkup:
    """بناء قائمة المشرف الأساسية"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ مراجعة الأخبار ({pending_count})", callback_data="review_news")],
        [InlineKeyboardButton("📊 إحصائيات النظام", callback_data="admin_stats")],
        [InlineKeyboardButton("📤 إرسال جماعي", callback_data="broadcast")],
        [InlineKeyboardButton("📡 الكيانات النشطة", callback_data="admin_entities_list")],
        [InlineKeyboardButton("➕ إضافة خدمة", callback_data="admin_add_service")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")],
    ])


def build_categories_menu() -> InlineKeyboardMarkup:
    """بناء قائمة الفئات"""
    buttons = []
    categories = firebase_get("categories") or {}
    
    default_cats = {
        "general": {"name": "عام", "icon": "📰"},
        "politics": {"name": "سياسة", "icon": "🏛️"},
        "economy": {"name": "اقتصاد", "icon": "💰"},
        "sports": {"name": "رياضة", "icon": "⚽"},
        "technology": {"name": "تقنية", "icon": "💻"},
    }
    
    all_cats = {**default_cats, **categories}
    
    for cat_id, cat_data in all_cats.items():
        icon = cat_data.get('icon', '📁')
        name = cat_data.get('name', cat_id)
        buttons.append([InlineKeyboardButton(f"{icon} {name}", callback_data=f"category_{cat_id}")])
    
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(buttons)


def build_back_button(callback_data: str = "back_main") -> InlineKeyboardMarkup:
    """زر رجوع بسيط"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=callback_data)]
    ])


def build_cancel_button() -> InlineKeyboardMarkup:
    """زر إلغاء"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_action")]
    ])


def build_confirm_menu(action: str, item_id: str) -> InlineKeyboardMarkup:
    """قائمة تأكيد"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تأكيد", callback_data=f"confirm_{action}_{item_id}"),
         InlineKeyboardButton("❌ إلغاء", callback_data="cancel_action")]
    ])


def build_reply_keyboard(options: List[str], row_size: int = 2) -> ReplyKeyboardMarkup:
    """لوحة مفاتيح ردود"""
    keyboard = []
    for i in range(0, len(options), row_size):
        row = options[i:i + row_size]
        keyboard.append([KeyboardButton(opt) for opt in row])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ==================== دوال إدارة فئات الكيانات ====================

def build_categories_management_menu(entity_id: str, entity_name: str) -> InlineKeyboardMarkup:
    """
    بناء قائمة إدارة فئات كيان معين
    
    Args:
        entity_id: معرف الكيان
        entity_name: اسم الكيان
    
    Returns:
        InlineKeyboardMarkup
    """
    from firebase_core import firebase_get
    from entity_manager import get_entity_category_preferences
    
    categories = firebase_get("categories") or {}
    default_cats = {
        "general": {"name": "عام", "icon": "📰"},
        "politics": {"name": "سياسة", "icon": "🏛️"},
        "economy": {"name": "اقتصاد", "icon": "💰"},
        "sports": {"name": "رياضة", "icon": "⚽"},
        "technology": {"name": "تقنية", "icon": "💻"},
        "health": {"name": "صحة", "icon": "🏥"},
    }
    all_cats = {**default_cats, **categories}
    
    preferences = get_entity_category_preferences(entity_id)
    
    # ترتيب الفئات
    sorted_cats = sorted(all_cats.items(), key=lambda x: x[1].get('order', 0))
    
    buttons = []
    
    # header
    buttons.append([InlineKeyboardButton(f"📋 {entity_name[:30]} - إدارة الفئات", callback_data="none")])
    buttons.append([InlineKeyboardButton("─" * 20, callback_data="none")])
    
    # أزرار الفئات
    for cat_id, cat_data in sorted_cats:
        icon = cat_data.get('icon', '📁')
        name = cat_data.get('name', cat_id)
        is_enabled = preferences.get(cat_id, True)
        status_icon = "✅" if is_enabled else "❌"
        btn_text = f"{status_icon} {icon} {name}"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"toggle_category_{entity_id}_{cat_id}")])
    
    buttons.append([InlineKeyboardButton("─" * 20, callback_data="none")])
    
    # أزرار التفعيل والتعطيل الجماعي
    buttons.append([
        InlineKeyboardButton("✅ تفعيل الكل", callback_data=f"enable_all_cats_{entity_id}"),
        InlineKeyboardButton("❌ تعطيل الكل", callback_data=f"disable_all_cats_{entity_id}")
    ])
    
    buttons.append([InlineKeyboardButton("💾 حفظ وإغلاق", callback_data=f"save_categories_{entity_id}")])
    
    return InlineKeyboardMarkup(buttons)


def build_active_entities_menu(page: int = 0, per_page: int = 10) -> InlineKeyboardMarkup:
    """
    بناء قائمة الكيانات النشطة مع تصفح
    
    Args:
        page: رقم الصفحة الحالية
        per_page: عدد العناصر في الصفحة
    
    Returns:
        InlineKeyboardMarkup
    """
    from entity_manager import get_all_entity_subscriptions
    
    subscribers = get_all_entity_subscriptions()
    entities_list = list(subscribers.values())
    entities_list.sort(key=lambda x: x.get('subscribed_at', ''), reverse=True)
    
    total_pages = (len(entities_list) + per_page - 1) // per_page if entities_list else 1
    start_idx = page * per_page
    end_idx = min(start_idx + per_page, len(entities_list))
    
    buttons = []
    
    # header
    buttons.append([InlineKeyboardButton(f"📡 الكيانات النشطة ({len(entities_list)})", callback_data="none")])
    buttons.append([InlineKeyboardButton("─" * 20, callback_data="none")])
    
    # أزرار الكيانات
    for entity in entities_list[start_idx:end_idx]:
        entity_name = entity.get('entity_name', 'غير معروف')
        entity_id = entity.get('entity_id', '')
        entity_type = "📢" if entity.get('entity_type') == 'channel' else "👥"
        if len(entity_name) > 25:
            entity_name = entity_name[:22] + "..."
        buttons.append([InlineKeyboardButton(f"{entity_type} {entity_name}", callback_data=f"manage_entity_cats_{entity_id}")])
    
    buttons.append([InlineKeyboardButton("─" * 20, callback_data="none")])
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ السابق", callback_data=f"entities_page_{page - 1}"))
    nav_buttons.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="none"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("التالي ▶️", callback_data=f"entities_page_{page + 1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(buttons)


def build_admin_full_control_panel() -> InlineKeyboardMarkup:
    """
    بناء لوحة التحكم الكاملة للمشرف
    
    Returns:
        InlineKeyboardMarkup
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 المتغيرات والإعدادات", callback_data="admin_variables")],
        [InlineKeyboardButton("📝 إدارة النصوص", callback_data="admin_texts")],
        [InlineKeyboardButton("🔘 إدارة الأزرار", callback_data="admin_buttons")],
        [InlineKeyboardButton("🔐 إدارة الصلاحيات", callback_data="admin_permissions")],
        [InlineKeyboardButton("📡 إدارة الكيانات", callback_data="admin_entities")],
        [InlineKeyboardButton("🗄️ إدارة قاعدة البيانات", callback_data="admin_database")],
        [InlineKeyboardButton("📦 تصدير البوت", callback_data="admin_export")],
        [InlineKeyboardButton("⚡ الأحداث والعمليات", callback_data="admin_events")],
        [InlineKeyboardButton("🎁 الهدايا والمكافآت", callback_data="admin_gifts")],
        [InlineKeyboardButton("💰 إدارة التعدين", callback_data="pending_mining")],
        [InlineKeyboardButton("✅ إنهاء الإعداد", callback_data="admin_complete_setup")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ])


def build_admin_panel_button() -> InlineKeyboardMarkup:
    """
    زر لوحة المشرف
    
    Returns:
        InlineKeyboardMarkup
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎛️ لوحة التحكم", callback_data="admin_control")]
    ])