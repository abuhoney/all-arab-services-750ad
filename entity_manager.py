#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
╔══════════════════════════════════════════════════════════════════╗
║                    CLASS: EntityManager                         ║
║              إدارة الكيانات والمشتركين والمراقبة                ║
║        يدعم: قنوات، مجموعات، مشتركين، كيانات مراقبة، تفضيلات   ║
╚══════════════════════════════════════════════════════════════════╝
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from bot_config import BotConfig
from firebase_core import firebase_get, firebase_set, firebase_update, firebase_delete
from user_manager import get_user, update_user

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)
logger.propagate = False


# ==================== دوال إدارة المشتركين (Subscribers) ====================

def add_subscriber(user_id: int, entity_type: str, entity_id: str, entity_name: str, access_hash: Optional[str] = None) -> bool:
    """
    إضافة مشترك جديد (قناة أو مجموعة) إلى قاعدة البيانات
    
    Args:
        user_id: معرف المستخدم الذي أضاف الكيان
        entity_type: نوع الكيان (channel, group, supergroup)
        entity_id: معرف الكيان
        entity_name: اسم الكيان
        access_hash: Hash الوصول للكيان (للاستخدام المباشر)
    
    Returns:
        True إذا تمت الإضافة بنجاح، False إذا كان الكيان موجوداً مسبقاً
    """
    try:
        # التحقق من وجود الكيان مسبقاً
        existing = firebase_get(f"subscribers/{entity_id}")
        if existing:
            return False
        
        # حفظ بيانات المشترك
        subscriber_data = {
            'user_id': str(user_id),
            'entity_type': entity_type,
            'entity_id': str(entity_id),
            'entity_name': entity_name,
            'access_hash': access_hash,
            'status': 'active',
            'subscribed_at': datetime.now().isoformat(),
            'last_active': datetime.now().isoformat()
        }
        firebase_set(f"subscribers/{entity_id}", subscriber_data)
        
        # إنشاء تفضيلات الفئات الافتراضية للكيان
        categories = firebase_get("categories") or {}
        default_cats = ["general", "politics", "economy", "sports", "technology", "health"]
        
        default_prefs = {}
        for cat_id in list(categories.keys()) + default_cats:
            default_prefs[cat_id] = {
                "enabled": True,
                "updated_at": datetime.now().isoformat()
            }
        firebase_set(f"entity_categories/{entity_id}", default_prefs)
        
        # تحديث قائمة المشتركين في ملف المستخدم
        user = get_user(user_id)
        if user:
            subscriptions = user.get('subscribed_entities', [])
            subscriptions.append({
                'type': entity_type,
                'id': str(entity_id),
                'name': entity_name,
                'access_hash': access_hash,
                'subscribed_at': datetime.now().isoformat()
            })
            update_user(user_id, {'subscribed_entities': subscriptions})
        
        logger.error(f"Subscriber added: {entity_name} ({entity_id}) by user {user_id}")
        return True
        
    except Exception:
        return False


def remove_subscriber(entity_id: str) -> bool:
    """
    إزالة مشترك (تعطيل الكيان)
    
    Args:
        entity_id: معرف الكيان المراد إزالته
    
    Returns:
        True إذا تمت الإزالة بنجاح
    """
    try:
        subscriber = firebase_get(f"subscribers/{entity_id}")
        if not subscriber:
            return False
        
        # تحديث الحالة إلى inactive بدلاً من الحذف
        firebase_update(f"subscribers/{entity_id}", {
            'status': 'inactive',
            'removed_at': datetime.now().isoformat()
        })
        
        # إزالة الكيان من قائمة المشتركين في ملف المستخدم
        user_id = int(subscriber.get('user_id', 0))
        if user_id:
            user = get_user(user_id)
            if user:
                subscriptions = user.get('subscribed_entities', [])
                subscriptions = [s for s in subscriptions if s.get('id') != entity_id]
                update_user(user_id, {'subscribed_entities': subscriptions})
        
        logger.error(f"Subscriber removed: {entity_id}")
        return True
        
    except Exception:
        return False


def get_active_subscribers() -> List[Dict]:
    """
    جلب جميع المشتركين النشطين
    
    Returns:
        قائمة بجميع المشتركين النشطين
    """
    try:
        subscribers = firebase_get("subscribers") or {}
        return [s for s in subscribers.values() if s.get('status') == 'active']
    except Exception:
        return []


def get_subscriber_info(entity_id: str) -> Optional[Dict]:
    """
    جلب معلومات مشترك محدد
    
    Args:
        entity_id: معرف الكيان
    
    Returns:
        بيانات المشترك أو None إذا لم يوجد
    """
    try:
        return firebase_get(f"subscribers/{entity_id}")
    except Exception:
        return None


def get_user_subscriptions(user_id: int) -> List[Dict]:
    """
    جلب قائمة الكيانات التي اشترك فيها مستخدم معين
    
    Args:
        user_id: معرف المستخدم
    
    Returns:
        قائمة بالكيانات المشترك فيها
    """
    try:
        user = get_user(user_id)
        if not user:
            return []
        return user.get('subscribed_entities', [])
    except Exception:
        return []


def update_subscriber_status(entity_id: str, status: str) -> bool:
    """
    تحديث حالة مشترك (active, inactive, banned)
    
    Args:
        entity_id: معرف الكيان
        status: الحالة الجديدة
    
    Returns:
        True إذا تم التحديث بنجاح
    """
    try:
        firebase_update(f"subscribers/{entity_id}", {
            'status': status,
            'updated_at': datetime.now().isoformat()
        })
        return True
    except Exception:
        return False


# ==================== دوال إدارة تفضيلات الفئات ====================

def get_entity_category_preferences(entity_id: str) -> Dict[str, bool]:
    """
    الحصول على تفضيلات الفئات لكيان معين
    
    Args:
        entity_id: معرف الكيان
    
    Returns:
        قاموس يحتوي على حالة كل فئة (مفعلة/معطلة)
    """
    try:
        prefs = firebase_get(f"entity_categories/{entity_id}") or {}
        result = {}
        
        for cat_id, cat_data in prefs.items():
            if isinstance(cat_data, dict):
                result[cat_id] = cat_data.get("enabled", True)
            else:
                result[cat_id] = True
        
        # إضافة الفئات الجديدة التي لم يتم تعيين تفضيل لها
        categories = firebase_get("categories") or {}
        default_cats = ["general", "politics", "economy", "sports", "technology", "health"]
        
        for cat_id in list(categories.keys()) + default_cats:
            if cat_id not in result:
                result[cat_id] = True
        
        return result
        
    except Exception:
        return {}


def update_entity_category_preference(entity_id: str, category_id: str, enabled: bool) -> bool:
    """
    تحديث تفضيل فئة محددة لكيان معين
    
    Args:
        entity_id: معرف الكيان
        category_id: معرف الفئة
        enabled: True للتفعيل، False للتعطيل
    
    Returns:
        True إذا تم التحديث بنجاح
    """
    try:
        firebase_set(f"entity_categories/{entity_id}/{category_id}", {
            "enabled": enabled,
            "updated_at": datetime.now().isoformat()
        })
        return True
    except Exception:
        return False


def set_entity_categories_bulk(entity_id: str, categories_enabled: Dict[str, bool]) -> bool:
    """
    تعيين تفضيلات الفئات بشكل جماعي
    
    Args:
        entity_id: معرف الكيان
        categories_enabled: قاموس {category_id: enabled}
    
    Returns:
        True إذا تم التحديث بنجاح
    """
    try:
        formatted = {}
        for cat_id, enabled in categories_enabled.items():
            formatted[cat_id] = {
                "enabled": enabled,
                "updated_at": datetime.now().isoformat()
            }
        return firebase_set(f"entity_categories/{entity_id}", formatted)
    except Exception:
        return False


def get_enabled_categories_for_entity(entity_id: str) -> List[str]:
    """
    الحصول على قائمة الفئات المفعّلة لكيان معين
    
    Args:
        entity_id: معرف الكيان
    
    Returns:
        قائمة بمعرفات الفئات المفعّلة
    """
    try:
        prefs = get_entity_category_preferences(entity_id)
        return [cat_id for cat_id, enabled in prefs.items() if enabled]
    except Exception:
        return []


# ==================== دوال إدارة الكيانات المراقبة (Monitored Entities) ====================

def add_monitored_entity(entity_id: int, access_hash: Optional[int], username: str, category_id: str, 
                         name: Optional[str] = None, invite_link: Optional[str] = None) -> bool:
    """
    إضافة كيان للمراقبة التلقائية (جمع الأخبار)
    
    Args:
        entity_id: معرف الكيان
        access_hash: Hash الوصول للكيان
        username: اسم المستخدم (@username)
        category_id: الفئة الافتراضية للكيان
        name: اسم الكيان (اختياري)
        invite_link: رابط دعوة للكيان الخاص (اختياري)
    
    Returns:
        True إذا تمت الإضافة بنجاح
    """
    try:
        data = {
            "entity_id": str(entity_id),
            "access_hash": str(access_hash) if access_hash else None,
            "username": username,
            "category_id": category_id,
            "status": "active",
            "added_at": datetime.now().isoformat(),
            "last_check": None,
            "last_extracted": 0
        }
        
        if name:
            data["name"] = name
        if invite_link:
            data["invite_link"] = invite_link
        
        firebase_set(f"monitored_entities/{entity_id}", data)
        logger.error(f"Monitored entity added: {username} ({entity_id}) with category {category_id}")
        return True
        
    except Exception:
        return False


def remove_monitored_entity(entity_id: str) -> bool:
    """
    إزالة كيان من المراقبة التلقائية
    
    Args:
        entity_id: معرف الكيان
    
    Returns:
        True إذا تمت الإزالة بنجاح
    """
    try:
        firebase_delete(f"monitored_entities/{entity_id}")
        logger.error(f"Monitored entity removed: {entity_id}")
        return True
    except Exception:
        return False


def get_monitored_entities() -> Dict[str, Dict]:
    """
    جلب جميع الكيانات المراقبة
    
    Returns:
        قاموس بالكيانات المراقبة {entity_id: data}
    """
    try:
        return firebase_get("monitored_entities") or {}
    except Exception:
        return {}


def get_monitored_entity(entity_id: str) -> Optional[Dict]:
    """
    جلب معلومات كيان مراقب محدد
    
    Args:
        entity_id: معرف الكيان
    
    Returns:
        بيانات الكيان أو None
    """
    try:
        return firebase_get(f"monitored_entities/{entity_id}")
    except Exception:
        return None


def update_monitored_entity(entity_id: str, updates: Dict) -> bool:
    """
    تحديث معلومات كيان مراقب
    
    Args:
        entity_id: معرف الكيان
        updates: التحديثات المطلوبة
    
    Returns:
        True إذا تم التحديث بنجاح
    """
    try:
        updates['updated_at'] = datetime.now().isoformat()
        return firebase_update(f"monitored_entities/{entity_id}", updates)
    except Exception:
        return False


def get_entity_by_username(username: str) -> Optional[Dict]:
    """
    البحث عن كيان مراقب بواسطة اسم المستخدم
    
    Args:
        username: اسم المستخدم (مع أو بدون @)
    
    Returns:
        بيانات الكيان أو None
    """
    try:
        if username.startswith('@'):
            username = username[1:]
        
        monitored = get_monitored_entities()
        for entity_id, data in monitored.items():
            if data.get('username') == username or data.get('username') == f"@{username}":
                data['entity_id'] = entity_id
                return data
        return None
    except Exception:
        return None


def get_monitored_entities_by_category(category_id: str) -> List[Dict]:
    """
    جلب الكيانات المراقبة حسب الفئة
    
    Args:
        category_id: معرف الفئة
    
    Returns:
        قائمة بالكيانات المراقبة في هذه الفئة
    """
    try:
        monitored = get_monitored_entities()
        return [data for data in monitored.values() if data.get('category_id') == category_id]
    except Exception:
        return []


def update_monitored_entity_last_check(entity_id: str) -> bool:
    """
    تحديث وقت آخر فحص لكيان مراقب
    
    Args:
        entity_id: معرف الكيان
    
    Returns:
        True إذا تم التحديث بنجاح
    """
    try:
        return update_monitored_entity(entity_id, {'last_check': datetime.now().isoformat()})
    except Exception:
        return False


# ==================== دوال إدارة معلومات الكيانات (Entity Info) ====================

def save_entity_info(entity_id: int, entity_data: Dict) -> bool:
    """
    حفظ معلومات كيان (access_hash, username, etc.)
    
    Args:
        entity_id: معرف الكيان
        entity_data: بيانات الكيان
    
    Returns:
        True إذا تم الحفظ بنجاح
    """
    try:
        entity_data['updated_at'] = datetime.now().isoformat()
        return firebase_set(f"entity_info/{entity_id}", entity_data)
    except Exception:
        return False


def get_entity_info(entity_id: int) -> Optional[Dict]:
    """
    جلب معلومات كيان
    
    Args:
        entity_id: معرف الكيان
    
    Returns:
        بيانات الكيان أو None
    """
    try:
        return firebase_get(f"entity_info/{entity_id}")
    except Exception:
        return None


def update_entity_info(entity_id: int, updates: Dict) -> bool:
    """
    تحديث معلومات كيان
    
    Args:
        entity_id: معرف الكيان
        updates: التحديثات المطلوبة
    
    Returns:
        True إذا تم التحديث بنجاح
    """
    try:
        updates['updated_at'] = datetime.now().isoformat()
        return firebase_update(f"entity_info/{entity_id}", updates)
    except Exception:
        return False


def delete_entity_info(entity_id: int) -> bool:
    """
    حذف معلومات كيان
    
    Args:
        entity_id: معرف الكيان
    
    Returns:
        True إذا تم الحذف بنجاح
    """
    try:
        return firebase_delete(f"entity_info/{entity_id}")
    except Exception:
        return False


# ==================== دوال إدارة جلسات الكيانات ====================

def save_entity_session(entity_id: str, session_data: Dict) -> bool:
    """
    حفظ جلسة كيان (للاستخدام في الجامع)
    
    Args:
        entity_id: معرف الكيان
        session_data: بيانات الجلسة
    
    Returns:
        True إذا تم الحفظ بنجاح
    """
    try:
        session_data['updated_at'] = datetime.now().isoformat()
        return firebase_set(f"entity_sessions/{entity_id}", session_data)
    except Exception:
        return False


def get_entity_session(entity_id: str) -> Optional[Dict]:
    """
    جلب جلسة كيان
    
    Args:
        entity_id: معرف الكيان
    
    Returns:
        بيانات الجلسة أو None
    """
    try:
        return firebase_get(f"entity_sessions/{entity_id}")
    except Exception:
        return None


def delete_entity_session(entity_id: str) -> bool:
    """
    حذف جلسة كيان
    
    Args:
        entity_id: معرف الكيان
    
    Returns:
        True إذا تم الحذف بنجاح
    """
    try:
        return firebase_delete(f"entity_sessions/{entity_id}")
    except Exception:
        return False


# ==================== دوال إحصائية ====================

def get_entities_statistics() -> Dict[str, Any]:
    """
    الحصول على إحصائيات الكيانات
    
    Returns:
        قاموس يحتوي على إحصائيات الكيانات
    """
    try:
        subscribers = get_active_subscribers()
        monitored = get_monitored_entities()
        
        # إحصائيات حسب النوع
        channel_count = sum(1 for s in subscribers if s.get('entity_type') == 'channel')
        group_count = sum(1 for s in subscribers if s.get('entity_type') in ['group', 'supergroup'])
        
        # إحصائيات الكيانات المراقبة حسب الفئة
        categories_count = {}
        for entity in monitored.values():
            cat_id = entity.get('category_id', 'general')
            categories_count[cat_id] = categories_count.get(cat_id, 0) + 1
        
        return {
            'total_subscribers': len(subscribers),
            'active_subscribers': len([s for s in subscribers if s.get('status') == 'active']),
            'channels': channel_count,
            'groups': group_count,
            'monitored_entities': len(monitored),
            'monitored_by_category': categories_count,
            'last_updated': datetime.now().isoformat()
        }
        
    except Exception:
        return {
            'total_subscribers': 0,
            'active_subscribers': 0,
            'channels': 0,
            'groups': 0,
            'monitored_entities': 0,
            'monitored_by_category': {},
            'last_updated': datetime.now().isoformat()
        }


def get_user_entities_stats(user_id: int) -> Dict[str, Any]:
    """
    الحصول على إحصائيات كيانات مستخدم معين
    
    Args:
        user_id: معرف المستخدم
    
    Returns:
        قاموس يحتوي على إحصائيات كيانات المستخدم
    """
    try:
        subscriptions = get_user_subscriptions(user_id)
        total_points = 0
        
        # حساب النقاط المستلمة من كل كيان
        for sub in subscriptions:
            entity_id = sub.get('id')
            # يمكن إضافة منطق لحساب النقاط من كل كيان
            total_points += BotConfig.POINTS_PER_SUBSCRIBE
        
        return {
            'total_subscriptions': len(subscriptions),
            'channels': sum(1 for s in subscriptions if s.get('type') == 'channel'),
            'groups': sum(1 for s in subscriptions if s.get('type') in ['group', 'supergroup']),
            'total_points_earned': total_points,
            'subscriptions': subscriptions
        }
        
    except Exception:
        return {
            'total_subscriptions': 0,
            'channels': 0,
            'groups': 0,
            'total_points_earned': 0,
            'subscriptions': []
        }


# ==================== دوال إدارة صلاحيات الكيانات ====================

def get_entity_admins(entity_id: str) -> List[Dict]:
    """
    جلب قائمة مدراء كيان معين (من Firebase)
    
    Args:
        entity_id: معرف الكيان
    
    Returns:
        قائمة بالمدراء
    """
    try:
        return firebase_get(f"entity_admins/{entity_id}") or []
    except Exception:
        return []


def add_entity_admin(entity_id: str, user_id: int, permissions: List[str] = None) -> bool:
    """
    إضافة مدير لكيان معين
    
    Args:
        entity_id: معرف الكيان
        user_id: معرف المستخدم
        permissions: قائمة الصلاحيات (افتراضي: ["manage_members", "manage_messages"])
    
    Returns:
        True إذا تمت الإضافة بنجاح
    """
    try:
        admins = get_entity_admins(entity_id)
        if permissions is None:
            permissions = ["manage_members", "manage_messages"]
        
        admin_data = {
            'user_id': user_id,
            'permissions': permissions,
            'added_at': datetime.now().isoformat()
        }
        
        # التحقق من عدم وجود المدراء مسبقاً
        for i, admin in enumerate(admins):
            if admin.get('user_id') == user_id:
                return False
        
        admins.append(admin_data)
        return firebase_set(f"entity_admins/{entity_id}", admins)
        
    except Exception:
        return False


def remove_entity_admin(entity_id: str, user_id: int) -> bool:
    """
    إزالة مدير من كيان
    
    Args:
        entity_id: معرف الكيان
        user_id: معرف المستخدم
    
    Returns:
        True إذا تمت الإزالة بنجاح
    """
    try:
        admins = get_entity_admins(entity_id)
        admins = [a for a in admins if a.get('user_id') != user_id]
        return firebase_set(f"entity_admins/{entity_id}", admins)
    except Exception:
        return False


def check_entity_admin_permission(entity_id: str, user_id: int, permission: str) -> bool:
    """
    التحقق مما إذا كان المستخدم لديه صلاحية معينة في كيان
    
    Args:
        entity_id: معرف الكيان
        user_id: معرف المستخدم
        permission: اسم الصلاحية المطلوبة
    
    Returns:
        True إذا كان لديه الصلاحية
    """
    try:
        # المشرف العام له كل الصلاحيات
        if user_id in BotConfig.ADMIN_IDS:
            return True
        
        admins = get_entity_admins(entity_id)
        for admin in admins:
            if admin.get('user_id') == user_id:
                permissions = admin.get('permissions', [])
                return permission in permissions
        
        return False
    except Exception:
        return False


# ==================== دوال إدارة إعدادات الكيانات ====================

def get_entity_settings(entity_id: str) -> Dict:
    """
    جلب إعدادات كيان معين
    
    Args:
        entity_id: معرف الكيان
    
    Returns:
        قاموس الإعدادات
    """
    try:
        return firebase_get(f"entity_settings/{entity_id}") or {}
    except Exception:
        return {}


def update_entity_settings(entity_id: str, updates: Dict) -> bool:
    """
    تحديث إعدادات كيان معين
    
    Args:
        entity_id: معرف الكيان
        updates: التحديثات المطلوبة
    
    Returns:
        True إذا تم التحديث بنجاح
    """
    try:
        current = get_entity_settings(entity_id)
        current.update(updates)
        current['updated_at'] = datetime.now().isoformat()
        return firebase_set(f"entity_settings/{entity_id}", current)
    except Exception:
        return False


def get_entity_welcome_message(entity_id: str) -> Optional[str]:
    """
    جلب رسالة الترحيب لكيان معين
    
    Args:
        entity_id: معرف الكيان
    
    Returns:
        نص رسالة الترحيب أو None
    """
    try:
        settings = get_entity_settings(entity_id)
        return settings.get('welcome_message')
    except Exception:
        return None


def set_entity_welcome_message(entity_id: str, message: str) -> bool:
    """
    تعيين رسالة ترحيب لكيان معين
    
    Args:
        entity_id: معرف الكيان
        message: نص رسالة الترحيب
    
    Returns:
        True إذا تم التعيين بنجاح
    """
    try:
        return update_entity_settings(entity_id, {'welcome_message': message})
    except Exception:
        return False


# ==================== دوال التصدير والاستيراد ====================

def export_entities_data() -> Dict:
    """
    تصدير جميع بيانات الكيانات
    
    Returns:
        قاموس بجميع بيانات الكيانات
    """
    try:
        return {
            'subscribers': firebase_get("subscribers") or {},
            'monitored_entities': firebase_get("monitored_entities") or {},
            'entity_categories': firebase_get("entity_categories") or {},
            'entity_settings': firebase_get("entity_settings") or {},
            'entity_admins': firebase_get("entity_admins") or {},
            'entity_sessions': firebase_get("entity_sessions") or {},
            'exported_at': datetime.now().isoformat()
        }
    except Exception:
        return {}


def import_entities_data(data: Dict) -> bool:
    """
    استيراد بيانات الكيانات من نسخة احتياطية
    
    Args:
        data: بيانات الكيانات
    
    Returns:
        True إذا تم الاستيراد بنجاح
    """
    try:
        if 'subscribers' in data:
            firebase_set("subscribers", data['subscribers'])
        if 'monitored_entities' in data:
            firebase_set("monitored_entities", data['monitored_entities'])
        if 'entity_categories' in data:
            firebase_set("entity_categories", data['entity_categories'])
        if 'entity_settings' in data:
            firebase_set("entity_settings", data['entity_settings'])
        if 'entity_admins' in data:
            firebase_set("entity_admins", data['entity_admins'])
        if 'entity_sessions' in data:
            firebase_set("entity_sessions", data['entity_sessions'])
        
        logger.error("Entities data imported successfully")
        return True
    except Exception:
        return False


# ==================== دوال مساعدة ====================

def get_all_entity_subscriptions() -> Dict[str, Dict]:
    """
    الحصول على جميع اشتراكات الكيانات
    
    Returns:
        قاموس بجميع المشتركين
    """
    try:
        return firebase_get("subscribers") or {}
    except Exception:
        return {}


def get_entity_subscription_info(entity_id: str) -> Optional[Dict]:
    """
    الحصول على معلومات اشتراك كيان محدد
    
    Args:
        entity_id: معرف الكيان
    
    Returns:
        بيانات الاشتراك أو None
    """
    try:
        return firebase_get(f"subscribers/{entity_id}")
    except Exception:
        return None


def get_entities_by_user(user_id: int) -> List[Dict]:
    """
    الحصول على جميع الكيانات التي يملكها مستخدم معين
    
    Args:
        user_id: معرف المستخدم
    
    Returns:
        قائمة بالكيانات
    """
    try:
        subscribers = get_all_entity_subscriptions()
        return [s for s in subscribers.values() if int(s.get('user_id', 0)) == user_id]
    except Exception:
        return []