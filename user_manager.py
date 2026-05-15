#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
╔══════════════════════════════════════════════════════════════════╗
║                    CLASS: UserManager                           ║
║              إدارة المستخدمين والنقاط والإحالات                 ║
╚══════════════════════════════════════════════════════════════════╝
"""

import time
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any, List

from bot_config import BotConfig
from firebase_core import firebase_get, firebase_set, firebase_update, firebase_delete, cached_firebase

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)
logger.propagate = False


def is_admin(user_id: int) -> bool:
    """التحقق من صلاحيات المشرف"""
    return user_id in BotConfig.ADMIN_IDS


def create_user(user_data: Dict) -> Dict:
    """
    إنشاء مستخدم جديد في قاعدة البيانات
    """
    user_id = str(user_data.get('user_id'))
    
    data = {
        'user_id': user_id,
        'username': user_data.get('username', ''),
        'first_name': user_data.get('first_name', ''),
        'last_name': user_data.get('last_name', ''),
        'points': user_data.get('points', 0),
        'total_points_earned': 0,
        'referral_code': hashlib.md5(f"{user_id}_{time.time()}".encode()).hexdigest()[:8],
        'referred_by': user_data.get('referred_by', ''),
        'referrals_count': 0,
        'subscribed_entities': [],
        'favorite_categories': [],
        'language': 'ar',
        'is_admin': int(user_id) in BotConfig.ADMIN_IDS,
        'is_active': True,
        'is_premium': user_data.get('is_premium', False),
        'is_banned': False,
        'notifications_enabled': True,
        'daily_streak': 0,
        'last_daily_bonus': None,
        'last_active': datetime.now().isoformat(),
        'created_at': datetime.now().isoformat(),
        'settings': {
            'theme': 'dark',
            'auto_save': True,
            'compact_view': False
        }
    }
    
    firebase_set(f"users/{user_id}", data)
    return data


@cached_firebase(ttl_seconds=10)
def get_user(user_id: int) -> Optional[Dict]:
    """جلب بيانات مستخدم محدد"""
    return firebase_get(f"users/{str(user_id)}")


def update_user(user_id: int, updates: Dict) -> bool:
    """تحديث بيانات مستخدم موجود"""
    updates['last_active'] = datetime.now().isoformat()
    return firebase_update(f"users/{str(user_id)}", updates)


def add_points(user_id: int, points: int, reason: str = "") -> bool:
    """
    إضافة نقاط لمستخدم
    """
    if not BotConfig.ENABLE_POINTS_SYSTEM:
        return True
    
    user = get_user(user_id)
    if not user:
        return False
    
    current = user.get('points', 0)
    total = user.get('total_points_earned', 0)
    
    success = update_user(user_id, {
        'points': current + points,
        'total_points_earned': total + points if points > 0 else total
    })
    
    return success


def get_daily_bonus(user_id: int) -> Tuple[int, bool]:
    """
    حساب المكافأة اليومية للمستخدم
    
    Returns:
        (مبلغ المكافأة, هل تم الاستلام)
    """
    user = get_user(user_id)
    if not user:
        return 0, False
    
    last_bonus = user.get('last_daily_bonus')
    today = datetime.now().date()
    
    if last_bonus:
        try:
            last_date = datetime.fromisoformat(last_bonus).date()
        except:
            last_date = today
        
        if last_date == today:
            return 0, False
        
        if last_date == today - timedelta(days=1):
            streak = user.get('daily_streak', 0) + 1
        else:
            streak = 1
    else:
        streak = 1
    
    bonus = BotConfig.POINTS_DAILY_BONUS + ((streak - 1) // 7) * 5
    
    update_user(user_id, {
        'points': user.get('points', 0) + bonus,
        'daily_streak': streak,
        'last_daily_bonus': datetime.now().isoformat()
    })
    
    return bonus, True


def get_user_stats(user_id: int) -> Dict:
    """
    الحصول على إحصائيات المستخدم
    """
    user = get_user(user_id) or {}
    subscriptions = user.get('subscribed_entities', [])
    
    return {
        'points': user.get('points', 0),
        'total_points': user.get('total_points_earned', 0),
        'subscriptions': len(subscriptions),
        'referrals': user.get('referrals_count', 0),
        'streak': user.get('daily_streak', 0),
        'referral_code': user.get('referral_code', ''),
        'user_id': user_id,
        'is_premium': user.get('is_premium', False),
        'is_admin': user.get('is_admin', False)
    }


def process_referral(new_user_id: int, referral_code: str) -> bool:
    """
    معالجة الإحالة عند تسجيل مستخدم جديد
    """
    if not BotConfig.ENABLE_REFERRAL_SYSTEM:
        return False
    
    all_users = firebase_get("users") or {}
    referrer_id = None
    
    for uid, user_data in all_users.items():
        if user_data.get('referral_code') == referral_code and int(uid) != new_user_id:
            referrer_id = int(uid)
            break
    
    if referrer_id:
        add_points(referrer_id, BotConfig.POINTS_PER_REFERRAL, f"إحالة مستخدم جديد ({new_user_id})")
        
        referrer = get_user(referrer_id)
        if referrer:
            update_user(referrer_id, {
                'referrals_count': referrer.get('referrals_count', 0) + 1
            })
        
        update_user(new_user_id, {'referred_by': str(referrer_id)})
        return True
    
    return False