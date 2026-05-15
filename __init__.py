#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
╔══════════════════════════════════════════════════════════════════╗
║                    PACKAGE: NewsBot                             ║
║              تجميع جميع كلاسات ومكتبات البوت                    ║
╚══════════════════════════════════════════════════════════════════╝

هذا الملف يقوم بتجميع جميع المكونات الأساسية للبوت
ليتم استيرادها بسهولة من أي مكان في المشروع
"""

# ==================== الإصدار والمعلومات ====================
__version__ = "6.0.0"
__author__ = "All Arab Services"
__description__ = "Telegram News Bot with Auto-Collector, Mining, Points System"

# ==================== استيراد الكلاسات الأساسية ====================

# إعدادات البوت
from bot_config import BotConfig

# إدارة Firebase
from firebase_core import (
    firebase_get, firebase_set, firebase_push, 
    firebase_update, firebase_delete, 
    cached_firebase, invalidate_cache,
    test_firebase_connection
)

# إدارة المستخدمين
from user_manager import (
    create_user, get_user, update_user, delete_user,
    add_points, deduct_points, get_daily_bonus,
    get_user_stats, get_user_ranking,
    process_referral, get_referral_link,
    is_admin
)

# إدارة الأخبار
from news_manager import (
    add_news, get_news, get_news_list, get_pending_news,
    update_news, approve_news, reject_news, delete_news,
    increment_views, increment_shares, increment_likes, increment_dislikes,
    search_news, get_system_stats
)

# إدارة اللغة والنصوص
from language_manager import LanguageManager, language_manager

# إدارة الكيانات والمشتركين
from entity_manager import (
    add_subscriber, remove_subscriber, get_active_subscribers,
    get_user_subscriptions, add_monitored_entity, remove_monitored_entity,
    get_monitored_entities, update_monitored_entity,
    get_entity_category_preferences, update_entity_category_preferences,
    get_entity_subscription_info, get_all_entity_subscriptions
)

# بناء لوحات المفاتيح
from menu_builder import (
    build_main_menu, build_admin_menu, build_categories_menu,
    build_categories_management_menu, build_active_entities_menu,
    build_news_list_menu, build_news_detail_menu, build_full_news_menu,
    build_settings_menu, build_language_menu, build_theme_menu,
    build_review_menu, build_confirm_menu, build_back_button,
    build_cancel_button, build_pagination_buttons,
    build_reply_keyboard, remove_keyboard, build_force_reply
)

# جامع الأخبار التلقائي
from collector import NewsCollector, news_collector, start_collector, stop_collector

# نظام التعدين
from mining_manager import SessionMiningManager, mining_manager, start_mining, stop_mining

# معالجات الأوامر
from admin_handlers import register_admin_handlers
from callback_handlers import register_callback_handlers
from text_handlers import register_text_handlers

# ==================== دوال مساعدة إضافية ====================

def get_bot_info() -> dict:
    """الحصول على معلومات البوت"""
    return {
        "name": BotConfig.APP_NAME,
        "version": __version__,
        "author": __author__,
        "description": __description__,
        "admin_ids": BotConfig.ADMIN_IDS,
        "bot_username": BotConfig.BOT_USERNAME
    }

def is_bot_ready() -> bool:
    """التحقق من جاهزية البوت"""
    setup_complete = firebase_get("system_config/setup_complete")
    if setup_complete:
        return True
    
    # التحقق من وجود مشرف قام بالتسجيل
    users = firebase_get("users") or {}
    for uid, user_data in users.items():
        if user_data.get('is_admin', False):
            return True
    
    return False

def get_bot_status() -> dict:
    """الحصول على حالة البوت الكاملة"""
    return {
        "ready": is_bot_ready(),
        "version": __version__,
        "uptime": firebase_get("system_config/uptime") or "unknown",
        "total_users": len(firebase_get("users") or {}),
        "total_news": len(firebase_get("news") or {}),
        "active_sessions": len(firebase_get("sessions") or {}),
        "monitored_entities": len(firebase_get("monitored_entities") or {})
    }

# ==================== تصدير جميع المكونات ====================

__all__ = [
    # الإعدادات
    "BotConfig",
    
    # Firebase
    "firebase_get", "firebase_set", "firebase_push", "firebase_update", "firebase_delete",
    "cached_firebase", "invalidate_cache", "test_firebase_connection",
    
    # المستخدمين
    "create_user", "get_user", "update_user", "delete_user",
    "add_points", "deduct_points", "get_daily_bonus",
    "get_user_stats", "get_user_ranking",
    "process_referral", "get_referral_link",
    "is_admin",
    
    # الأخبار
    "add_news", "get_news", "get_news_list", "get_pending_news",
    "update_news", "approve_news", "reject_news", "delete_news",
    "increment_views", "increment_shares", "increment_likes", "increment_dislikes",
    "search_news", "get_system_stats",
    
    # اللغة
    "LanguageManager", "language_manager",
    
    # الكيانات
    "add_subscriber", "remove_subscriber", "get_active_subscribers",
    "get_user_subscriptions", "add_monitored_entity", "remove_monitored_entity",
    "get_monitored_entities", "update_monitored_entity",
    "get_entity_category_preferences", "update_entity_category_preferences",
    "get_entity_subscription_info", "get_all_entity_subscriptions",
    
    # لوحات المفاتيح
    "build_main_menu", "build_admin_menu", "build_categories_menu",
    "build_categories_management_menu", "build_active_entities_menu",
    "build_news_list_menu", "build_news_detail_menu", "build_full_news_menu",
    "build_settings_menu", "build_language_menu", "build_theme_menu",
    "build_review_menu", "build_confirm_menu", "build_back_button",
    "build_cancel_button", "build_pagination_buttons",
    "build_reply_keyboard", "remove_keyboard", "build_force_reply",
    
    # جامع الأخبار
    "NewsCollector", "news_collector", "start_collector", "stop_collector",
    
    # التعدين
    "SessionMiningManager", "mining_manager", "start_mining", "stop_mining",
    
    # المعالجات
    "register_admin_handlers", "register_callback_handlers", "register_text_handlers",
    
    # دوال مساعدة
    "get_bot_info", "is_bot_ready", "get_bot_status"
]

# ==================== طباعة معلومات التجميع (للتأكد فقط) ====================
# ملاحظة: لا شيء يطبع في الكونسول في النسخة النهائية