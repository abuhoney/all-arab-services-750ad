#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
╔══════════════════════════════════════════════════════════════════╗
║                    CLASS: NewsManager                           ║
║                    إدارة الأخبار والبحث                         ║
╚══════════════════════════════════════════════════════════════════╝
"""

from datetime import datetime
from typing import Dict, List, Optional

from firebase_core import firebase_get, firebase_set, firebase_update, firebase_push
from bot_config import BotConfig


def add_news(news_data: Dict) -> str:
    """إضافة خبر جديد"""
    news_id = firebase_push("news", news_data)
    return news_id or f"local_{int(datetime.now().timestamp())}"


def get_news(news_id: str) -> Optional[Dict]:
    """جلب خبر بالمعرف"""
    return firebase_get(f"news/{news_id}")


def get_news_list(status: str = 'approved', category: Optional[str] = None, limit: int = 20) -> List[Dict]:
    """جلب قائمة الأخبار"""
    all_news = firebase_get("news") or {}
    news_list = []
    
    for nid, data in all_news.items():
        if data.get('status') != status:
            continue
        if data.get('is_deleted'):
            continue
        if category and category != 'all' and data.get('category_id') != category:
            continue
        data['id'] = nid
        news_list.append(data)
    
    news_list.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return news_list[:limit]


def get_pending_news(limit: int = 50) -> List[Dict]:
    """جلب الأخبار قيد المراجعة"""
    all_news = firebase_get("news") or {}
    pending = []
    
    for nid, data in all_news.items():
        if data.get('status') == 'pending' and not data.get('is_deleted'):
            data['id'] = nid
            pending.append(data)
    
    pending.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return pending[:limit]


def update_news(news_id: str, updates: Dict) -> bool:
    """تحديث خبر"""
    updates['updated_at'] = datetime.now().isoformat()
    return firebase_update(f"news/{news_id}", updates)


def approve_news(news_id: str, admin_id: int) -> bool:
    """الموافقة على خبر"""
    return update_news(news_id, {
        'status': 'approved',
        'approved_by': str(admin_id),
        'approved_at': datetime.now().isoformat()
    })


def reject_news(news_id: str, admin_id: int, reason: str = "") -> bool:
    """رفض خبر"""
    return update_news(news_id, {
        'status': 'rejected',
        'rejected_by': str(admin_id),
        'rejected_at': datetime.now().isoformat(),
        'rejection_reason': reason
    })


def delete_news(news_id: str) -> bool:
    """حذف خبر (soft delete)"""
    return update_news(news_id, {'is_deleted': True})


def increment_views(news_id: str) -> bool:
    """زيادة عدد المشاهدات"""
    news = get_news(news_id)
    if news:
        current = news.get('views', 0)
        return update_news(news_id, {'views': current + 1})
    return False


def increment_shares(news_id: str) -> bool:
    """زيادة عدد المشاركات"""
    news = get_news(news_id)
    if news:
        current = news.get('shares', 0)
        return update_news(news_id, {'shares': current + 1})
    return False


def search_news(query: str, limit: int = 20) -> List[Dict]:
    """البحث في الأخبار"""
    all_news = get_news_list(status='approved', limit=100)
    results = []
    query_lower = query.lower()
    
    for news in all_news:
        title = news.get('title', '').lower()
        content = news.get('content', '').lower()
        if query_lower in title or query_lower in content:
            results.append(news)
            if len(results) >= limit:
                break
    
    return results


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

# ==================== دوال الإعجابات والمشاركات ====================

def increment_likes(news_id: str) -> bool:
    """زيادة عدد الإعجابات بخبر"""
    try:
        news = get_news(news_id)
        if news:
            current = news.get('likes', 0)
            return firebase_update(f"news/{news_id}", {'likes': current + 1})
        return False
    except Exception:
        return False


def increment_dislikes(news_id: str) -> bool:
    """زيادة عدد عدم الإعجاب بخبر"""
    try:
        news = get_news(news_id)
        if news:
            current = news.get('dislikes', 0)
            return firebase_update(f"news/{news_id}", {'dislikes': current + 1})
        return False
    except Exception:
        return False


def increment_views(news_id: str) -> bool:
    """زيادة عدد المشاهدات"""
    try:
        news = get_news(news_id)
        if news:
            current = news.get('views', 0)
            return firebase_update(f"news/{news_id}", {'views': current + 1})
        return False
    except Exception:
        return False


def increment_shares(news_id: str) -> bool:
    """زيادة عدد المشاركات"""
    try:
        news = get_news(news_id)
        if news:
            current = news.get('shares', 0)
            return firebase_update(f"news/{news_id}", {'shares': current + 1})
        return False
    except Exception:
        return False