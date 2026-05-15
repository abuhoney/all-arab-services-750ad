#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
╔══════════════════════════════════════════════════════════════════╗
║                    CLASS: FirebaseCore                          ║
║              دوال Firebase الأساسية مع نظام Cache               ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import time
import json
import hashlib
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Tuple, Dict, Any, List
from collections import defaultdict

# ================== تجاوز SSL ==================
os.environ['PYTHONHTTPSVERIFY'] = '0'
os.environ['CURL_CA_BUNDLE'] = ''
os.environ['REQUESTS_CA_BUNDLE'] = ''

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

from bot_config import BotConfig

# ================== إعداد التسجيل الصامت ==================
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)
logger.propagate = False

# ================== نظام Cache ==================
_cache: Dict[str, Any] = {}
_cache_time: Dict[str, datetime] = {}

def invalidate_cache(path: str = None) -> None:
    """مسح الكاش بالكامل أو لجزء محدد"""
    global _cache, _cache_time
    if path:
        _cache.pop(path, None)
        _cache_time.pop(path, None)
    else:
        _cache.clear()
        _cache_time.clear()

def cached_firebase(ttl_seconds: int = BotConfig.CACHE_TTL):
    """ديكوريتور لإضافة التخزين المؤقت لدوال Firebase"""
    def decorator(func):
        @wraps(func)
        def wrapper(path: str, *args, **kwargs):
            now = datetime.now()
            cache_key = f"{func.__name__}:{path}"
            
            if cache_key in _cache and cache_key in _cache_time:
                if (now - _cache_time[cache_key]).total_seconds() < ttl_seconds:
                    return _cache[cache_key]
            
            result = func(path, *args, **kwargs)
            
            if result is not None:
                _cache[cache_key] = result
                _cache_time[cache_key] = now
            
            return result
        return wrapper
    return decorator

# ================== جلسة Firebase ==================
session = requests.Session()
session.verify = False

# ================== دوال Firebase الأساسية ==================
def firebase_get(path: str, default: Any = None) -> Any:
    """
    جلب بيانات من Firebase Realtime Database
    """
    try:
        resp = session.get(f"{BotConfig.FIREBASE_URL}/{path}.json", timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return data if data is not None else default
        return default
    except Exception:
        return default

def firebase_set(path: str, data: Any) -> bool:
    """
    تعيين بيانات في Firebase Realtime Database
    """
    try:
        resp = session.put(f"{BotConfig.FIREBASE_URL}/{path}.json", json=data, timeout=30)
        if resp.status_code == 200:
            invalidate_cache(path.split('/')[0])
            return True
        return False
    except Exception:
        return False

def firebase_push(path: str, data: Any) -> Optional[str]:
    """
    إضافة بيانات جديدة إلى Firebase Realtime Database (توليد ID تلقائي)
    """
    try:
        resp = session.post(f"{BotConfig.FIREBASE_URL}/{path}.json", json=data, timeout=30)
        if resp.status_code == 200:
            result = resp.json().get("name")
            invalidate_cache(path)
            return result
        return None
    except Exception:
        return None

def firebase_update(path: str, data: Any) -> bool:
    """
    تحديث بيانات جزئية في Firebase Realtime Database
    """
    try:
        resp = session.patch(f"{BotConfig.FIREBASE_URL}/{path}.json", json=data, timeout=30)
        if resp.status_code == 200:
            invalidate_cache(path.split('/')[0])
            return True
        return False
    except Exception:
        return False

def firebase_delete(path: str) -> bool:
    """
    حذف بيانات من Firebase Realtime Database
    """
    try:
        resp = session.delete(f"{BotConfig.FIREBASE_URL}/{path}.json", timeout=30)
        if resp.status_code == 200:
            invalidate_cache(path.split('/')[0])
            return True
        return False
    except Exception:
        return False

def test_firebase_connection() -> bool:
    """اختبار الاتصال بقاعدة البيانات"""
    try:
        test_data = {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "version": BotConfig.APP_VERSION
        }
        result = firebase_set("test_connection", test_data)
        if result:
            firebase_delete("test_connection")
            return True
        return False
    except Exception:
        return False