#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
╔══════════════════════════════════════════════════════════════════╗
║                    CLASS: NewsCollector                         ║
║              جامع الأخبار التلقائي من الكيانات المراقبة         ║
║              يدعم جلسات متعددة مع Pyrogram الحقيقي              ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import hashlib
import re
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Set, Any
from collections import defaultdict

from pyrogram import Client
from pyrogram.enums import ParseMode, ChatType, ChatMemberStatus
from pyrogram.errors import FloodWait, ChatWriteForbidden, UsernameNotOccupied, PeerIdInvalid, RPCError
from pyrogram.raw.functions.messages import GetHistory
from pyrogram.raw.types import InputPeerChannel, InputPeerChat

from bot_config import BotConfig
from firebase_core import firebase_get, firebase_set, firebase_update, firebase_delete, firebase_push
from user_manager import add_points

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)
logger.propagate = False


class NewsCollector:
    """
    كلاس جلب الأخبار - يقوم بمراقبة الكيانات المضافة وجلب الأخبار تلقائياً
    يدعم جلسات متعددة من Pyrogram للاتصال بخوادم تيليجرام
    """
    
    def __init__(self):
        # جلسات Pyrogram النشطة
        self.sessions: Dict[str, Client] = {}
        self.session_info: Dict[str, Dict] = {}
        
        # حالة التشغيل
        self.is_running = False
        self.scan_interval = BotConfig.SCAN_INTERVAL if hasattr(BotConfig, 'SCAN_INTERVAL') else 60
        
        # إحصائيات
        self.stats: Dict[str, Any] = {
            "total_scanned": 0,
            "total_extracted": 0,
            "total_errors": 0,
            "last_scan": None,
            "active_sessions": 0,
            "monitored_entities": 0,
            "processing_status": "idle"
        }
        
        # الكلمات المفتاحية لتصنيف الأخبار
        self.category_keywords: Dict[str, List[str]] = {
            "politics": ["سياسي", "وزير", "حكومة", "برلمان", "انتخابات", "رئيس", "ملك", "أمير", "سياسة"],
            "economy": ["اقتصاد", "سوق", "أسهم", "ذهب", "نفط", "بترول", "دولار", "ريال", "بنك", "استثمار"],
            "sports": ["رياضة", "كأس", "دوري", "مباراة", "هدف", "فريق", "لاعب", "مدرب", "أولمبياد"],
            "technology": ["تقنية", "ذكاء اصطناعي", "AI", "برمجيات", "هاتف", "تطبيق", "موبايل", "كمبيوتر"],
            "health": ["صحة", "مرض", "علاج", "دواء", "مستشفى", "وباء", "فيروس", "لقاح"],
            "science": ["علم", "بحث", "دراسة", "فضاء", "كوكب", "طاقة", "فيزياء", "كيمياء"],
            "entertainment": ["فن", "سينما", "موسيقى", "فنان", "ممثل", "حفل", "فيلم", "مسلسل"],
            "education": ["تعليم", "مدرسة", "جامعة", "طالب", "معلم", "مناهج", "دراسة"],
            "general": []
        }
        
        # سجل الرسائل المعالجة (لتجنب التكرار)
        self.processed_messages: Set[str] = set()
        self.max_processed_cache = 10000
        
        logger.error("NewsCollector initialized")
    
    # ==================== إدارة الجلسات ====================
    
async def add_session(self, session_string: str, added_by: int = 0) -> Tuple[bool, str]:
    """إضافة جلسة جديدة للجامع"""
    try:
        # إنشاء عميل اختبار
        test_client = Client(
            f"test_session_{int(time.time())}",
            session_string=session_string,
            api_id=BotConfig.API_ID,
            api_hash=BotConfig.API_HASH
        )
        
        await test_client.connect()
        
        # محاولة الحصول على معلومات المستخدم للتحقق من صحة الجلسة
        try:
            me = await test_client.get_me()
        except Exception as e:
            await test_client.disconnect()
            return False, f"❌ الجلسة غير صالحة: {str(e)[:50]}"
        
        session_id = f"session_{me.id}"
        
        # حفظ الجلسة في Firebase
        firebase_set(f"sessions/{session_id}", {
            'session_string': session_string,
            'user_id': me.id,
            'username': me.username,
            'first_name': me.first_name,
            'added_by': added_by,
            'added_at': datetime.now().isoformat()
        })
        
        await test_client.disconnect()
        
        # إنشاء العميل الحقيقي
        client = Client(
            f"collector_{me.id}",
            session_string=session_string,
            api_id=BotConfig.API_ID,
            api_hash=BotConfig.API_HASH
        )
        await client.start()
        self.sessions[session_id] = client
        self.stats["active_sessions"] = len(self.sessions)
        
        return True, f"✅ تم إضافة الجلسة: {me.first_name}"
        
    except Exception as e:
        return False, f"❌ فشل: {str(e)[:100]}"
    
    async def remove_session(self, session_id: str) -> bool:
        """
        إزالة جلسة من الجامع
        
        Args:
            session_id: معرف الجلسة
        
        Returns:
            True إذا تمت الإزالة بنجاح
        """
        try:
            if session_id in self.sessions:
                await self.sessions[session_id].stop()
                del self.sessions[session_id]
            
            if session_id in self.session_info:
                del self.session_info[session_id]
            
            # تحديث الحالة في Firebase
            firebase_update(f"sessions/{session_id}", {'is_active': False, 'status': 'removed'})
            
            self.stats["active_sessions"] = len(self.sessions)
            logger.error(f"Session removed: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove session: {e}")
            return False
    
    async def load_sessions_from_db(self) -> int:
        """
        تحميل الجلسات المحفوظة من قاعدة البيانات
        
        Returns:
            عدد الجلسات التي تم تحميلها
        """
        try:
            sessions_data = firebase_get("sessions") or {}
            loaded_count = 0
            
            for session_id, session_data in sessions_data.items():
                if not session_data.get('is_active', True):
                    continue
                
                session_string = session_data.get('session_string')
                if not session_string:
                    continue
                
                # إضافة الجلسة
                success, _ = await self.add_session(session_string, session_data.get('added_by', 0))
                if success:
                    loaded_count += 1
            
            logger.error(f"Loaded {loaded_count} sessions from database")
            return loaded_count
            
        except Exception as e:
            logger.error(f"Failed to load sessions: {e}")
            return 0
    
    # ==================== دوال مساعدة للكيانات ====================
    
    async def _resolve_peer(self, client: Client, entity_id: str, access_hash: str = None, username: str = None):
        """
        تحويل معرف الكيان إلى Peer يمكن استخدامه في الطلبات
        
        Args:
            client: عميل Pyrogram
            entity_id: معرف الكيان
            access_hash: hash الوصول (اختياري)
            username: اسم المستخدم (اختياري)
        
        Returns:
            Peer object أو None
        """
        try:
            # محاولة الحصول على الكيان بالمعرف أولاً
            try:
                chat = await client.get_chat(int(entity_id))
                return chat
            except Exception:
                pass
            
            # محاولة باستخدام username
            if username:
                try:
                    chat = await client.get_chat(username)
                    return chat
                except Exception:
                    pass
            
            # محاولة باستخدام access_hash
            if access_hash and entity_id:
                try:
                    peer = InputPeerChannel(channel_id=int(entity_id), access_hash=int(access_hash))
                    return peer
                except Exception:
                    pass
            
            return None
            
        except Exception:
            return None
    
    async def _fetch_messages(self, client: Client, chat, limit: int = 50) -> List:
        """
        جلب الرسائل من كيان معين
        
        Args:
            client: عميل Pyrogram
            chat: كائن المحادثة أو Peer
            limit: عدد الرسائل المطلوبة
        
        Returns:
            قائمة بالرسائل
        """
        try:
            messages = []
            async for message in client.get_chat_history(chat, limit=limit):
                messages.append(message)
            return messages
        except FloodWait as e:
            await asyncio.sleep(e.value)
            return []
        except Exception:
            return []
    
    # ==================== استخراج الأخبار ====================
    
    async def _extract_news_from_message(self, message, source_id: int, source_name: str, category_id: str = "general") -> Optional[Dict]:
        """
        استخراج خبر من رسالة واحدة
        
        Args:
            message: كائن الرسالة من Pyrogram
            source_id: معرف المصدر
            source_name: اسم المصدر
            category_id: الفئة المحددة للكيان (إن وجدت)
        
        Returns:
            قاموس الخبر أو None
        """
        try:
            # الحصول على النص من الرسالة
            text = message.text or message.caption
            if not text or len(text) < 50:
                return None
            
            # تجاهل الأوامر
            if text.startswith('/'):
                return None
            
            # استخراج العنوان والمحتوى
            title = self._extract_title(text)
            content = self._clean_text(text)
            
            # تصنيف الخبر (إذا لم تكن هناك فئة محددة)
            detected_category = self._classify_news(text)
            final_category = category_id if category_id != 'general' else detected_category
            
            # إنشاء معرف فريد للخبر
            news_id = hashlib.md5(
                f"{source_id}_{message.id}_{message.date.timestamp() if message.date else time.time()}".encode()
            ).hexdigest()[:16]
            
            # استخراج نوع الوسائط
            media_type = "text"
            media_file_id = None
            
            if message.photo:
                media_type = "photo"
                media_file_id = message.photo.file_id
            elif message.video:
                media_type = "video"
                media_file_id = message.video.file_id
            elif message.document:
                media_type = "document"
                media_file_id = message.document.file_id
            elif message.audio:
                media_type = "audio"
                media_file_id = message.audio.file_id
            
            # بناء بيانات الخبر
            news_data = {
                'id': news_id,
                'title': title,
                'content': content,
                'source_id': source_id,
                'source_name': source_name,
                'category_id': final_category,
                'original_text': text[:500],
                'message_id': message.id,
                'media_type': media_type,
                'media_file_id': media_file_id,
                'views': getattr(message, 'views', 0),
                'forwards': getattr(message, 'forwards', 0),
                'replies': getattr(message, 'replies', 0),
                'status': 'pending',
                'created_at': datetime.now().isoformat(),
                'is_deleted': False
            }
            
            return news_data
            
        except Exception:
            return None
    
    def _extract_title(self, text: str, max_length: int = 100) -> str:
        """استخراج عنوان من النص"""
        try:
            lines = text.strip().split('\n')
            title = lines[0] if lines else text[:max_length]
            
            # تنظيف العنوان
            title = re.sub(r'[#@]\w+', '', title)
            title = re.sub(r'https?://\S+', '', title)
            title = re.sub(r'[^\w\s\u0600-\u06FF]', ' ', title)
            title = re.sub(r'\s+', ' ', title).strip()
            
            if len(title) > max_length:
                title = title[:max_length-3] + "..."
            
            return title or "خبر"
            
        except Exception:
            return text[:max_length] if text else "خبر"
    
    def _clean_text(self, text: str) -> str:
        """تنظيف النص من الروابط والرموز غير المرغوب فيها"""
        if not text:
            return ""
        
        cleaned = text
        cleaned = re.sub(r'https?://\S+', '', cleaned)
        cleaned = re.sub(r'www\.\S+', '', cleaned)
        cleaned = re.sub(r't\.me/\S+', '', cleaned)
        cleaned = re.sub(r'@\w+', '', cleaned)
        cleaned = re.sub(r'<[^>]+>', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned
    
    def _classify_news(self, text: str) -> str:
        """تصنيف الخبر بناءً على الكلمات المفتاحية"""
        text_lower = text.lower()
        scores = defaultdict(int)
        
        for category, keywords in self.category_keywords.items():
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    scores[category] += 1
        
        if scores:
            return max(scores, key=scores.get)
        return "general"
    
    # ==================== منع التكرار ====================
    
    def _is_message_processed(self, chat_id: int, message_id: int) -> bool:
        """التحقق مما إذا كانت الرسالة قد تمت معالجتها مسبقاً"""
        key = f"{chat_id}_{message_id}"
        return key in self.processed_messages
    
    def _mark_message_processed(self, chat_id: int, message_id: int):
        """تسجيل الرسالة كمعالجة"""
        key = f"{chat_id}_{message_id}"
        self.processed_messages.add(key)
        
        # تنظيف الكاش إذا أصبح كبيراً جداً
        if len(self.processed_messages) > self.max_processed_cache:
            to_remove = list(self.processed_messages)[:self.max_processed_cache // 2]
            for item in to_remove:
                self.processed_messages.discard(item)
    
    # ==================== حفظ الأخبار وإشعار المشرفين ====================
    
    async def _save_news(self, news_data: Dict, client: Client = None) -> bool:
        """
        حفظ الخبر في قاعدة البيانات وإشعار المشرفين
        
        Args:
            news_data: بيانات الخبر
            client: عميل Pyrogram للإشعارات (اختياري)
        
        Returns:
            True إذا تم الحفظ بنجاح
        """
        try:
            # حفظ الخبر في Firebase
            news_id = news_data['id']
            firebase_set(f"news/{news_id}", news_data)
            
            # إشعار المشرفين (إذا كان العميل متاحاً)
            if client:
                for admin_id in BotConfig.ADMIN_IDS:
                    try:
                        await client.send_message(
                            admin_id,
                            f"📋 **خبر جديد**\n\n"
                            f"📡 **المصدر:** {news_data['source_name']}\n"
                            f"📂 **الفئة:** {news_data['category_id']}\n"
                            f"📝 **العنوان:** {news_data['title'][:100]}\n"
                            f"🆔 **المعرف:** `{news_id}`\n\n"
                            f"📌 للمراجعة: `/review_news`",
                            parse_mode=ParseMode.MARKDOWN
                        )
                    except Exception:
                        pass
            
            self.stats["total_extracted"] += 1
            return True
            
        except Exception:
            return False
    
    # ==================== معالجة الكيان الواحد ====================
    
    async def _process_single_entity(self, entity_id: str, entity_data: Dict, client: Client, session_id: str) -> int:
        """
        معالجة كيان واحد وجلب أخباره
        
        Args:
            entity_id: معرف الكيان
            entity_data: بيانات الكيان من Firebase
            client: عميل Pyrogram المستخدم
            session_id: معرف الجلسة
        
        Returns:
            عدد الأخبار المستخرجة
        """
        extracted_count = 0
        
        try:
            chat_id = int(entity_id)
            username = entity_data.get('username')
            access_hash = entity_data.get('access_hash')
            category_id = entity_data.get('category_id', 'general')
            source_name = entity_data.get('name') or username or f"entity_{chat_id}"
            
            # حل الكيان إلى Peer
            chat = await self._resolve_peer(client, entity_id, access_hash, username)
            if not chat:
                return 0
            
            # جلب آخر الرسائل
            messages = await self._fetch_messages(client, chat, limit=50)
            if not messages:
                return 0
            
            # معالجة كل رسالة
            for message in messages:
                # تجنب التكرار
                if self._is_message_processed(chat_id, message.id):
                    continue
                
                # استخراج الخبر
                news_data = await self._extract_news_from_message(
                    message=message,
                    source_id=chat_id,
                    source_name=source_name,
                    category_id=category_id
                )
                
                if news_data:
                    # حفظ الخبر
                    await self._save_news(news_data, client)
                    self._mark_message_processed(chat_id, message.id)
                    extracted_count += 1
                    
                    # تحديث إحصائيات الجلسة
                    if session_id in self.session_info:
                        self.session_info[session_id]['total_extracted'] += 1
                        self.session_info[session_id]['total_scanned'] += 1
            
            # تحديث وقت آخر فحص للكيان
            firebase_update(f"monitored_entities/{entity_id}", {
                'last_check': datetime.now().isoformat(),
                'last_extracted': extracted_count
            })
            
            return extracted_count
            
        except FloodWait as e:
            await asyncio.sleep(e.value)
            return 0
        except Exception:
            if session_id in self.session_info:
                self.session_info[session_id]['errors_count'] += 1
            self.stats["total_errors"] += 1
            return 0
    
    # ==================== حلقة المسح الرئيسية ====================
    
    async def _scan_monitored_entities(self):
        """مسح جميع الكيانات المراقبة باستخدام الجلسات المتاحة"""
        # جلب الكيانات المراقبة من Firebase
        monitored_entities = firebase_get("monitored_entities") or {}
        
        if not monitored_entities:
            return
        
        self.stats["monitored_entities"] = len(monitored_entities)
        self.stats["processing_status"] = "processing"
        
        # توزيع الكيانات على الجلسات المتاحة
        sessions_list = list(self.sessions.items())
        
        if not sessions_list:
            self.stats["processing_status"] = "idle"
            return
        
        # توزيع الكيانات بطريقة Round-Robin على الجلسات
        entity_items = list(monitored_entities.items())
        session_index = 0
        total_extracted = 0
        
        for entity_id, entity_data in entity_items:
            if session_index >= len(sessions_list):
                session_index = 0
            
            session_id, client = sessions_list[session_index]
            session_index += 1
            
            try:
                # التحقق من أن العميل لا يزال متصلاً
                if not client.is_connected:
                    await client.connect()
                
                # معالجة الكيان
                extracted = await self._process_single_entity(entity_id, entity_data, client, session_id)
                total_extracted += extracted
                self.stats["total_scanned"] += 1
                
                # تأخير بسيط بين الطلبات
                await asyncio.sleep(2)
                
            except Exception:
                self.stats["total_errors"] += 1
        
        self.stats["total_extracted"] += total_extracted
        self.stats["processing_status"] = "idle"
        self.stats["last_scan"] = datetime.now().isoformat()
        
        logger.error(f"Scan completed: {len(entity_items)} entities, {total_extracted} news extracted")
    
    # ==================== التشغيل والإيقاف ====================
    
    async def start_collecting(self):
        """بدء جمع الأخبار من الكيانات المراقبة"""
        if self.is_running:
            return
        
        self.is_running = True
        logger.error("NewsCollector started - scanning loop active")
        
        try:
            while self.is_running:
                try:
                    await self._scan_monitored_entities()
                    await asyncio.sleep(self.scan_interval)
                    
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                except Exception:
                    await asyncio.sleep(10)
                    
        except asyncio.CancelledError:
            pass
        finally:
            self.is_running = False
            logger.error("NewsCollector stopped")
    
    async def stop_collecting(self):
        """إيقاف جمع الأخبار"""
        self.is_running = False
        
        # إيقاف جميع الجلسات النشطة
        for session_id, client in self.sessions.items():
            try:
                await client.stop()
            except Exception:
                pass
        
        self.sessions.clear()
        self.session_info.clear()
        logger.error("NewsCollector stopped and cleaned up")
    
    async def get_collector_stats(self) -> Dict[str, Any]:
        """الحصول على إحصائيات الجامع"""
        pending_approvals = firebase_get("pending_mining_approvals") or {}
        
        return {
            **self.stats,
            "active_sessions": len(self.sessions),
            "monitored_entities": len(firebase_get("monitored_entities") or {}),
            "processed_cache_size": len(self.processed_messages),
            "session_details": self.session_info,
            "pending_approvals": len(pending_approvals)
        }
    
    async def add_monitored_entity(self, entity_id: str, username: str, category_id: str, access_hash: str = None, name: str = None) -> bool:
        """
        إضافة كيان للمراقبة
        
        Args:
            entity_id: معرف الكيان
            username: اسم المستخدم (@username)
            category_id: معرف الفئة
            access_hash: hash الوصول (اختياري)
            name: اسم الكيان (اختياري)
        
        Returns:
            True إذا تمت الإضافة بنجاح
        """
        try:
            entity_data = {
                "entity_id": entity_id,
                "username": username,
                "category_id": category_id,
                "status": "active",
                "added_at": datetime.now().isoformat(),
                "last_check": None
            }
            
            if access_hash:
                entity_data["access_hash"] = access_hash
            if name:
                entity_data["name"] = name
            
            firebase_set(f"monitored_entities/{entity_id}", entity_data)
            logger.error(f"Entity added to monitoring: {username}")
            return True
            
        except Exception:
            return False
    
    async def remove_monitored_entity(self, entity_id: str) -> bool:
        """
        إزالة كيان من المراقبة
        
        Args:
            entity_id: معرف الكيان
        
        Returns:
            True إذا تمت الإزالة بنجاح
        """
        try:
            firebase_delete(f"monitored_entities/{entity_id}")
            logger.error(f"Entity removed from monitoring: {entity_id}")
            return True
        except Exception:
            return False


# ==================== إنشاء النسخة العالمية ====================

news_collector = NewsCollector()


# ==================== دوال مساعدة للتشغيل ====================

async def start_collector():
    """بدء تشغيل جامع الأخبار مع تحميل الجلسات المحفوظة"""
    # تحميل الجلسات من قاعدة البيانات
    await news_collector.load_sessions_from_db()
    
    # بدء حلقة المسح
    asyncio.create_task(news_collector.start_collecting())
    logger.error("Collector startup task created")


async def stop_collector():
    """إيقاف جامع الأخبار"""
    await news_collector.stop_collecting()