#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
╔══════════════════════════════════════════════════════════════════╗
║                     CLASS: BotConfig                            ║
║                  فئة الإعدادات المركزية للبوت                    ║
╚══════════════════════════════════════════════════════════════════╝
"""

from typing import List, Dict, Any
import os


class BotConfig:
    """
    فئة الإعدادات المركزية - تحتوي على جميع متغيرات البوت
    يمكن تعديل هذه القيم ديناميكياً عبر نظام الإدارة
    """
    
    # ===== إعدادات تيليجرام الأساسية =====
    BOT_TOKEN: str = "7560654484:AAEgkPzIvKr8FhPfag8QSo5zT28uaFzSNzs"
    API_ID: int = 28635681
    API_HASH: str = "9ab1acca768da671ab3f16eff541d999"
    ADMIN_IDS: List[int] = [7082122839]
    BOT_USERNAME: str = "@StoreReferralBot"
    NOTIFICATION_CHANNEL: str = "UsersGenerator"
    
    # ===== إعدادات Firebase =====
    FIREBASE_URL: str = "https://all-arab-services-default-rtdb.firebaseio.com"
    FIREBASE_API_KEY: str = "AIzaSyBm-ZwOv8oPd_0rms_2oesGz3fDmt5ogvA"
    FIREBASE_PROJECT_ID: str = "all-arab-services-750ad"
    FIREBASE_STORAGE_BUCKET: str = "all-arab-services-750ad.firebasestorage.app"
    
    # ===== إعدادات النظام =====
    APP_NAME: str = "All Arab Services"
    APP_VERSION: str = "6.0.0"
    WEB_URL: str = "https://all-arab-services-750ad.onrender.com"
    
    # ===== نظام النقاط والمكافآت (القيم الافتراضية - يمكن تعديلها ديناميكياً) =====
    POINTS_PER_SUBSCRIBE: int = 10
    POINTS_PER_REFERRAL: int = 50
    POINTS_PER_NEWS_SHARE: int = 5
    POINTS_DAILY_BONUS: int = 15
    POINTS_PER_VIEW: int = 1
    POINTS_VERIFICATION_REWARD: int = 50
    
    # ===== إعدادات الأخبار =====
    NEWS_PER_PAGE: int = 5
    MAX_NEWS_LENGTH: int = 4096
    MAX_TITLE_LENGTH: int = 200
    MAX_CONTENT_PREVIEW: int = 500
    
    # ===== إعدادات الوقت والتخزين المؤقت =====
    CACHE_TTL: int = 30
    BROADCAST_DELAY: float = 0.5
    FLOOD_WAIT_SLEEP: float = 1.0
    
    # ===== تفعيل/تعطيل الميزات =====
    ENABLE_POINTS_SYSTEM: bool = True
    ENABLE_REFERRAL_SYSTEM: bool = True
    ENABLE_AUTO_MODERATION: bool = True
    ENABLE_NOTIFICATIONS: bool = True
    ENABLE_OFFLINE_MODE: bool = True
    
    # ===== إعدادات التعدين =====
    MINING_INTERVAL: int = 3600
    MINING_POINTS_PER_HOUR: int = 30
    
    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """الحصول على قيمة إعداد معين (يدعم القيم الديناميكية)"""
        return getattr(cls, key, default)
    
    @classmethod
    def set(cls, key: str, value: Any) -> None:
        """تعيين قيمة إعداد معين (للتعديل الديناميكي)"""
        if hasattr(cls, key):
            setattr(cls, key, value)
    
    @classmethod
    def get_all_configs(cls) -> Dict[str, Any]:
        """الحصول على جميع الإعدادات كقاموس"""
        return {
            k: v for k, v in cls.__dict__.items()
            if not k.startswith('_') and not callable(v)
        }