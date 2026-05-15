#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
╔══════════════════════════════════════════════════════════════════╗
║                  CLASS: CallbackHandlers                        ║
║              معالجات جميع الأزرار والاستدعاءات                  ║
║              يدعم: أخبار، إدارة، تصويت، تمويل، تعدين، إعدادات   ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import urllib.parse
from datetime import datetime
from typing import Dict, List, Optional, Any

from pyrogram import Client
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait

from bot_config import BotConfig
from firebase_core import firebase_get, firebase_set, firebase_update, firebase_delete
from user_manager import is_admin, get_user, get_user_stats, add_points, update_user
from news_manager import (
    get_news, get_news_list, get_pending_news, approve_news, reject_news, 
    delete_news, increment_views, increment_shares, increment_likes, increment_dislikes
)
from menu_builder import (
    build_main_menu, build_admin_menu, build_categories_menu, build_back_button,
    build_categories_management_menu, build_active_entities_menu,
    build_admin_full_control_panel, build_confirm_menu
)
from collector import news_collector
from mining_manager import mining_manager
from language_manager import language_manager


def register_callback_handlers(app: Client):
    """تسجيل جميع معالجات الأزرار"""

    @app.on_callback_query()
    async def handle_callback(client: Client, callback: CallbackQuery):
        """
        المعالج الرئيسي لجميع الأزرار - يوجه الطلبات حسب البادئة
        """
        try:
            data = callback.data
            user_id = callback.from_user.id
            message = callback.message

            await callback.answer()

            # ==================== القائمة الرئيسية ====================

            if data == "back_main":
                await handle_back_main(client, callback, user_id)

            elif data == "admin_panel":
                await handle_admin_panel(client, callback, user_id)

            elif data == "admin_control":
                await handle_admin_control(client, callback, user_id)

            # ==================== الأخبار ====================

            elif data == "latest_news":
                await handle_latest_news(client, callback)

            elif data == "categories":
                await handle_categories_menu(client, callback)

            elif data == "activate_news":
                await handle_activate_news(client, callback)

            elif data == "my_stats":
                await handle_my_stats(client, callback, user_id)

            elif data == "settings":
                await handle_settings_menu(client, callback, user_id)

            elif data == "help":
                await handle_help_menu(client, callback, user_id)

            # ==================== تصفح الأخبار ====================

            elif data.startswith("category_"):
                cat_id = data.replace("category_", "")
                await handle_category_news(client, callback, cat_id)

            elif data.startswith("view_news_"):
                news_id = data.replace("view_news_", "")
                await handle_view_news(client, callback, news_id)

            elif data.startswith("show_full_news_"):
                news_id = data.replace("show_full_news_", "")
                await handle_full_news(client, callback, news_id)

            elif data.startswith("share_news_"):
                news_id = data.replace("share_news_", "")
                await handle_share_news(client, callback, news_id)

            elif data.startswith("like_news_"):
                news_id = data.replace("like_news_", "")
                await handle_like_news(client, callback, news_id)

            elif data.startswith("dislike_news_"):
                news_id = data.replace("dislike_news_", "")
                await handle_dislike_news(client, callback, news_id)

            elif data.startswith("news_page_"):
                page = int(data.replace("news_page_", ""))
                await handle_latest_news(client, callback, page)

            elif data.startswith("filter_category_"):
                cat_id = data.replace("filter_category_", "")
                await handle_category_news(client, callback, cat_id)

            # ==================== إدارة المشرف ====================

            elif data == "review_news":
                await handle_review_news(client, callback, user_id)

            elif data == "admin_stats":
                await handle_admin_stats(client, callback)

            elif data == "broadcast":
                await handle_broadcast_request(client, callback, user_id)

            elif data == "admin_add_service":
                await handle_admin_add_service(client, callback)

            elif data == "admin_add_button":
                await handle_admin_add_button(client, callback, user_id)

            elif data == "admin_add_category":
                await handle_admin_add_category(client, callback, user_id)

            elif data == "admin_manage_buttons":
                await handle_admin_manage_buttons(client, callback)

            elif data == "admin_manage_categories":
                await handle_admin_manage_categories(client, callback)

            elif data == "admin_entities_list":
                await handle_entities_list(client, callback, 0)

            elif data.startswith("entities_page_"):
                page = int(data.replace("entities_page_", ""))
                await handle_entities_list(client, callback, page)

            # ==================== إدارة المتغيرات ====================

            elif data == "admin_variables":
                await handle_admin_variables(client, callback)

            elif data == "admin_add_variable":
                await handle_admin_add_variable(client, callback, user_id)

            elif data.startswith("config_type_"):
                var_type = data.replace("config_type_", "")
                await handle_config_type_selection(client, callback, user_id, var_type)

            # ==================== إدارة النصوص ====================

            elif data == "admin_texts":
                await handle_admin_texts(client, callback)

            elif data == "admin_add_text":
                await handle_admin_add_text(client, callback, user_id)

            # ==================== إدارة الأزرار ====================

            elif data == "admin_buttons":
                await handle_admin_buttons(client, callback)

            elif data == "admin_add_button_quick":
                await handle_admin_add_button(client, callback, user_id)

            elif data.startswith("edit_btn_"):
                action = data.replace("edit_btn_", "")
                await handle_edit_button_action(client, callback, user_id, action)

            elif data == "toggle_btn_visibility":
                await handle_toggle_button_visibility(client, callback, user_id)

            elif data == "delete_btn":
                await handle_delete_button_request(client, callback, user_id)

            # ==================== إدارة الصلاحيات ====================

            elif data == "admin_permissions":
                await handle_admin_permissions(client, callback)

            elif data == "admin_add_permission":
                await handle_admin_add_permission(client, callback, user_id)

            # ==================== إدارة الكيانات ====================

            elif data == "admin_entities":
                await handle_admin_entities(client, callback)

            elif data == "admin_add_entity":
                await handle_admin_add_entity(client, callback, user_id)

            # ==================== إدارة قاعدة البيانات ====================

            elif data == "admin_database":
                await handle_admin_database(client, callback)

            elif data == "db_stats":
                await handle_db_stats(client, callback)

            elif data == "db_backup":
                await handle_db_backup(client, callback)

            elif data == "db_restore":
                await handle_db_restore_menu(client, callback)

            # ==================== تصدير البوت ====================

            elif data == "admin_export":
                await handle_admin_export(client, callback)

            elif data == "export_now":
                await handle_export_now(client, callback, user_id)

            elif data == "export_history":
                await handle_export_history(client, callback)

            # ==================== إدارة الأحداث ====================

            elif data == "admin_events":
                await handle_admin_events(client, callback)

            elif data == "admin_add_event":
                await handle_admin_add_event(client, callback, user_id)

            # ==================== إدارة الهدايا ====================

            elif data == "admin_gifts":
                await handle_admin_gifts(client, callback)

            elif data == "admin_add_gift":
                await handle_admin_add_gift(client, callback, user_id)

            # ==================== إدارة التعدين ====================

            elif data.startswith("approve_mining_"):
                approval_id = data.replace("approve_mining_", "")
                await handle_approve_mining(client, callback, user_id, approval_id)

            elif data.startswith("reject_mining_"):
                approval_id = data.replace("reject_mining_", "")
                await handle_reject_mining(client, callback, user_id, approval_id)

            # ==================== إعدادات المستخدم ====================

            elif data == "toggle_notifications":
                await handle_toggle_notifications(client, callback, user_id)

            elif data == "settings_language":
                await handle_settings_language(client, callback)

            elif data == "settings_theme":
                await handle_settings_theme(client, callback)

            elif data == "show_referral":
                await handle_show_referral(client, callback, user_id)

            elif data.startswith("set_lang_"):
                lang = data.replace("set_lang_", "")
                await handle_set_language(client, callback, user_id, lang)

            elif data.startswith("set_theme_"):
                theme = data.replace("set_theme_", "")
                await handle_set_theme(client, callback, user_id, theme)

            # ==================== إدارة فئات الكيانات ====================

            elif data.startswith("toggle_category_"):
                await handle_toggle_category(client, callback)

            elif data.startswith("enable_all_cats_"):
                await handle_enable_all_categories(client, callback)

            elif data.startswith("disable_all_cats_"):
                await handle_disable_all_categories(client, callback)

            elif data.startswith("save_categories_"):
                await handle_save_categories(client, callback)

            elif data.startswith("manage_entity_cats_"):
                entity_id = data.replace("manage_entity_cats_", "")
                await handle_manage_entity_categories(client, callback, entity_id)

            # ==================== مراجعة الأخبار ====================

            elif data.startswith("approve_news_"):
                news_id = data.replace("approve_news_", "")
                await handle_approve_news(client, callback, user_id, news_id)

            elif data.startswith("reject_news_"):
                news_id = data.replace("reject_news_", "")
                await handle_reject_news(client, callback, user_id, news_id)

            elif data.startswith("delete_news_"):
                news_id = data.replace("delete_news_", "")
                await handle_delete_news(client, callback, user_id, news_id)

            elif data.startswith("edit_news_"):
                news_id = data.replace("edit_news_", "")
                await handle_edit_news(client, callback, user_id, news_id)

            elif data.startswith("review_next_"):
                index = int(data.replace("review_next_", "")) + 1
                await handle_review_navigation(client, callback, user_id, index)

            elif data.startswith("review_prev_"):
                index = int(data.replace("review_prev_", "")) - 1
                await handle_review_navigation(client, callback, user_id, index)

            # ==================== تأكيد الحذف ====================

            elif data.startswith("confirm_delete_config_"):
                var_name = data.replace("confirm_delete_config_", "")
                await handle_confirm_delete_config(client, callback, user_id, var_name)

            elif data.startswith("confirm_delete_button_"):
                btn_id = data.replace("confirm_delete_button_", "")
                await handle_confirm_delete_button(client, callback, user_id, btn_id)

            # ==================== أزرار ديناميكية ====================

            elif data.startswith("dyn_"):
                btn_id = data.replace("dyn_", "")
                await handle_dynamic_button(client, callback, btn_id)

            # ==================== إلغاء وإجراءات عامة ====================

            elif data == "cancel_action":
                await handle_cancel_action(client, callback, user_id)

            elif data == "admin_complete_setup":
                await handle_complete_setup(client, callback, user_id)

            elif data == "refresh_collector":
                await handle_refresh_collector(client, callback)

            elif data == "none":
                pass

            else:
                await callback.answer("⚠️ إجراء غير معروف")

        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception:
            pass

    # ==================== دوال معالجة القائمة الرئيسية ====================

    async def handle_back_main(client: Client, callback: CallbackQuery, user_id: int):
        """العودة إلى القائمة الرئيسية"""
        stats = get_user_stats(user_id)
        user = callback.from_user
        await callback.message.edit_text(
            f"📰 **القائمة الرئيسية**\n\n"
            f"👤 {user.first_name}\n"
            f"🆔 `{user_id}`\n"
            f"💎 {stats['points']} نقطة",
            reply_markup=build_main_menu(user_id),
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_admin_panel(client: Client, callback: CallbackQuery, user_id: int):
        """عرض لوحة المشرف"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        stats = get_system_stats()
        await callback.message.edit_text(
            f"📊 **لوحة المشرف**\n\n"
            f"📰 الأخبار: {stats['total_news']}\n"
            f"⏳ قيد المراجعة: {stats['pending_news']}",
            reply_markup=build_admin_menu(stats['pending_news']),
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_admin_control(client: Client, callback: CallbackQuery, user_id: int):
        """عرض لوحة التحكم الكاملة"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        await callback.message.edit_text(
            "🎛️ **لوحة التحكم الرئيسية**\n\n"
            "استخدم الأزرار أدناه لإدارة جميع إعدادات البوت:",
            reply_markup=build_admin_full_control_panel(),
            parse_mode=ParseMode.MARKDOWN
        )

    # ==================== دوال معالجة الأخبار ====================

    async def handle_latest_news(client: Client, callback: CallbackQuery, page: int = 0):
        """عرض آخر الأخبار"""
        news_list = get_news_list(limit=BotConfig.NEWS_PER_PAGE * 4)

        if not news_list:
            await callback.message.edit_text(
                "📰 لا توجد أخبار متاحة حالياً",
                reply_markup=build_back_button(),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        total_pages = (len(news_list) + BotConfig.NEWS_PER_PAGE - 1) // BotConfig.NEWS_PER_PAGE
        start = page * BotConfig.NEWS_PER_PAGE
        end = start + BotConfig.NEWS_PER_PAGE
        page_news = news_list[start:end]

        text = f"📰 **آخر الأخبار** (صفحة {page + 1}/{total_pages})\n▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
        buttons = []

        for i, news in enumerate(page_news, 1):
            title = news.get('title', 'خبر')[:50]
            cat_id = news.get('category_id', 'general')
            cat_name = firebase_get(f"categories/{cat_id}/name") or 'عام'
            text += f"{i}. **{title}**\n   📂 {cat_name} | 👁 {news.get('views', 0)}\n\n"

        # أزرار التنقل
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("◀️ السابق", callback_data=f"news_page_{page - 1}"))
        nav_buttons.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="none"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("التالي ▶️", callback_data=f"news_page_{page + 1}"))
        if nav_buttons:
            buttons.append(nav_buttons)

        # أزرار الأخبار
        for news in page_news:
            title = news.get('title', 'خبر')[:40]
            buttons.append([InlineKeyboardButton(f"📰 {title}", callback_data=f"view_news_{news.get('id')}")])

        # أزرار الفئات
        categories = firebase_get("categories") or {}
        default_cats = {
            "general": {"name": "عام", "icon": "📰"},
            "politics": {"name": "سياسة", "icon": "🏛️"},
            "economy": {"name": "اقتصاد", "icon": "💰"},
            "sports": {"name": "رياضة", "icon": "⚽"},
            "technology": {"name": "تقنية", "icon": "💻"},
        }
        all_cats = {**default_cats, **categories}
        cat_list = list(all_cats.items())[:9]

        for i in range(0, len(cat_list), 3):
            row = []
            for cat_id, cat_data in cat_list[i:i+3]:
                row.append(InlineKeyboardButton(
                    f"{cat_data.get('icon', '📁')} {cat_data.get('name', cat_id)}",
                    callback_data=f"filter_category_{cat_id}"
                ))
            buttons.append(row)

        buttons.append([InlineKeyboardButton("🔄 رجوع", callback_data="back_main")])

        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_categories_menu(client: Client, callback: CallbackQuery):
        """عرض قائمة الفئات"""
        await callback.message.edit_text(
            "📂 **فئات الأخبار**\n▬▬▬▬▬▬▬▬▬▬▬▬",
            reply_markup=build_categories_menu(),
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_activate_news(client: Client, callback: CallbackQuery):
        """طلب تفعيل الأخبار"""
        await callback.message.delete()
        await callback.message.reply_text(
            "🔔 **لتفعيل الأخبار**\n\n"
            "أرسل يوزر القناة أو المجموعة:\n"
            "مثال: `@channel`\n\n"
            "أو رابط الدعوة:\n"
            "`https://t.me/channel`",
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_my_stats(client: Client, callback: CallbackQuery, user_id: int):
        """عرض إحصائيات المستخدم"""
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
        await callback.message.edit_text(
            text,
            reply_markup=build_back_button(),
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_settings_menu(client: Client, callback: CallbackQuery, user_id: int):
        """عرض قائمة الإعدادات"""
        user = get_user(user_id)
        notifications_enabled = user.get('notifications_enabled', True) if user else True

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{'✅' if notifications_enabled else '❌'} الإشعارات", callback_data="toggle_notifications")],
            [InlineKeyboardButton("🌐 اللغة", callback_data="settings_language")],
            [InlineKeyboardButton("🎨 المظهر", callback_data="settings_theme")],
            [InlineKeyboardButton("🔗 كود الإحالة", callback_data="show_referral")],
            [InlineKeyboardButton("📊 إحصائياتي", callback_data="my_stats")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
        ])

        await callback.message.edit_text(
            "⚙️ **الإعدادات**\n\n"
            "🔔 الإشعارات: " + ("مفعلة" if notifications_enabled else "معطلة") + "\n"
            "🌐 اللغة: العربية\n"
            "🎨 المظهر: داكن",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_help_menu(client: Client, callback: CallbackQuery, user_id: int):
        """عرض قائمة المساعدة"""
        help_text = f"""
❓ **مساعدة بوت {BotConfig.APP_NAME}**

**الأوامر المتاحة:**
• /start - القائمة الرئيسية
• /news - تفعيل الأخبار
• /search [نص] - البحث في الأخبار
• /stats - إحصائيات حسابك
• /daily - المكافأة اليومية
• /activate_mining - تفعيل التعدين

**النقاط والمكافآت:**
• تفعيل قناة/مجموعة: +{BotConfig.POINTS_PER_SUBSCRIBE}
• المكافأة اليومية: +{BotConfig.POINTS_DAILY_BONUS}
• مشاركة خبر: +{BotConfig.POINTS_PER_NEWS_SHARE}
• إحالة مستخدم: +{BotConfig.POINTS_PER_REFERRAL}
"""
        await callback.message.edit_text(
            help_text,
            reply_markup=build_back_button(),
            parse_mode=ParseMode.MARKDOWN
        )

    # ==================== دوال معالجة عرض الأخبار ====================

    async def handle_category_news(client: Client, callback: CallbackQuery, category_id: str, page: int = 0):
        """عرض أخبار فئة محددة"""
        news_list = get_news_list(category=category_id, limit=BotConfig.NEWS_PER_PAGE * 4)
        cat_data = firebase_get(f"categories/{category_id}") or {}
        cat_name = cat_data.get('name', category_id)
        cat_icon = cat_data.get('icon', '📁')

        if not news_list:
            await callback.message.edit_text(
                f"{cat_icon} لا توجد أخبار في فئة **{cat_name}**",
                reply_markup=build_back_button("categories"),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        total_pages = (len(news_list) + BotConfig.NEWS_PER_PAGE - 1) // BotConfig.NEWS_PER_PAGE
        start = page * BotConfig.NEWS_PER_PAGE
        end = start + BotConfig.NEWS_PER_PAGE
        page_news = news_list[start:end]

        text = f"{cat_icon} **{cat_name}** (صفحة {page + 1}/{total_pages})\n▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
        buttons = []

        # أزرار التنقل
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("◀️ السابق", callback_data=f"category_page_{category_id}_{page - 1}"))
        nav_buttons.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="none"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("التالي ▶️", callback_data=f"category_page_{category_id}_{page + 1}"))
        if nav_buttons:
            buttons.append(nav_buttons)

        for i, news in enumerate(page_news, 1):
            title = news.get('title', 'خبر')[:50]
            text += f"{i}. **{title}**\n   👁 {news.get('views', 0)}\n\n"
            buttons.append([InlineKeyboardButton(f"{i}. {title[:40]}", callback_data=f"view_news_{news.get('id')}")])

        buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="categories")])

        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_view_news(client: Client, callback: CallbackQuery, news_id: str):
        """عرض تفاصيل خبر"""
        news = get_news(news_id)

        if not news:
            await callback.answer("الخبر غير متوفر", show_alert=True)
            return

        increment_views(news_id)
        add_points(callback.from_user.id, BotConfig.POINTS_PER_VIEW, "مشاهدة خبر")

        content = news.get('content', 'لا يوجد محتوى')
        if len(content) > BotConfig.MAX_NEWS_LENGTH - 500:
            content = content[:BotConfig.MAX_NEWS_LENGTH - 500] + "..."

        preview = content[:300] + "..." if len(content) > 300 else content

        cat_id = news.get('category_id', 'general')
        cat_name = firebase_get(f"categories/{cat_id}/name") or 'عام'

        text = f"""
📰 **{news.get('title', 'خبر بدون عنوان')}**

▬▬▬▬▬▬▬▬▬▬▬▬
{preview}
▬▬▬▬▬▬▬▬▬▬▬▬

📂 **الفئة:** {cat_name}
📅 **التاريخ:** {news.get('created_at', datetime.now().isoformat())[:10]}
👁 **المشاهدات:** {news.get('views', 0) + 1}
🔄 **المشاركات:** {news.get('shares', 0)}
"""

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 عرض المزيد", callback_data=f"show_full_news_{news_id}")],
            [InlineKeyboardButton("📤 مشاركة", callback_data=f"share_news_{news_id}")],
            [InlineKeyboardButton("👍 إعجاب", callback_data=f"like_news_{news_id}"),
             InlineKeyboardButton("👎 عدم إعجاب", callback_data=f"dislike_news_{news_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="latest_news")]
        ])

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

    async def handle_full_news(client: Client, callback: CallbackQuery, news_id: str):
        """عرض الخبر كاملاً"""
        news = get_news(news_id)

        if not news:
            await callback.answer("الخبر غير متوفر", show_alert=True)
            return

        cat_id = news.get('category_id', 'general')
        cat_name = firebase_get(f"categories/{cat_id}/name") or 'عام'

        text = f"""
📰 **{news.get('title', 'خبر بدون عنوان')}**

▬▬▬▬▬▬▬▬▬▬▬▬
{news.get('content', 'لا يوجد محتوى')}
▬▬▬▬▬▬▬▬▬▬▬▬

📂 **الفئة:** {cat_name}
📅 **التاريخ:** {news.get('created_at', datetime.now().isoformat())[:10]}
👁 **المشاهدات:** {news.get('views', 0)}
🔄 **المشاركات:** {news.get('shares', 0)}
👍 **الإعجابات:** {news.get('likes', 0)} | 👎 **عدم الإعجاب:** {news.get('dislikes', 0)}
"""

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 مشاركة", callback_data=f"share_news_{news_id}")],
            [InlineKeyboardButton("👍 إعجاب", callback_data=f"like_news_{news_id}"),
             InlineKeyboardButton("👎 عدم إعجاب", callback_data=f"dislike_news_{news_id}")],
            [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="latest_news")]
        ])

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

    async def handle_share_news(client: Client, callback: CallbackQuery, news_id: str):
        """مشاركة خبر"""
        news = get_news(news_id)

        if not news:
            await callback.answer("الخبر غير متوفر", show_alert=True)
            return

        increment_shares(news_id)
        add_points(callback.from_user.id, BotConfig.POINTS_PER_NEWS_SHARE, "مشاركة خبر")

        share_text = f"📰 {news.get('title', 'خبر')}\n\n{news.get('content', '')[:200]}..."
        share_url = f"https://t.me/share/url?url={urllib.parse.quote(share_text)}"

        await callback.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 مشاركة عبر تيليجرام", url=share_url)],
                [InlineKeyboardButton("🔙 رجوع", callback_data=f"view_news_{news_id}")]
            ])
        )

        await callback.answer(f"💎 +{BotConfig.POINTS_PER_NEWS_SHARE} نقطة", show_alert=True)

    async def handle_like_news(client: Client, callback: CallbackQuery, news_id: str):
        """إعجاب بخبر"""
        increment_likes(news_id)
        add_points(callback.from_user.id, 1, "إعجاب بخبر")
        await callback.answer("👍 تم الإعجاب! +1 نقطة", show_alert=True)

    async def handle_dislike_news(client: Client, callback: CallbackQuery, news_id: str):
        """عدم إعجاب بخبر"""
        increment_dislikes(news_id)
        await callback.answer("👎 تم تسجيل عدم الإعجاب", show_alert=True)

    # ==================== دوال معالجة إدارة المشرف ====================

    async def handle_admin_variables(client: Client, callback: CallbackQuery):
        """عرض إدارة المتغيرات"""
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        variables = firebase_get("system_registry/variables") or {}
        text = "📊 **المتغيرات والإعدادات**\n\n"

        for var_name, var_data in list(variables.items())[:20]:
            value = var_data.get('value', 'N/A')
            text += f"• `{var_name}` = `{value}`\n"

        if len(variables) > 20:
            text += f"\n📊 إجمالي المتغيرات: {len(variables)}"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة متغير", callback_data="admin_add_variable")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_control")]
        ])

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

    async def handle_admin_add_variable(client: Client, callback: CallbackQuery, user_id: int):
        """طلب إضافة متغير جديد"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        firebase_set(f"admin_state/{user_id}", {"action": "waiting_config_value"})

        await callback.message.edit_text(
            "📝 **إضافة متغير جديد**\n\n"
            "أدخل اسم المتغير (بالحروف الكبيرة):\n"
            "مثال: `POINTS_PER_REFERRAL`",
            reply_markup=build_cancel_button(),
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_config_type_selection(client: Client, callback: CallbackQuery, user_id: int, var_type: str):
        """معالجة اختيار نوع المتغير"""
        state = firebase_get(f"admin_state/{user_id}")
        if not state or state.get("action") != "waiting_config_value":
            await callback.answer("❌ انتهت الجلسة", show_alert=True)
            return

        var_name = state.get("var_name")
        if not var_name:
            await callback.answer("❌ خطأ", show_alert=True)
            return

        firebase_update(f"admin_state/{user_id}", {"var_type": var_type})

        await callback.message.edit_text(
            f"📝 **متغير:** `{var_name}`\n"
            f"📌 **النوع:** {var_type}\n\n"
            f"**أدخل قيمة المتغير:**",
            reply_markup=build_cancel_button(),
            parse_mode=ParseMode.MARKDOWN
        )

    # ==================== دوال معالجة إدارة النصوص ====================

    async def handle_admin_texts(client: Client, callback: CallbackQuery):
        """عرض إدارة النصوص"""
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        texts = firebase_get("system_registry/texts") or {}
        text = "📝 **النصوص القابلة للتعديل**\n\n"

        for text_id, text_data in list(texts.items())[:20]:
            desc = text_data.get('description', '')
            text += f"• `{text_id}` - {desc}\n"

        if len(texts) > 20:
            text += f"\n📊 إجمالي النصوص: {len(texts)}"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة نص", callback_data="admin_add_text")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_control")]
        ])

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

    async def handle_admin_add_text(client: Client, callback: CallbackQuery, user_id: int):
        """طلب إضافة نص جديد"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        firebase_set(f"admin_state/{user_id}", {"action": "waiting_text_content"})

        await callback.message.edit_text(
            "📝 **إضافة نص جديد**\n\n"
            "أدخل معرف النص (بالحروف الصغيرة والشرطات):\n"
            "مثال: `welcome_message`",
            reply_markup=build_cancel_button(),
            parse_mode=ParseMode.MARKDOWN
        )

    # ==================== دوال معالجة إدارة الأزرار ====================

    async def handle_admin_buttons(client: Client, callback: CallbackQuery):
        """عرض إدارة الأزرار"""
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        buttons = firebase_get("dynamic_buttons") or {}
        text = "🔘 **الأزرار الديناميكية**\n\n"

        for btn_id, btn_data in list(buttons.items())[:20]:
            btn_text = btn_data.get('text_ar', 'زر')
            is_hidden = btn_data.get('is_hidden', False)
            status = "👁️ مخفي" if is_hidden else "👁️ ظاهر"
            text += f"• `{btn_id}` - {btn_text} ({status})\n"

        if len(buttons) > 20:
            text += f"\n📊 إجمالي الأزرار: {len(buttons)}"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة زر", callback_data="admin_add_button_quick")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_control")]
        ])

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

    async def handle_admin_add_button(client: Client, callback: CallbackQuery, user_id: int):
        """طلب إضافة زر جديد"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        firebase_set(f"admin_state/{user_id}", {"action": "waiting_btn_name"})

        await callback.message.edit_text(
            "🔘 **إضافة زر جديد**\n\n"
            "**أدخل النص الذي سيظهر على الزر:**\n"
            "مثال: `💰 تمويل القناة`",
            reply_markup=build_cancel_button(),
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_edit_button_action(client: Client, callback: CallbackQuery, user_id: int, action: str):
        """معالجة إجراءات تعديل الزر"""
        state = firebase_get(f"admin_state/{user_id}")
        if not state or state.get("action") != "waiting_edit_btn":
            await callback.answer("❌ انتهت الجلسة", show_alert=True)
            return

        btn_id = state.get("btn_id")

        if action == "text":
            firebase_update(f"admin_state/{user_id}", {"action": "waiting_edit_btn_text"})
            await callback.message.edit_text(
                f"✏️ **تعديل نص الزر** `{btn_id}`\n\n"
                f"أدخل النص الجديد للزر:",
                reply_markup=build_cancel_button(),
                parse_mode=ParseMode.MARKDOWN
            )
        elif action == "msg":
            firebase_update(f"admin_state/{user_id}", {"action": "waiting_edit_btn_msg"})
            await callback.message.edit_text(
                f"✏️ **تعديل محتوى الزر** `{btn_id}`\n\n"
                f"أدخل المحتوى الجديد للرسالة:",
                reply_markup=build_cancel_button(),
                parse_mode=ParseMode.MARKDOWN
            )

    async def handle_toggle_button_visibility(client: Client, callback: CallbackQuery, user_id: int):
        """تبديل حالة إخفاء/إظهار الزر"""
        state = firebase_get(f"admin_state/{user_id}")
        if not state or state.get("action") != "waiting_edit_btn":
            await callback.answer("❌ انتهت الجلسة", show_alert=True)
            return

        btn_id = state.get("btn_id")
        btn_data = state.get("btn_data", {})
        current_hidden = btn_data.get('is_hidden', False)

        update_dynamic_button(btn_id, {"is_hidden": not current_hidden})

        await callback.answer(
            f"✅ تم {'إخفاء' if not current_hidden else 'إظهار'} الزر",
            show_alert=True
        )

        # تحديث القائمة
        await handle_admin_buttons(client, callback)

    async def handle_delete_button_request(client: Client, callback: CallbackQuery, user_id: int):
        """طلب حذف زر (مع تأكيد)"""
        state = firebase_get(f"admin_state/{user_id}")
        if not state or state.get("action") != "waiting_edit_btn":
            await callback.answer("❌ انتهت الجلسة", show_alert=True)
            return

        btn_id = state.get("btn_id")

        await callback.message.edit_text(
            f"⚠️ **تأكيد حذف الزر**\n\n"
            f"`{btn_id}`\n\n"
            f"هل أنت متأكد من رغبتك في حذف هذا الزر؟",
            reply_markup=build_confirm_menu("delete_button", btn_id),
            parse_mode=ParseMode.MARKDOWN
        )

    # ==================== دوال معالجة إدارة الصلاحيات ====================

    async def handle_admin_permissions(client: Client, callback: CallbackQuery):
        """عرض إدارة الصلاحيات"""
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        permissions = firebase_get("system_registry/permissions") or {}
        text = "🔐 **الصلاحيات المتاحة**\n\n"

        for perm_id, perm_data in permissions.items():
            desc = perm_data.get('description', '')
            text += f"• `{perm_id}` - {desc}\n"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة صلاحية", callback_data="admin_add_permission")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_control")]
        ])

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

    async def handle_admin_add_permission(client: Client, callback: CallbackQuery, user_id: int):
        """طلب إضافة صلاحية جديدة"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        firebase_set(f"admin_state/{user_id}", {"action": "waiting_perm_id"})

        await callback.message.edit_text(
            "🔐 **إضافة صلاحية جديدة**\n\n"
            "أدخل معرف الصلاحية (بالحروف الصغيرة):\n"
            "مثال: `premium_only`",
            reply_markup=build_cancel_button(),
            parse_mode=ParseMode.MARKDOWN
        )

    # ==================== دوال معالجة إدارة الكيانات ====================

    async def handle_admin_entities(client: Client, callback: CallbackQuery):
        """عرض إدارة الكيانات"""
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        monitored = firebase_get("monitored_entities") or {}
        text = "📡 **الكيانات المراقبة**\n\n"

        for entity_id, entity_data in list(monitored.items())[:20]:
            username = entity_data.get('username', 'N/A')
            status = "✅" if entity_data.get('status') == 'active' else "❌"
            text += f"{status} `{entity_id}` - {username}\n"

        if len(monitored) > 20:
            text += f"\n📊 إجمالي الكيانات: {len(monitored)}"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة كيان", callback_data="admin_add_entity")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_control")]
        ])

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

    async def handle_admin_add_entity(client: Client, callback: CallbackQuery, user_id: int):
        """طلب إضافة كيان جديد للمراقبة"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        firebase_set(f"admin_state/{user_id}", {"action": "waiting_entity_username"})

        await callback.message.edit_text(
            "📡 **إضافة كيان للمراقبة**\n\n"
            "أدخل @username الخاص بالكيان:\n"
            "مثال: `@news_channel`",
            reply_markup=build_cancel_button(),
            parse_mode=ParseMode.MARKDOWN
        )

    # ==================== دوال معالجة قاعدة البيانات ====================

    async def handle_admin_database(client: Client, callback: CallbackQuery):
        """عرض إدارة قاعدة البيانات"""
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 إحصائيات قاعدة البيانات", callback_data="db_stats")],
            [InlineKeyboardButton("💾 إنشاء نسخة احتياطية", callback_data="db_backup")],
            [InlineKeyboardButton("🔄 استعادة نسخة", callback_data="db_restore")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_control")]
        ])

        await callback.message.edit_text(
            "🗄️ **إدارة قاعدة البيانات**\n\nاختر الإجراء المطلوب:",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_db_stats(client: Client, callback: CallbackQuery):
        """عرض إحصائيات قاعدة البيانات"""
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

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
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_database")]
        ])

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

    async def handle_db_backup(client: Client, callback: CallbackQuery):
        """إنشاء نسخة احتياطية"""
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        await callback.message.edit_text(
            "⏳ **جاري إنشاء النسخة الاحتياطية...**",
            parse_mode=ParseMode.MARKDOWN
        )

        try:
            backup_data = {
                "backup_time": datetime.now().isoformat(),
                "created_by": callback.from_user.id,
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

            backup_id = f"backup_{int(datetime.now().timestamp())}"
            firebase_set(f"backups/{backup_id}", backup_data)

            # إرسال الملف
            import tempfile
            import json
            import os

            json_data = json.dumps(backup_data, ensure_ascii=False, indent=2, default=str)

            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
                f.write(json_data)
                temp_path = f.name

            await client.send_document(
                callback.from_user.id,
                temp_path,
                caption=f"💾 **نسخة احتياطية**\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n🆔 `{backup_id}`",
                parse_mode=ParseMode.MARKDOWN
            )

            os.unlink(temp_path)

            await callback.message.edit_text(
                f"✅ **تم إنشاء النسخة الاحتياطية بنجاح!**\n\n"
                f"🆔 المعرف: `{backup_id}`",
                reply_markup=build_back_button("admin_database"),
                parse_mode=ParseMode.MARKDOWN
            )

        except Exception as e:
            await callback.message.edit_text(
                f"❌ فشل إنشاء النسخة الاحتياطية: {str(e)[:100]}",
                reply_markup=build_back_button("admin_database"),
                parse_mode=ParseMode.MARKDOWN
            )

    async def handle_db_restore_menu(client: Client, callback: CallbackQuery):
        """عرض قائمة النسخ الاحتياطية للاستعادة"""
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        backups = firebase_get("backups") or {}

        if not backups:
            await callback.message.edit_text(
                "📋 **لا توجد نسخ احتياطية**",
                reply_markup=build_back_button("admin_database"),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        text = "💾 **النسخ الاحتياطية المتاحة**\n\n"
        buttons = []

        for backup_id, backup_data in list(backups.items())[-10:]:
            timestamp = backup_data.get('backup_time', '')[:19]
            text += f"• `{backup_id}` - {timestamp}\n"
            buttons.append([InlineKeyboardButton(f"📂 {backup_id[:20]}", callback_data=f"restore_backup_{backup_id}")])

        buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_database")])

        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.MARKDOWN
        )

    # ==================== دوال معالجة التصدير ====================

    async def handle_admin_export(client: Client, callback: CallbackQuery):
        """عرض إدارة التصدير"""
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔽 تصدير النسخة الحالية", callback_data="export_now")],
            [InlineKeyboardButton("📋 عرض سجل التصدير", callback_data="export_history")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_control")]
        ])

        await callback.message.edit_text(
            "📦 **تصدير البوت**\n\n"
            "يمكنك تحميل نسخة كاملة من البوت مع جميع الإعدادات.\n\n"
            "⚠️ تحتوي النسخة على مفاتيح API الخاصة بك.",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_export_now(client: Client, callback: CallbackQuery, user_id: int):
        """تصدير البوت الآن"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        await callback.message.edit_text(
            "🔽 **جاري تصدير كود البوت...**\n\n"
            "سيتم إرسال الملف خلال لحظات.",
            parse_mode=ParseMode.MARKDOWN
        )

        from admin_handlers import export_bot_script
        await export_bot_script(client, callback.message)

    async def handle_export_history(client: Client, callback: CallbackQuery):
        """عرض سجل التصدير"""
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        exports = firebase_get("export_history") or {}
        text = "📋 **سجل التصدير**\n\n"

        for exp_id, exp_data in list(exports.items())[-10:]:
            timestamp = exp_data.get('timestamp', '')[:19]
            exported_by = exp_data.get('user_id', 'غير معروف')
            text += f"• {timestamp} - بواسطة `{exported_by}`\n"

        if not exports:
            text += "لا توجد سجلات تصدير"

        await callback.message.edit_text(
            text,
            reply_markup=build_back_button("admin_export"),
            parse_mode=ParseMode.MARKDOWN
        )

    # ==================== دوال معالجة الأحداث ====================

    async def handle_admin_events(client: Client, callback: CallbackQuery):
        """عرض إدارة الأحداث"""
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        events = firebase_get("system_registry/events") or {}
        text = "⚡ **الأحداث والعمليات**\n\n"

        for event_id, event_data in events.items():
            active = "✅" if event_data.get('active', True) else "❌"
            desc = event_data.get('description', '')
            text += f"{active} `{event_id}` - {desc}\n"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة حدث", callback_data="admin_add_event")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_control")]
        ])

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

    async def handle_admin_add_event(client: Client, callback: CallbackQuery, user_id: int):
        """طلب إضافة حدث جديد"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        firebase_set(f"admin_state/{user_id}", {"action": "waiting_event_id"})

        await callback.message.edit_text(
            "⚡ **إضافة حدث جديد**\n\n"
            "أدخل معرف الحدث:\n"
            "مثال: `on_user_register`",
            reply_markup=build_cancel_button(),
            parse_mode=ParseMode.MARKDOWN
        )

    # ==================== دوال معالجة الهدايا ====================

    async def handle_admin_gifts(client: Client, callback: CallbackQuery):
        """عرض إدارة الهدايا"""
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        gifts = firebase_get("gifts") or {}
        text = "🎁 **الهدايا والمكافآت**\n\n"

        for gift_id, gift_data in gifts.items():
            gift_type = gift_data.get('type', 'unknown')
            amount = gift_data.get('amount', 0)
            text += f"• `{gift_id}` - {gift_type}: {amount}\n"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة هدية", callback_data="admin_add_gift")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_control")]
        ])

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

    async def handle_admin_add_gift(client: Client, callback: CallbackQuery, user_id: int):
        """طلب إضافة هدية جديدة"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        firebase_set(f"admin_state/{user_id}", {"action": "waiting_gift_id"})

        await callback.message.edit_text(
            "🎁 **إضافة هدية جديدة**\n\n"
            "أدخل معرف الهدية (بالحروف الصغيرة والشرطات):\n"
            "مثال: `welcome_bonus`",
            reply_markup=build_cancel_button(),
            parse_mode=ParseMode.MARKDOWN
        )

    # ==================== دوال معالجة التعدين ====================

    async def handle_approve_mining(client: Client, callback: CallbackQuery, user_id: int, approval_id: str):
        """الموافقة على طلب تعدين"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        success, msg = await mining_manager.approve_mining_session(approval_id, user_id, client)

        if success:
            await callback.answer("✅ تمت الموافقة وتفعيل التعدين", show_alert=True)
            await callback.message.edit_text(
                f"✅ {msg}\n\nتم التفعيل بنجاح.",
                reply_markup=build_back_button("admin_control"),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await callback.answer("❌ فشل التفعيل", show_alert=True)
            await callback.message.edit_text(
                f"❌ {msg}",
                reply_markup=build_back_button("admin_control"),
                parse_mode=ParseMode.MARKDOWN
            )

    async def handle_reject_mining(client: Client, callback: CallbackQuery, user_id: int, approval_id: str):
        """رفض طلب تعدين"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        success, msg = await mining_manager.reject_mining_session(approval_id, user_id, client)

        if success:
            await callback.answer("✅ تم رفض طلب التعدين", show_alert=True)
            await callback.message.edit_text(
                f"✅ {msg}",
                reply_markup=build_back_button("admin_control"),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await callback.answer("❌ فشل الرفض", show_alert=True)

    # ==================== دوال معالجة إعدادات المستخدم ====================

    async def handle_toggle_notifications(client: Client, callback: CallbackQuery, user_id: int):
        """تبديل حالة الإشعارات"""
        user = get_user(user_id)
        if user:
            current = user.get('notifications_enabled', True)
            update_user(user_id, {'notifications_enabled': not current})
            await callback.answer(f"🔔 {'تم التفعيل' if not current else 'تم التعطيل'}", show_alert=True)

        await handle_settings_menu(client, callback, user_id)

    async def handle_settings_language(client: Client, callback: CallbackQuery):
        """عرض قائمة اللغات"""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇸🇦 العربية", callback_data="set_lang_ar")],
            [InlineKeyboardButton("🇬🇧 English", callback_data="set_lang_en")],
            [InlineKeyboardButton("🇫🇷 Français", callback_data="set_lang_fr")],
            [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="set_lang_de")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="settings")]
        ])

        await callback.message.edit_text(
            "🌐 **اختر اللغة:**",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_settings_theme(client: Client, callback: CallbackQuery):
        """عرض قائمة المظاهر"""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌙 داكن", callback_data="set_theme_dark")],
            [InlineKeyboardButton("☀️ فاتح", callback_data="set_theme_light")],
            [InlineKeyboardButton("🔵 أزرق", callback_data="set_theme_blue")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="settings")]
        ])

        await callback.message.edit_text(
            "🎨 **اختر المظهر:**",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_show_referral(client: Client, callback: CallbackQuery, user_id: int):
        """عرض رابط الإحالة"""
        stats = get_user_stats(user_id)
        bot_usr = BotConfig.BOT_USERNAME.replace('@', '')
        ref_url = f"https://t.me/{bot_usr}?start={stats['referral_code']}"

        text = f"""
🔗 **رابط الدعوة الخاص بك:**

`{ref_url}`

📢 شارك هذا الرابط مع أصدقائك!
💎 ستحصل على {BotConfig.POINTS_PER_REFERRAL} نقطة
🎁 صديقك سيحصل على {BotConfig.POINTS_VERIFICATION_REWARD} نقطة عند التسجيل عبر رابطك!
"""

        await callback.message.edit_text(
            text,
            reply_markup=build_back_button("settings"),
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_set_language(client: Client, callback: CallbackQuery, user_id: int, lang: str):
        """تعيين لغة المستخدم"""
        update_user(user_id, {'language': lang})
        await callback.answer(f"🌐 تم تغيير اللغة إلى {lang}", show_alert=True)
        await handle_settings_menu(client, callback, user_id)

    async def handle_set_theme(client: Client, callback: CallbackQuery, user_id: int, theme: str):
        """تعيين مظهر المستخدم"""
        user = get_user(user_id)
        if user:
            settings = user.get('settings', {})
            settings['theme'] = theme
            update_user(user_id, {'settings': settings})
        await callback.answer(f"🎨 تم تغيير المظهر إلى {theme}", show_alert=True)
        await handle_settings_menu(client, callback, user_id)

    # ==================== دوال معالجة إدارة فئات الكيانات ====================

    async def handle_toggle_category(client: Client, callback: CallbackQuery):
        """تبديل حالة فئة لكيان معين"""
        try:
            parts = callback.data.split("_")
            if len(parts) >= 4:
                entity_id = "_".join(parts[2:-1])
                category_id = parts[-1]
            else:
                await callback.answer("❌ خطأ في البيانات", show_alert=True)
                return

            preferences = get_entity_category_preferences(entity_id)
            current_status = preferences.get(category_id, True)
            update_entity_category_preferences(entity_id, category_id, not current_status)

            subscriber = firebase_get(f"subscribers/{entity_id}")
            entity_name = subscriber.get('entity_name', 'الكيان') if subscriber else 'الكيان'

            await callback.message.edit_text(
                f"✅ **تم تحديث إعدادات الفئات بنجاح!**\n\n"
                f"📋 **الكيان:** {entity_name}\n"
                f"🆔 **المعرف:** `{entity_id}`\n\n"
                f"📂 **القائمة المحدثة:**",
                reply_markup=build_categories_management_menu(entity_id, entity_name),
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer("✅ تم تحديث إعدادات الفئة", show_alert=False)
        except Exception:
            await callback.answer("❌ حدث خطأ", show_alert=True)

    async def handle_enable_all_categories(client: Client, callback: CallbackQuery):
        """تفعيل جميع الفئات لكيان"""
        try:
            entity_id = callback.data.replace("enable_all_cats_", "")
            categories = firebase_get("categories") or {}
            default_cats = ["general", "politics", "economy", "sports", "technology", "health"]

            for cat_id in list(categories.keys()) + default_cats:
                update_entity_category_preferences(entity_id, cat_id, True)

            subscriber = firebase_get(f"subscribers/{entity_id}")
            entity_name = subscriber.get('entity_name', 'الكيان') if subscriber else 'الكيان'

            await callback.message.edit_text(
                f"✅ **تم تفعيل جميع الفئات!**\n\n"
                f"📋 **الكيان:** {entity_name}\n"
                f"🆔 **المعرف:** `{entity_id}`\n\n"
                f"📂 **القائمة المحدثة:**",
                reply_markup=build_categories_management_menu(entity_id, entity_name),
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer("✅ تم تفعيل جميع الفئات", show_alert=False)
        except Exception:
            await callback.answer("❌ حدث خطأ", show_alert=True)

    async def handle_disable_all_categories(client: Client, callback: CallbackQuery):
        """تعطيل جميع الفئات لكيان"""
        try:
            entity_id = callback.data.replace("disable_all_cats_", "")
            categories = firebase_get("categories") or {}
            default_cats = ["general", "politics", "economy", "sports", "technology", "health"]

            for cat_id in list(categories.keys()) + default_cats:
                update_entity_category_preferences(entity_id, cat_id, False)

            subscriber = firebase_get(f"subscribers/{entity_id}")
            entity_name = subscriber.get('entity_name', 'الكيان') if subscriber else 'الكيان'

            await callback.message.edit_text(
                f"⚠️ **تم تعطيل جميع الفئات!**\n\n"
                f"📋 **الكيان:** {entity_name}\n"
                f"🆔 **المعرف:** `{entity_id}`\n\n"
                f"📂 **لن يتم إرسال أي أخبار حتى تقوم بتفعيل بعض الفئات**\n\n"
                f"**القائمة الحالية:**",
                reply_markup=build_categories_management_menu(entity_id, entity_name),
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer("⚠️ تم تعطيل جميع الفئات", show_alert=False)
        except Exception:
            await callback.answer("❌ حدث خطأ", show_alert=True)

    async def handle_save_categories(client: Client, callback: CallbackQuery):
        """حفظ إعدادات الفئات والعودة للقائمة"""
        try:
            entity_id = callback.data.replace("save_categories_", "")
            subscriber = firebase_get(f"subscribers/{entity_id}")
            entity_name = subscriber.get('entity_name', 'الكيان') if subscriber else 'الكيان'
            user_id = int(subscriber.get('user_id', 0)) if subscriber else 0
            preferences = firebase_get(f"entity_categories/{entity_id}") or {}
            enabled_cats = [cat_id for cat_id, enabled in preferences.items() if enabled]

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

            summary = f"""
✅ **تم حفظ إعدادات الفئات بنجاح!**

📋 **الكيان:** {entity_name}
📊 **الفئات المفعّلة:** {len(enabled_cats)}/{len(all_cats)}

**الفئات المستلمة:**
"""
            for cat_id in enabled_cats[:10]:
                cat_info = all_cats.get(cat_id, {"name": cat_id, "icon": "📁"})
                summary += f"• {cat_info.get('icon', '📁')} {cat_info.get('name', cat_id)}\n"

            if len(enabled_cats) > 10:
                summary += f"• ... و{len(enabled_cats) - 10} فئة أخرى"

            summary += "\n🔔 سيتم إرسال الأخبار من هذه الفئات فقط تلقائياً"

            if user_id:
                await callback.message.edit_text(
                    summary,
                    reply_markup=build_main_menu(user_id),
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await callback.message.edit_text(
                    summary,
                    reply_markup=build_back_button(),
                    parse_mode=ParseMode.MARKDOWN
                )

            await callback.answer("✅ تم حفظ إعدادات الفئات", show_alert=False)
        except Exception:
            await callback.answer("❌ حدث خطأ", show_alert=True)

    async def handle_manage_entity_categories(client: Client, callback: CallbackQuery, entity_id: str):
        """عرض إدارة فئات كيان محدد"""
        try:
            subscriber = firebase_get(f"subscribers/{entity_id}")
            if not subscriber:
                await callback.answer("❌ الكيان غير موجود", show_alert=True)
                return
            entity_name = subscriber.get('entity_name', 'الكيان')

            await callback.message.edit_text(
                f"📂 **إدارة فئات الكيان:**\n\n"
                f"📋 **{entity_name}**\n"
                f"🆔 `{entity_id}`\n\n"
                f"اختر الفئات التي تريد تفعيلها لهذا الكيان:",
                reply_markup=build_categories_management_menu(entity_id, entity_name),
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer()
        except Exception:
            await callback.answer("❌ حدث خطأ", show_alert=True)

    async def handle_entities_list(client: Client, callback: CallbackQuery, page: int):
        """عرض قائمة الكيانات النشطة"""
        await callback.message.edit_text(
            "📡 **الكيانات النشطة**\n\nاختر كياناً لإدارة فئاته:",
            reply_markup=build_active_entities_menu(page),
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()

    # ==================== دوال معالجة مراجعة الأخبار ====================

    async def handle_review_news(client: Client, callback: CallbackQuery, user_id: int):
        """بدء مراجعة الأخبار المعلقة"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        pending = get_pending_news()

        if not pending:
            await callback.message.edit_text(
                "✅ **لا توجد أخبار قيد المراجعة**",
                reply_markup=build_back_button("admin_panel"),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        firebase_set(f"review_navigation/{user_id}", {
            "news_list": pending,
            "current_index": 0,
            "total": len(pending)
        })

        await show_review_news(client, callback, pending, 0)

    async def handle_approve_news(client: Client, callback: CallbackQuery, user_id: int, news_id: str):
        """الموافقة على خبر"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        approve_news(news_id, user_id)
        await broadcast_news_to_subscribers(client, news_id)

        await callback.answer("✅ تمت الموافقة والنشر", show_alert=True)

        nav = firebase_get(f"review_navigation/{user_id}")
        if nav:
            pending = nav.get("news_list", [])
            current_idx = nav.get("current_index", 0)
            await show_review_news(client, callback, pending, current_idx + 1)
        else:
            await callback.message.edit_text(
                "✅ تمت المراجعة",
                reply_markup=build_back_button("admin_panel"),
                parse_mode=ParseMode.MARKDOWN
            )

    async def handle_reject_news(client: Client, callback: CallbackQuery, user_id: int, news_id: str):
        """رفض خبر"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        reject_news(news_id, user_id, "مرفوض من المشرف")
        await callback.answer("❌ تم رفض الخبر", show_alert=True)

        nav = firebase_get(f"review_navigation/{user_id}")
        if nav:
            pending = nav.get("news_list", [])
            current_idx = nav.get("current_index", 0)
            await show_review_news(client, callback, pending, current_idx + 1)
        else:
            await callback.message.edit_text(
                "✅ تمت المراجعة",
                reply_markup=build_back_button("admin_panel"),
                parse_mode=ParseMode.MARKDOWN
            )

    async def handle_delete_news(client: Client, callback: CallbackQuery, user_id: int, news_id: str):
        """حذف خبر"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        delete_news(news_id)
        await callback.answer("🗑️ تم حذف الخبر", show_alert=True)

        nav = firebase_get(f"review_navigation/{user_id}")
        if nav:
            pending = nav.get("news_list", [])
            current_idx = nav.get("current_index", 0)
            await show_review_news(client, callback, pending, current_idx + 1)

    async def handle_edit_news(client: Client, callback: CallbackQuery, user_id: int, news_id: str):
        """بدء تعديل خبر"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        firebase_set(f"admin_state/{user_id}", {"action": "editing_news", "news_id": news_id})
        await callback.message.edit_text(
            "✏️ **أرسل المحتوى الجديد للخبر:**\n\n"
            "سيتم استخراج العنوان تلقائياً من أول سطر.",
            reply_markup=build_cancel_button(),
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_review_navigation(client: Client, callback: CallbackQuery, user_id: int, index: int):
        """التنقل بين أخبار المراجعة"""
        nav = firebase_get(f"review_navigation/{user_id}")
        if nav:
            pending = nav.get("news_list", [])
            if 0 <= index < len(pending):
                await show_review_news(client, callback, pending, index)
            else:
                await callback.message.edit_text(
                    "✅ **تمت مراجعة جميع الأخبار**",
                    reply_markup=build_back_button("admin_panel"),
                    parse_mode=ParseMode.MARKDOWN
                )
                firebase_delete(f"review_navigation/{user_id}")

    # ==================== دوال معالجة التأكيد ====================

    async def handle_confirm_delete_config(client: Client, callback: CallbackQuery, user_id: int, var_name: str):
        """تأكيد حذف متغير"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        firebase_delete(f"system_registry/variables/{var_name}")
        firebase_delete(f"admin_state/{user_id}")

        await callback.answer("✅ تم حذف المتغير", show_alert=True)
        await handle_admin_variables(client, callback)

    async def handle_confirm_delete_button(client: Client, callback: CallbackQuery, user_id: int, btn_id: str):
        """تأكيد حذف زر"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        firebase_delete(f"dynamic_buttons/{btn_id}")
        firebase_delete(f"admin_state/{user_id}")

        await callback.answer("✅ تم حذف الزر", show_alert=True)
        await handle_admin_buttons(client, callback)

    # ==================== دوال معالجة الأزرار الديناميكية ====================

    async def handle_dynamic_button(client: Client, callback: CallbackQuery, btn_id: str):
        """عرض محتوى زر ديناميكي"""
        btn_data = firebase_get(f"dynamic_buttons/{btn_id}")
        if btn_data:
            msg = btn_data.get('msg_ar', 'محتوى الخدمة')
            await callback.message.edit_text(
                msg,
                reply_markup=build_back_button(),
                parse_mode=ParseMode.MARKDOWN
            )

    # ==================== دوال معالجة عامة ====================

    async def handle_cancel_action(client: Client, callback: CallbackQuery, user_id: int):
        """إلغاء العملية الحالية"""
        firebase_delete(f"admin_state/{user_id}")
        firebase_delete(f"review_navigation/{user_id}")
        firebase_delete(f"mining_state/{user_id}")
        await callback.message.delete()
        await callback.answer("❌ تم الإلغاء")

    async def handle_admin_stats(client: Client, callback: CallbackQuery):
        """عرض إحصائيات النظام"""
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        stats = get_system_stats()
        collector_stats = await news_collector.get_collector_stats()

        text = f"""
📊 **إحصائيات المنظومة**

📰 **الأخبار:**
• إجمالي الأخبار: {stats['total_news']}
• المنشورة: {stats['approved_news']}
• قيد المراجعة: {stats['pending_news']}

👥 **المستخدمين والمشتركين:**
• إجمالي المستخدمين: {stats['total_users']}
• المشتركين النشطين: {stats['total_subscribers']}

📡 **جامع الأخبار:**
• الجلسات النشطة: {collector_stats.get('active_sessions', 0)}
• الكيانات المراقبة: {collector_stats.get('monitored_entities', 0)}
• إجمالي المستخرج: {collector_stats.get('total_extracted', 0)}

📅 **آخر تحديث:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        await callback.message.edit_text(
            text,
            reply_markup=build_back_button("admin_panel"),
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_broadcast_request(client: Client, callback: CallbackQuery, user_id: int):
        """طلب إرسال جماعي"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        firebase_set(f"admin_state/{user_id}", {"action": "waiting_broadcast"})
        await callback.message.edit_text(
            "📤 **أدخل نص الرسالة للإرسال الجماعي:**\n\n"
            "يمكنك استخدام Markdown للتنسيق\n\n"
            "⚠️ سيتم إرسال الرسالة إلى جميع المشتركين النشطين.",
            reply_markup=build_cancel_button(),
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_admin_add_service(client: Client, callback: CallbackQuery):
        """عرض قائمة إضافة الخدمات"""
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة زر", callback_data="admin_add_button")],
            [InlineKeyboardButton("📂 إضافة فئة", callback_data="admin_add_category")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
        ])

        await callback.message.edit_text(
            "🛠 **إضافة خدمة جديدة**\n\nاختر نوع الخدمة:",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_admin_add_category(client: Client, callback: CallbackQuery, user_id: int):
        """طلب إضافة فئة جديدة"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        firebase_set(f"admin_state/{user_id}", {"action": "waiting_cat_details"})
        await callback.message.edit_text(
            "📂 **أدخل تفاصيل الفئة:**\n\n"
            "`الاسم اللغة الأيقونة النص`\n\n"
            "مثال:\n"
            "`التداول ar 💰 التداول`",
            reply_markup=build_cancel_button(),
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_admin_manage_buttons(client: Client, callback: CallbackQuery):
        """عرض إدارة الأزرار (قائمة مختصرة)"""
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        buttons = firebase_get("dynamic_buttons") or {}
        if not buttons:
            await callback.message.edit_text(
                "📋 **لا توجد أزرار مضافة**",
                reply_markup=build_back_button("admin_panel"),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        text = "📋 **الأزرار المضافة:**\n\n"
        for btn_id, btn_data in list(buttons.items())[:10]:
            text += f"• {btn_data.get('text_ar', 'زر')} | `{btn_id}`\n"

        await callback.message.edit_text(
            text,
            reply_markup=build_back_button("admin_panel"),
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_admin_manage_categories(client: Client, callback: CallbackQuery):
        """عرض إدارة الفئات (قائمة مختصرة)"""
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        categories = firebase_get("categories") or {}
        text = "📂 **الفئات:**\n\n"
        for cat_id, cat_data in list(categories.items())[:15]:
            text += f"{cat_data.get('icon', '📁')} {cat_data.get('name', cat_id)} | `{cat_id}`\n"

        await callback.message.edit_text(
            text,
            reply_markup=build_back_button("admin_panel"),
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_complete_setup(client: Client, callback: CallbackQuery, user_id: int):
        """إنهاء إعداد البوت"""
        if not is_admin(user_id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        firebase_set("system_config/setup_complete", True)
        firebase_set("system_config/setup_completed_at", datetime.now().isoformat())
        firebase_set("system_config/setup_completed_by", user_id)

        await callback.message.edit_text(
            "✅ **تم إعداد البوت بنجاح!**\n\n"
            "يمكنك الآن:\n"
            "• استخدام `/start` لعرض القائمة الرئيسية\n"
            "• استخدام `/admin_control` للعودة إلى لوحة التحكم\n"
            "• مشاركة البوت مع المستخدمين",
            reply_markup=build_back_button(),
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_refresh_collector(client: Client, callback: CallbackQuery):
        """تحديث إحصائيات الجامع"""
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ غير مصرح لك", show_alert=True)
            return

        await handle_admin_stats(client, callback)

    # ==================== دوال مساعدة ====================

    async def show_review_news(client: Client, callback: CallbackQuery, news_list: List[Dict], index: int):
        """عرض خبر واحد للمراجعة"""
        if index >= len(news_list):
            await callback.message.edit_text(
                "✅ **تمت مراجعة جميع الأخبار**",
                reply_markup=build_back_button("admin_panel"),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        news = news_list[index]
        cat_name = firebase_get(f"categories/{news.get('category_id', 'general')}/name") or 'عام'

        text = f"""
📋 **مراجعة خبر {index + 1}/{len(news_list)}**

**العنوان:** {news.get('title', 'بدون عنوان')}

**المحتوى:**
{news.get('content', '')[:500]}{'...' if len(news.get('content', '')) > 500 else ''}

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
                InlineKeyboardButton("✏️ تعديل", callback_data=f"edit_news_{news['id']}"),
                InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_news_{news['id']}")
            ],
            [
                InlineKeyboardButton("◀️ السابق", callback_data=f"review_prev_{index}"),
                InlineKeyboardButton(f"{index + 1}/{len(news_list)}", callback_data="none"),
                InlineKeyboardButton("التالي ▶️", callback_data=f"review_next_{index}")
            ],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
        ])

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

    async def broadcast_news_to_subscribers(client: Client, news_id: str, category_id: str = None):
        """نشر الخبر للمشتركين"""
        try:
            news = get_news(news_id)
            if not news:
                return

            if not category_id:
                category_id = news.get('category_id', 'general')

            subscribers = firebase_get("subscribers") or {}
            active_subscribers = [s for s in subscribers.values() if s.get('status') == 'active']

            if not active_subscribers:
                return

            cat_name = firebase_get(f"categories/{category_id}/name") or 'عام'

            broadcast_text = f"""
📰 **{news.get('title', 'خبر جديد')}**

{news.get('content', '')[:800]}{'...' if len(news.get('content', '')) > 800 else ''}

📂 **الفئة:** {cat_name}
🕒 **التاريخ:** {news.get('created_at', datetime.now().isoformat())[:10]}
"""

            for sub in active_subscribers:
                try:
                    entity_id = sub.get('entity_id')
                    if not entity_id:
                        continue

                    preferences = firebase_get(f"entity_categories/{entity_id}") or {}
                    is_enabled = preferences.get(category_id, {}).get('enabled', True)

                    if not is_enabled:
                        continue

                    await client.send_message(int(entity_id), broadcast_text, parse_mode=ParseMode.MARKDOWN)
                    await asyncio.sleep(BotConfig.BROADCAST_DELAY)

                except FloodWait as e:
                    await asyncio.sleep(e.value)
                except Exception:
                    pass

        except Exception:
            pass

    # ==================== دوال مساعدة إضافية ====================

    def get_system_stats() -> Dict:
        """جلب إحصائيات النظام"""
        all_news = firebase_get("news") or {}
        all_users = firebase_get("users") or {}
        subscribers = firebase_get("subscribers") or {}

        approved = sum(1 for n in all_news.values() if n.get('status') == 'approved' and not n.get('is_deleted'))
        pending = sum(1 for n in all_news.values() if n.get('status') == 'pending' and not n.get('is_deleted'))

        return {
            'total_news': len(all_news),
            'approved_news': approved,
            'pending_news': pending,
            'total_subscribers': len(subscribers),
            'total_users': len(all_users)
        }

    def update_dynamic_button(btn_id: str, updates: Dict) -> bool:
        """تحديث زر ديناميكي"""
        current = firebase_get(f"dynamic_buttons/{btn_id}") or {}
        current.update(updates)
        return firebase_set(f"dynamic_buttons/{btn_id}", current)

    def get_entity_category_preferences(entity_id: str) -> Dict[str, bool]:
        """الحصول على تفضيلات فئات كيان"""
        prefs = firebase_get(f"entity_categories/{entity_id}") or {}
        result = {}
        for cat_id, cat_data in prefs.items():
            result[cat_id] = cat_data.get("enabled", True)
        return result

    def update_entity_category_preferences(entity_id: str, category_id: str, enabled: bool) -> bool:
        """تحديث تفضيل فئة لكيان"""
        return firebase_set(f"entity_categories/{entity_id}/{category_id}", {
            "enabled": enabled,
            "updated_at": datetime.now().isoformat()
        })


# ==================== تسجيل المعالجات ====================

def register_callback_handlers(app: Client):
    """تسجيل جميع معالجات الأزرار - تم تنفيذها أعلاه"""
    pass