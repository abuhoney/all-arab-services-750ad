#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
╔══════════════════════════════════════════════════════════════════╗
║                    CLASS: TextHandlers                          ║
║              معالجات النصوص والرسائل النصية                     ║
║              يدعم التحقق، حالات المشرف، التعدين، تفعيل الكيانات ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import re
import time
import random
from datetime import datetime
from typing import Dict, Optional, Tuple, List

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode, ChatType, ChatMemberStatus
from pyrogram.errors import FloodWait, ChatWriteForbidden, UsernameNotOccupied, PeerIdInvalid, RPCError

from bot_config import BotConfig
from firebase_core import firebase_get, firebase_set, firebase_update, firebase_delete
from user_manager import (
    is_admin, get_user, create_user, add_points, update_user, 
    get_user_stats, process_referral, get_daily_bonus
)
from news_manager import add_news, get_news, search_news, increment_views, increment_shares
from menu_builder import (
    build_main_menu, build_back_button, build_cancel_button, 
    build_categories_management_menu, build_admin_full_control_panel
)
from collector import news_collector
from mining_manager import mining_manager
from language_manager import language_manager


def register_text_handlers(app: Client):
    """تسجيل جميع معالجات النصوص"""
    
    # ==================== معالج النصوص الرئيسي ====================
    
    @app.on_message(filters.text & filters.private)
    async def text_handler(client: Client, message: Message):
        """
        المعالج الرئيسي للنصوص - يقوم بتوجيه الطلبات حسب الحالة
        """
        try:
            user_id = message.from_user.id
            text = message.text.strip()
            
            # ========== 1. معالجة التحقق من المستخدم الجديد ==========
            verification = firebase_get(f"verifications/{user_id}")
            if verification:
                await handle_verification(client, message, verification)
                return
            
            # ========== 2. معالجة حالة المشرف (إضافة متغيرات، نصوص، أزرار) ==========
            admin_state = firebase_get(f"admin_state/{user_id}")
            if admin_state and is_admin(user_id):
                await handle_admin_state(client, message, admin_state)
                return
            
            # ========== 3. معالجة حالة التعدين (انتظار رقم هاتف أو رمز) ==========
            mining_state = firebase_get(f"mining_state/{user_id}")
            if mining_state:
                await handle_mining_state(client, message, mining_state)
                return
            
            # ========== 4. معالجة تفعيل الأخبار (رابط قناة/مجموعة) ==========
            if text.startswith('@') or text.startswith('https://t.me/'):
                await process_entity_submission(client, message)
                return
            
            # ========== 5. معالجة البحث المباشر (بدون أمر) ==========
            if len(text) > 3 and not text.startswith('/'):
                # بحث سريع عن الأخبار
                results = search_news(text, limit=3)
                if results:
                    await handle_quick_search(client, message, text, results)
                    return
            
            # ========== 6. رسالة افتراضية (مساعدة) ==========
            await send_help_message(client, message)
            
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception:
            pass
    
    # ==================== دوال معالجة التحقق ====================
    
    async def handle_verification(client: Client, message: Message, verification: Dict):
        """
        معالجة التحقق من المستخدم الجديد (مسألة رياضية)
        """
        user_id = message.from_user.id
        user = message.from_user
        text = message.text.strip()
        
        attempts = verification.get('attempts', 0)
        correct_answer = verification.get('answer')
        question = verification.get('question')
        
        if text == correct_answer:
            # إجابة صحيحة
            firebase_delete(f"verifications/{user_id}")
            add_points(user_id, BotConfig.POINTS_VERIFICATION_REWARD, "إكمال التحقق")
            update_user(user_id, {'is_active': True})
            
            stats = get_user_stats(user_id)
            
            welcome_text = f"""
✅ **تم تفعيل حسابك بنجاح!**
🎁 **ربحت {BotConfig.POINTS_VERIFICATION_REWARD} نقطة ترحيبية**

📰 **مرحباً بك في {BotConfig.APP_NAME}!**

👤 **المستخدم:** {user.first_name}
🆔 **الآي دي:** `{user_id}`
💎 **النقاط:** {stats['points']}
🔗 **كود الإحالة:** `{stats['referral_code']}`

📋 **القائمة الرئيسية:**
"""
            await message.reply_text(
                welcome_text,
                reply_markup=build_main_menu(user_id),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            # إجابة خاطئة
            attempts += 1
            firebase_update(f"verifications/{user_id}", {"attempts": attempts})
            
            if attempts >= 5:
                firebase_delete(f"verifications/{user_id}")
                await message.reply_text(
                    "❌ **تم تجاوز الحد الأقصى من المحاولات**\n\n"
                    "تم تفعيل حسابك ولكن بدون نقاط التحقق.\n"
                    "استخدم /start للمتابعة",
                    parse_mode=ParseMode.MARKDOWN
                )
                stats = get_user_stats(user_id)
                await message.reply_text(
                    f"📰 **القائمة الرئيسية**\n\n💎 النقاط: {stats['points']}",
                    reply_markup=build_main_menu(user_id),
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await message.reply_text(
                    f"❌ **إجابة خاطئة!** (محاولة {attempts}/5)\n\n"
                    f"حاول مرة أخرى: {question}",
                    parse_mode=ParseMode.MARKDOWN
                )
    
    # ==================== دوال معالجة حالة المشرف ====================
    
    async def handle_admin_state(client: Client, message: Message, state: Dict):
        """
        معالجة حالات المشرف المتعددة الخطوات
        يدعم: إضافة متغيرات، نصوص، أزرار، صلاحيات، كيانات، هدايا
        """
        user_id = message.from_user.id
        text = message.text.strip()
        action = state.get("action")
        
        # ========== 1. إضافة متغير (waiting_config_value) ==========
        if action == "waiting_config_value":
            var_name = state.get("var_name")
            value = text
            
            # محاولة تحويل القيمة إلى النوع المناسب
            original_value = value
            var_type = "str"
            
            if value.lower() == "true":
                value = True
                var_type = "bool"
            elif value.lower() == "false":
                value = False
                var_type = "bool"
            elif value.isdigit():
                value = int(value)
                var_type = "int"
            elif value.replace('.', '', 1).isdigit() and value.count('.') <= 1:
                value = float(value)
                var_type = "float"
            elif value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
                var_type = "str"
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
                var_type = "str"
            
            # حفظ المتغير
            var_data = {
                "value": value,
                "type": var_type,
                "description": f"Added by admin {user_id} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "category": "general",
                "updated_at": datetime.now().isoformat()
            }
            firebase_set(f"system_registry/variables/{var_name}", var_data)
            
            firebase_delete(f"admin_state/{user_id}")
            
            await message.reply_text(
                f"✅ **تم إضافة المتغير بنجاح!**\n\n"
                f"📌 `{var_name}` = `{value}`\n"
                f"📌 النوع: `{var_type}`\n\n"
                f"يمكنك الآن استخدام `{{#{var_name}}}` في أي نص لعرض هذه القيمة.",
                reply_markup=build_back_button("admin_control"),
                parse_mode=ParseMode.MARKDOWN
            )
        
        # ========== 2. تعديل متغير (waiting_edit_config_value) ==========
        elif action == "waiting_edit_config_value":
            var_name = state.get("var_name")
            old_value = state.get("old_value")
            
            if not text:
                # الإبقاء على القيمة الحالية
                firebase_delete(f"admin_state/{user_id}")
                await message.reply_text(
                    f"✅ **لم يتم تغيير المتغير**\n\n`{var_name}` = `{old_value}`",
                    reply_markup=build_back_button("admin_control"),
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            value = text
            
            # محاولة تحويل القيمة
            if value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False
            elif value.isdigit():
                value = int(value)
            elif value.replace('.', '', 1).isdigit() and value.count('.') <= 1:
                value = float(value)
            elif value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            
            # تحديث المتغير
            existing = firebase_get(f"system_registry/variables/{var_name}") or {}
            existing["value"] = value
            existing["updated_at"] = datetime.now().isoformat()
            firebase_set(f"system_registry/variables/{var_name}", existing)
            
            firebase_delete(f"admin_state/{user_id}")
            
            await message.reply_text(
                f"✅ **تم تعديل المتغير بنجاح!**\n\n"
                f"📌 `{var_name}` = `{value}`\n"
                f"(كان سابقاً: `{old_value}`)",
                reply_markup=build_back_button("admin_control"),
                parse_mode=ParseMode.MARKDOWN
            )
        
        # ========== 3. إضافة نص (waiting_text_content) ==========
        elif action == "waiting_text_content":
            text_id = state.get("text_id")
            content = text
            
            # حفظ النص
            text_data = {
                "ar": content,
                "description": f"Added by admin {user_id}",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            firebase_set(f"system_registry/texts/{text_id}", text_data)
            
            firebase_delete(f"admin_state/{user_id}")
            
            await message.reply_text(
                f"✅ **تم إضافة النص بنجاح!**\n\n"
                f"📌 المعرف: `{text_id}`\n"
                f"📝 المحتوى: {content[:100]}...\n\n"
                f"يمكنك استخدامه الآن في أي مكان.",
                reply_markup=build_back_button("admin_control"),
                parse_mode=ParseMode.MARKDOWN
            )
        
        # ========== 4. تعديل نص (waiting_edit_text_content) ==========
        elif action == "waiting_edit_text_content":
            text_id = state.get("text_id")
            
            if not text:
                # الإبقاء على المحتوى الحالي
                firebase_delete(f"admin_state/{user_id}")
                await message.reply_text(
                    f"✅ **لم يتم تغيير النص**\n\n`{text_id}`",
                    reply_markup=build_back_button("admin_control"),
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # تحديث النص
            existing = firebase_get(f"system_registry/texts/{text_id}") or {}
            existing["ar"] = text
            existing["updated_at"] = datetime.now().isoformat()
            firebase_set(f"system_registry/texts/{text_id}", existing)
            
            firebase_delete(f"admin_state/{user_id}")
            
            await message.reply_text(
                f"✅ **تم تعديل النص بنجاح!**\n\n"
                f"📌 المعرف: `{text_id}`\n"
                f"📝 المحتوى الجديد: {text[:100]}...",
                reply_markup=build_back_button("admin_control"),
                parse_mode=ParseMode.MARKDOWN
            )
        
        # ========== 5. إضافة زر (مراحل متعددة) ==========
        elif action == "waiting_btn_name":
            # المرحلة 1: اسم الزر
            firebase_update(f"admin_state/{user_id}", {
                "action": "waiting_btn_text",
                "btn_name": text
            })
            await message.reply_text(
                "✏️ **أدخل النص الذي سيظهر على الزر:**\n"
                "مثال: `💰 تمويل القناة`",
                reply_markup=build_cancel_button(),
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif action == "waiting_btn_text":
            # المرحلة 2: نص الزر
            firebase_update(f"admin_state/{user_id}", {
                "action": "waiting_btn_msg",
                "btn_name": state.get("btn_name"),
                "btn_text": text
            })
            await message.reply_text(
                "📝 **أدخل نص الرسالة التي ستظهر عند الضغط على الزر:**\n\n"
                "يمكنك استخدام Markdown و {{#VAR_NAME}} للقيم الديناميكية\n\n"
                "مثال:\n"
                "```\n"
                "**خدمات البوت**\n\n"
                "1. تفعيل الأخبار: {{#POINTS_PER_SUBSCRIBE}} نقطة\n"
                "2. الإحالات: {{#POINTS_PER_REFERRAL}} نقطة\n"
                "```",
                reply_markup=build_cancel_button(),
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif action == "waiting_btn_msg":
            # المرحلة 3: محتوى الرسالة
            btn_name = state.get("btn_name")
            btn_text = state.get("btn_text")
            btn_msg = text
            btn_id = f"btn_{int(datetime.now().timestamp())}"
            
            btn_data = {
                "text_ar": btn_text,
                "msg_ar": btn_msg,
                "is_deleted": False,
                "is_hidden": False,
                "hidden_for": "",
                "created_at": datetime.now().isoformat(),
                "created_by": user_id
            }
            firebase_set(f"dynamic_buttons/{btn_id}", btn_data)
            
            firebase_delete(f"admin_state/{user_id}")
            
            await message.reply_text(
                f"✅ **تم حفظ الزر بنجاح!**\n\n"
                f"🆔 **الآي دي:** `{btn_id}`\n"
                f"🔘 **النص:** {btn_text}\n"
                f"📝 **المحتوى:** {btn_msg[:100]}...\n\n"
                f"يمكنك الآن استخدام هذا الزر في القائمة الرئيسية.",
                reply_markup=build_back_button("admin_control"),
                parse_mode=ParseMode.MARKDOWN
            )
        
        # ========== 6. إضافة صلاحية (waiting_perm_details) ==========
        elif action == "waiting_perm_id":
            perm_id = text.lower().replace(' ', '_')
            firebase_update(f"admin_state/{user_id}", {
                "action": "waiting_perm_description",
                "perm_id": perm_id
            })
            await message.reply_text(
                f"📝 **أدخل وصف الصلاحية** `{perm_id}`:\n"
                "مثال: `الوصول للمستخدمين المميزين فقط`",
                reply_markup=build_cancel_button(),
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif action == "waiting_perm_description":
            perm_id = state.get("perm_id")
            description = text
            
            perm_data = {
                "description": description,
                "roles": [],
                "allowed_user_ids": [],
                "priority": 50,
                "created_at": datetime.now().isoformat(),
                "created_by": user_id
            }
            firebase_set(f"system_registry/permissions/{perm_id}", perm_data)
            
            firebase_delete(f"admin_state/{user_id}")
            
            await message.reply_text(
                f"✅ **تم إضافة الصلاحية بنجاح!**\n\n"
                f"🆔 **المعرف:** `{perm_id}`\n"
                f"📝 **الوصف:** {description}\n\n"
                f"يمكنك الآن استخدام هذه الصلاحية للأزرار والأوامر.",
                reply_markup=build_back_button("admin_control"),
                parse_mode=ParseMode.MARKDOWN
            )
        
        # ========== 7. إضافة كيان للمراقبة (waiting_entity_details) ==========
        elif action == "waiting_entity_username":
            username = text
            if not username.startswith('@'):
                username = '@' + username
            
            firebase_update(f"admin_state/{user_id}", {
                "action": "waiting_entity_category",
                "username": username
            })
            
            # عرض الفئات المتاحة
            categories = firebase_get("categories") or {}
            default_cats = ["general", "politics", "economy", "sports", "technology", "health"]
            cat_list = list(categories.keys()) + default_cats
            cat_text = "، ".join([f"`{c}`" for c in list(set(cat_list))[:10]])
            
            await message.reply_text(
                f"📂 **أدخل فئة الكيان** `{username}`:\n\n"
                f"الفئات المتاحة: {cat_text}\n\n"
                f"مثال: `politics` أو `technology`",
                reply_markup=build_cancel_button(),
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif action == "waiting_entity_category":
            username = state.get("username")
            category_id = text.lower()
            
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
                
                firebase_delete(f"admin_state/{user_id}")
                
                if success:
                    await message.reply_text(
                        f"✅ **تم إضافة الكيان للمراقبة**\n\n"
                        f"📡 **الكيان:** {name}\n"
                        f"🆔 **المعرف:** `{entity_id}`\n"
                        f"📂 **الفئة:** {category_id}\n"
                        f"🔑 **Access Hash:** `{access_hash}`\n\n"
                        f"📰 سيتم جلب جميع رسائل هذا الكيان كأخبار.",
                        reply_markup=build_back_button("admin_control"),
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await message.reply_text(
                        f"❌ فشل إضافة الكيان للمراقبة",
                        reply_markup=build_back_button("admin_control"),
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
            except Exception as e:
                firebase_delete(f"admin_state/{user_id}")
                await message.reply_text(
                    f"❌ **فشل الوصول للكيان**\n\n"
                    f"تأكد من صحة @username وأن البوت لديه صلاحية الوصول\n\n"
                    f"**الخطأ:** {str(e)[:100]}",
                    reply_markup=build_back_button("admin_control"),
                    parse_mode=ParseMode.MARKDOWN
                )
        
        # ========== 8. إضافة هدية (waiting_gift_details) ==========
        elif action == "waiting_gift_id":
            gift_id = text.lower().replace(' ', '_')
            firebase_update(f"admin_state/{user_id}", {
                "action": "waiting_gift_type",
                "gift_id": gift_id
            })
            await message.reply_text(
                f"🎁 **اختر نوع الهدية** `{gift_id}`:\n\n"
                "• `points` - نقاط\n"
                "• `premium_days` - أيام بريميوم\n"
                "• `role` - دور خاص\n\n"
                "أدخل النوع:",
                reply_markup=build_cancel_button(),
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif action == "waiting_gift_type":
            gift_id = state.get("gift_id")
            gift_type = text.lower()
            
            if gift_type not in ["points", "premium_days", "role"]:
                await message.reply_text(
                    f"❌ نوع غير صالح. الأنواع المتاحة: `points`, `premium_days`, `role`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            firebase_update(f"admin_state/{user_id}", {
                "action": "waiting_gift_amount",
                "gift_id": gift_id,
                "gift_type": gift_type
            })
            await message.reply_text(
                f"💰 **أدخل قيمة الهدية** `{gift_id}`:\n\n"
                f"لـ {gift_type}:\n"
                f"• points: عدد النقاط (مثال: `100`)\n"
                f"• premium_days: عدد الأيام (مثال: `30`)\n"
                f"• role: اسم الدور (مثال: `vip`)\n\n"
                f"أدخل القيمة:",
                reply_markup=build_cancel_button(),
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif action == "waiting_gift_amount":
            gift_id = state.get("gift_id")
            gift_type = state.get("gift_type")
            amount = text
            
            # تحويل القيمة حسب النوع
            if gift_type == "points":
                try:
                    amount = int(amount)
                except ValueError:
                    await message.reply_text("❌ يجب أن تكون القيمة رقماً صحيحاً", parse_mode=ParseMode.MARKDOWN)
                    return
            elif gift_type == "premium_days":
                try:
                    amount = int(amount)
                except ValueError:
                    await message.reply_text("❌ يجب أن تكون القيمة رقماً صحيحاً", parse_mode=ParseMode.MARKDOWN)
                    return
            else:  # role
                amount = amount.lower().replace(' ', '_')
            
            gift_data = {
                "type": gift_type,
                "amount": amount,
                "description": f"Added by admin {user_id}",
                "active": True,
                "created_at": datetime.now().isoformat(),
                "redeemed_count": 0
            }
            firebase_set(f"gifts/{gift_id}", gift_data)
            
            firebase_delete(f"admin_state/{user_id}")
            
            await message.reply_text(
                f"✅ **تم إضافة الهدية بنجاح!**\n\n"
                f"🎁 **المعرف:** `{gift_id}`\n"
                f"📌 **النوع:** {gift_type}\n"
                f"💰 **القيمة:** {amount}\n\n"
                f"يمكنك الآن منح هذه الهدية للمستخدمين.",
                reply_markup=build_back_button("admin_control"),
                parse_mode=ParseMode.MARKDOWN
            )
        
        # ========== 9. تأكيد الحذف ==========
        elif action == "confirm_delete_config":
            var_name = state.get("var_name")
            firebase_delete(f"system_registry/variables/{var_name}")
            firebase_delete(f"admin_state/{user_id}")
            await message.reply_text(
                f"✅ **تم حذف المتغير** `{var_name}`",
                reply_markup=build_back_button("admin_control"),
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif action == "confirm_delete_button":
            btn_id = state.get("btn_id")
            firebase_delete(f"dynamic_buttons/{btn_id}")
            firebase_delete(f"admin_state/{user_id}")
            await message.reply_text(
                f"✅ **تم حذف الزر** `{btn_id}`",
                reply_markup=build_back_button("admin_control"),
                parse_mode=ParseMode.MARKDOWN
            )
        
        # ========== 10. إرسال جماعي ==========
        elif action == "waiting_broadcast":
            firebase_delete(f"admin_state/{user_id}")
            
            # جلب جميع المشتركين النشطين
            subscribers = firebase_get("subscribers") or {}
            active_subscribers = [s for s in subscribers.values() if s.get('status') == 'active']
            
            if not active_subscribers:
                await message.reply_text("❌ لا توجد مشتركين نشطين للإرسال", parse_mode=ParseMode.MARKDOWN)
                return
            
            await message.reply_text(
                f"📤 **جاري الإرسال الجماعي إلى {len(active_subscribers)} مشترك...**",
                parse_mode=ParseMode.MARKDOWN
            )
            
            success_count = 0
            fail_count = 0
            
            for sub in active_subscribers:
                try:
                    entity_id = sub.get('entity_id')
                    if entity_id:
                        await client.send_message(int(entity_id), text, parse_mode=ParseMode.MARKDOWN)
                        success_count += 1
                        await asyncio.sleep(BotConfig.BROADCAST_DELAY)
                except Exception:
                    fail_count += 1
            
            await message.reply_text(
                f"📤 **نتيجة الإرسال الجماعي**\n\n"
                f"✅ نجح: {success_count}\n"
                f"❌ فشل: {fail_count}",
                reply_markup=build_back_button("admin_panel"),
                parse_mode=ParseMode.MARKDOWN
            )
        
        # ========== 11. تعديل خبر ==========
        elif action == "editing_news":
            news_id = state.get("news_id")
            if news_id:
                update_news(news_id, {
                    'content': text,
                    'title': extract_title(text),
                    'updated_at': datetime.now().isoformat()
                })
                firebase_delete(f"admin_state/{user_id}")
                await message.reply_text(
                    "✅ **تم تحديث الخبر بنجاح!**",
                    reply_markup=build_back_button("admin_panel"),
                    parse_mode=ParseMode.MARKDOWN
                )
        
        else:
            # حالة غير معروفة - إلغاء
            firebase_delete(f"admin_state/{user_id}")
            await message.reply_text(
                "❌ **تم إلغاء العملية**\n\nلم يتم التعرف على الحالة.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    # ==================== دوال معالجة التعدين ====================
    
    async def handle_mining_state(client: Client, message: Message, state: Dict):
        """
        معالجة حالة تفعيل التعدين
        المرحلة 1: انتظار رقم الهاتف
        المرحلة 2: انتظار رمز التحقق
        """
        user_id = message.from_user.id
        text = message.text.strip()
        action = state.get("action")
        
        # ========== المرحلة 1: انتظار رقم الهاتف ==========
        if action == "waiting_phone":
            phone = text
            
            # التأكد من صيغة الرقم
            if not phone.startswith('+'):
                phone = '+' + phone
            
            # التحقق من صحة الرقم (أقل عدد من الأرقام)
            if len(phone) < 10:
                await message.reply_text(
                    "❌ **رقم غير صالح**\n\n"
                    "أرسل رقم الهاتف مع رمز الدولة\n"
                    "مثال: `+967773458975`\n\n"
                    "لإلغاء العملية: /cancel",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # تحديث الحالة
            firebase_update(f"mining_state/{user_id}", {
                "action": "waiting_code",
                "phone": phone,
                "attempts": 0,
                "start_time": datetime.now().isoformat()
            })
            
            # طلب رمز التحقق من خوادم تيليجرام
            await message.reply_text(
                f"📱 **جاري إرسال رمز التحقق إلى** `{phone}`...\n\n"
                f"⏱ يرجى الانتظار...",
                parse_mode=ParseMode.MARKDOWN
            )
            
            success, msg, request_id = await mining_manager.request_verification_code(phone, user_id, client)
            
            if success:
                # تحديث الحالة مع request_id
                firebase_update(f"mining_state/{user_id}", {
                    "request_id": request_id
                })
                # الرسالة تم إرسالها بالفعل من داخل الدالة
                pass
            else:
                firebase_delete(f"mining_state/{user_id}")
                await message.reply_text(
                    f"{msg}\n\nللمحاولة مرة أخرى: `/activate_mining`",
                    parse_mode=ParseMode.MARKDOWN
                )
        
        # ========== المرحلة 2: انتظار رمز التحقق ==========
        elif action == "waiting_code":
            code = text.strip()
            phone = state.get("phone")
            request_id = state.get("request_id")
            attempts = state.get("attempts", 0) + 1
            
            # تحديث عدد المحاولات
            firebase_update(f"mining_state/{user_id}", {"attempts": attempts})
            
            if not request_id:
                await message.reply_text(
                    "❌ **انتهت صلاحية الطلب**\n\n"
                    "استخدم `/activate_mining` للمحاولة مرة أخرى",
                    parse_mode=ParseMode.MARKDOWN
                )
                firebase_delete(f"mining_state/{user_id}")
                return
            
            # التحقق من الرمز
            await message.reply_text(
                "⏳ **جاري التحقق من الرمز...**",
                parse_mode=ParseMode.MARKDOWN
            )
            
            success, msg, session_string = await mining_manager.verify_code(request_id, code, client)
            
            if success:
                # تم التحقق بنجاح - في انتظار موافقة المشرف
                firebase_delete(f"mining_state/{user_id}")
                await message.reply_text(
                    f"✅ **تم التحقق بنجاح!**\n\n"
                    f"{msg}\n\n"
                    f"⏳ سيتم إشعارك عند موافقة المشرف.",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                if attempts >= 3:
                    firebase_delete(f"mining_state/{user_id}")
                    await message.reply_text(
                        f"❌ **تم تجاوز الحد الأقصى من المحاولات**\n\n"
                        f"{msg}\n\n"
                        f"استخدم `/activate_mining` للمحاولة مرة أخرى",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await message.reply_text(
                        f"❌ {msg}\n\n"
                        f"محاولة {attempts}/3\n"
                        f"أدخل رمز التحقق الصحيح:",
                        reply_markup=build_cancel_button(),
                        parse_mode=ParseMode.MARKDOWN
                    )
        
        else:
            # حالة غير معروفة - إلغاء
            firebase_delete(f"mining_state/{user_id}")
            await message.reply_text(
                "❌ **تم إلغاء عملية التعدين**",
                parse_mode=ParseMode.MARKDOWN
            )
    
    # ==================== دوال معالجة تفعيل الكيانات ====================
    
    async def process_entity_submission(client: Client, message: Message):
        """
        معالجة تقديم كيان للتفعيل (قناة/مجموعة)
        يدعم: @username, https://t.me/username
        """
        try:
            user_id = message.from_user.id
            text = message.text.strip()
            
            # استخراج اسم المستخدم من الرابط أو المعرف المباشر
            if text.startswith('@'):
                entity_ref = text
            elif text.startswith('https://t.me/'):
                # استخراج username من الرابط
                username_match = re.search(r't\.me/([a-zA-Z0-9_]+)', text)
                if username_match:
                    entity_ref = '@' + username_match.group(1)
                else:
                    await message.reply_text(
                        "⚠️ **رابط الدعوة غير مدعوم حالياً**\n\n"
                        "يرجى استخدام @username أو الرابط المباشر\n"
                        "مثال: `@channel_name` أو `https://t.me/channel_name`",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
            else:
                await message.reply_text(
                    "❌ **صيغة غير صحيحة**\n\n"
                    "أرسل @username أو https://t.me/username\n"
                    "مثال: `@my_channel`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # جلب معلومات الكيان
            try:
                chat = await client.get_chat(entity_ref)
                entity_id = str(chat.id)
                entity_type = 'channel' if chat.type == ChatType.CHANNEL else 'group'
                entity_name = chat.title or entity_ref
                access_hash = str(getattr(chat, 'access_hash', 0)) if getattr(chat, 'access_hash', 0) else None
                
                # التحقق من صلاحيات البوت في الكيان
                try:
                    bot_member = await client.get_chat_member(chat.id, (await client.get_me()).id)
                    can_send = bot_member.status in [
                        ChatMemberStatus.ADMINISTRATOR, 
                        ChatMemberStatus.OWNER, 
                        ChatMemberStatus.MEMBER
                    ]
                    if not can_send:
                        await message.reply_text(
                            "⚠️ **البوت ليس لديه صلاحية الإرسال في هذا الكيان!**\n\n"
                            "الرجاء إضافة البوت كمشرف أولاً",
                            parse_mode=ParseMode.MARKDOWN
                        )
                        return
                except Exception:
                    pass
                
                # التحقق مما إذا كان الكيان مفعلاً مسبقاً
                existing = firebase_get(f"subscribers/{entity_id}")
                
                if not existing:
                    # حفظ المشترك الجديد
                    subscriber_data = {
                        'user_id': str(user_id),
                        'entity_type': entity_type,
                        'entity_id': entity_id,
                        'entity_name': entity_name,
                        'access_hash': access_hash,
                        'status': 'active',
                        'subscribed_at': datetime.now().isoformat(),
                        'last_active': datetime.now().isoformat()
                    }
                    firebase_set(f"subscribers/{entity_id}", subscriber_data)
                    
                    # إضافة نقاط للمستخدم
                    add_points(user_id, BotConfig.POINTS_PER_SUBSCRIBE, f"تفعيل كيان: {entity_name}")
                    
                    # تحديث قائمة المشتركين في ملف المستخدم
                    user = get_user(user_id)
                    if user:
                        subscriptions = user.get('subscribed_entities', [])
                        subscriptions.append({
                            'type': entity_type,
                            'id': entity_id,
                            'name': entity_name,
                            'access_hash': access_hash,
                            'subscribed_at': datetime.now().isoformat()
                        })
                        update_user(user_id, {'subscribed_entities': subscriptions})
                    
                    stats = get_user_stats(user_id)
                    
                    # عرض رسالة النجاح مع إعدادات الفئات
                    success_text = f"""
✅ **تم تفعيل الأخبار بنجاح!**

📋 **الكيان:** {entity_name}
🆔 **المعرف:** `{entity_id}`
📅 **النوع:** {'قناة' if entity_type == 'channel' else 'مجموعة'}
🔑 **Access Hash:** {access_hash if access_hash else 'غير متوفر'}

🔔 سيتم إرسال الأخبار تلقائياً
💎 **+{BotConfig.POINTS_PER_SUBSCRIBE} نقطة** (إجمالي نقاطك: {stats['points']})

📂 **الآن، اختر الفئات التي تريد استلام أخبارها:**
"""
                    await message.reply_text(
                        success_text,
                        reply_markup=build_categories_management_menu(entity_id, entity_name),
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    # الكيان مفعل مسبقاً - عرض إعدادات الفئات الحالية
                    preferences = firebase_get(f"entity_categories/{entity_id}") or {}
                    enabled_count = sum(1 for v in preferences.values() if isinstance(v, dict) and v.get('enabled', True))
                    total_count = len(preferences) if preferences else 0
                    
                    await message.reply_text(
                        f"⚠️ **هذا الكيان مفعل بالفعل!**\n\n"
                        f"📋 **الكيان:** {entity_name}\n"
                        f"📊 **الفئات المفعّلة:** {enabled_count}/{total_count}\n\n"
                        f"يمكنك تعديل الفئات:",
                        reply_markup=build_categories_management_menu(entity_id, entity_name),
                        parse_mode=ParseMode.MARKDOWN
                    )
                
            except ChatWriteForbidden:
                await message.reply_text(
                    "❌ **البوت ليس لديه صلاحية الكتابة في هذا الكيان!**\n\n"
                    "الرجاء إضافة البوت كمشرف أولاً",
                    parse_mode=ParseMode.MARKDOWN
                )
            except UsernameNotOccupied:
                await message.reply_text(
                    "❌ **الكيان غير موجود!**\n\n"
                    "تأكد من صحة @username أو الرابط",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                await message.reply_text(
                    f"❌ **لا يمكن الوصول إلى الكيان**\n\n"
                    f"تأكد من:\n"
                    f"• صحة @username أو الرابط\n"
                    f"• إضافة البوت كمشرف في الكيان\n"
                    f"• أن الكيان عام أو البوت مضاف\n\n"
                    f"**الخطأ:** {str(e)[:150]}",
                    parse_mode=ParseMode.MARKDOWN
                )
                
        except Exception:
            pass
    
    # ==================== دوال مساعدة ====================
    
    async def handle_quick_search(client: Client, message: Message, query: str, results: List[Dict]):
        """
        معالجة البحث السريع (بدون أمر /search)
        """
        user_id = message.from_user.id
        
        text = f"🔍 **نتائج البحث عن:** `{query[:30]}`\n\n"
        buttons = []
        
        for i, news in enumerate(results[:5], 1):
            title = news.get('title', 'خبر')[:50]
            cat_name = firebase_get(f"categories/{news.get('category_id', 'general')}/name") or 'عام'
            text += f"{i}. **{title}**\n   📂 {cat_name} | 👁 {news.get('views', 0)}\n\n"
            buttons.append([InlineKeyboardButton(f"{i}. {title[:40]}", callback_data=f"view_news_{news['id']}")])
        
        buttons.append([InlineKeyboardButton("🔍 بحث متقدم", switch_inline_query_current_chat="")])
        buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
        
        await message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def send_help_message(client: Client, message: Message):
        """
        إرسال رسالة المساعدة الافتراضية
        """
        user_id = message.from_user.id
        
        help_text = f"""
👋 **أهلاً بك!**

**الأوامر المتاحة:**
• /start - القائمة الرئيسية
• /news - تفعيل الأخبار في قناتك/مجموعتك
• /search [نص] - البحث في الأخبار
• /stats - إحصائيات حسابك
• /daily - المكافأة اليومية
• /activate_mining - تفعيل التعدين (كسب نقاط تلقائي)

**للمشرفين فقط:**
• /admin - لوحة المشرف
• /admin_control - لوحة التحكم الكاملة

**كيفية كسب النقاط:**
• تفعيل قناة/مجموعة: +{BotConfig.POINTS_PER_SUBSCRIBE} نقطة
• المكافأة اليومية: +{BotConfig.POINTS_DAILY_BONUS} نقطة
• مشاركة خبر: +{BotConfig.POINTS_PER_NEWS_SHARE} نقطة
• إحالة مستخدم: +{BotConfig.POINTS_PER_REFERRAL} نقطة
"""
        
        await message.reply_text(
            help_text,
            reply_markup=build_back_button(),
            parse_mode=ParseMode.MARKDOWN
        )
    
    # ==================== دالة مساعدة لاستخراج العنوان ====================
    
    def extract_title(text: str, max_length: int = 100) -> str:
        """استخراج عنوان من النص"""
        try:
            lines = text.strip().split('\n')
            title = lines[0] if lines else text[:max_length]
            title = re.sub(r'[#@]\w+', '', title)
            title = re.sub(r'https?://\S+', '', title)
            title = re.sub(r'[^\w\s\u0600-\u06FF]', ' ', title)
            title = re.sub(r'\s+', ' ', title).strip()
            if len(title) > max_length:
                title = title[:max_length-3] + "..."
            return title or "خبر"
        except Exception:
            return text[:max_length] if text else "خبر"
    
    # ==================== دالة مساعدة لتحديث الأخبار ====================
    
    def update_news(news_id: str, updates: Dict) -> bool:
        """تحديث خبر"""
        from firebase_core import firebase_update
        updates['updated_at'] = datetime.now().isoformat()
        return firebase_update(f"news/{news_id}", updates)


# ==================== تسجيل المعالجات ====================

def register_text_handlers(app: Client):
    """تسجيل جميع معالجات النصوص - تم تنفيذها أعلاه"""
    # جميع الدوال مسجلة بالفعل داخل هذا الـ function
    pass