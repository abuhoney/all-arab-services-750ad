#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
╔══════════════════════════════════════════════════════════════════╗
║                  CLASS: LanguageManager                         ║
║               فئة إدارة اللغة والنصوص الديناميكية               ║
╚══════════════════════════════════════════════════════════════════╝
"""

from typing import Dict, Any, Optional
import re
from firebase_core import firebase_get, firebase_set


class LanguageManager:
    """
    فئة إدارة اللغة والنصوص
    تدعم النصوص الديناميكية والترجمة التلقائية
    """
    
    _instance = None
    _texts_cache: Dict[str, Dict[str, str]] = {}
    _variables_cache: Dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.default_language = "ar"
        self._load_texts()
        self._load_variables()
    
    def _load_texts(self) -> None:
        """تحميل النصوص من Firebase"""
        texts = firebase_get("system_registry/texts") or {}
        self._texts_cache = texts
    
    def _load_variables(self) -> None:
        """تحميل المتغيرات من Firebase"""
        variables = firebase_get("system_registry/variables") or {}
        self._variables_cache = variables
    
    def get_text(self, text_id: str, language: str = None, context: Dict = None) -> str:
        """
        الحصول على نص معين مع استبدال المتغيرات
        
        Args:
            text_id: معرف النص
            language: اللغة المطلوبة (افتراضي العربية)
            context: سياق لاستبدال المتغيرات الإضافية
        
        Returns:
            النص مع استبدال المتغيرات
        """
        if language is None:
            language = self.default_language
        
        # البحث عن النص في الكاش
        text_data = self._texts_cache.get(text_id, {})
        text = text_data.get(language, text_data.get('ar', text_id))
        
        # استبدال المتغيرات
        text = self._replace_placeholders(text, context)
        
        return text
    
    def _replace_placeholders(self, text: str, context: Dict = None) -> str:
        """
        استبدال المتغيرات في النص
        
        الصيغة المدعومة:
        - {#VAR_NAME} -> قيمة المتغير من Firebase
        - {#VAR_NAME:format} -> مع تنسيق خاص
        - {user.first_name} -> من سياق المستخدم
        """
        if not text:
            return text
        
        def replacer(match):
            var_expr = match.group(1)
            parts = var_expr.split(':')
            var_name = parts[0]
            format_spec = parts[1] if len(parts) > 1 else None
            
            # البحث في المتغيرات من Firebase
            if var_name in self._variables_cache:
                value = self._variables_cache[var_name].get('value', var_name)
            # البحث في السياق
            elif context and var_name in context:
                value = context[var_name]
            # البحث في السمات (مثل user.first_name)
            elif '.' in var_name and context:
                obj_name, attr = var_name.split('.')
                obj = context.get(obj_name, {})
                if hasattr(obj, attr):
                    value = getattr(obj, attr)
                elif isinstance(obj, dict):
                    value = obj.get(attr, var_name)
                else:
                    value = var_name
            else:
                value = f"{{{var_name}}}"
            
            # تطبيق التنسيق
            if format_spec == "currency":
                return f"{value} 💎"
            elif format_spec == "uppercase":
                return str(value).upper()
            elif format_spec == "lowercase":
                return str(value).lower()
            elif format_spec == "capitalize":
                return str(value).capitalize()
            
            return str(value)
        
        # استبدال {#...} و {user.xxx}
        pattern = r'\{([#\w\.]+)(?::\w+)?\}'
        return re.sub(pattern, replacer, text)
    
    def get_variable(self, var_name: str, default: Any = None) -> Any:
        """الحصول على قيمة متغير ديناميكي"""
        var_data = self._variables_cache.get(var_name, {})
        return var_data.get('value', default)
    
    def set_variable(self, var_name: str, value: Any, var_type: str = "str", description: str = "") -> bool:
        """تعيين قيمة متغير ديناميكي"""
        var_data = {
            "value": value,
            "type": var_type,
            "description": description,
            "updated_at": __import__('datetime').datetime.now().isoformat()
        }
        result = firebase_set(f"system_registry/variables/{var_name}", var_data)
        if result:
            self._variables_cache[var_name] = var_data
        return result
    
    def update_text(self, text_id: str, language: str, content: str, description: str = "") -> bool:
        """تحديث نص معين"""
        current = self._texts_cache.get(text_id, {})
        current[language] = content
        if description:
            current['description'] = description
        
        result = firebase_set(f"system_registry/texts/{text_id}", current)
        if result:
            self._texts_cache[text_id] = current
        return result
    
    def get_all_texts(self) -> Dict:
        """الحصول على جميع النصوص"""
        return self._texts_cache.copy()
    
    def get_all_variables(self) -> Dict:
        """الحصول على جميع المتغيرات"""
        return self._variables_cache.copy()
    
    def reload(self) -> None:
        """إعادة تحميل جميع البيانات من Firebase"""
        self._load_texts()
        self._load_variables()


# إنشاء نسخة واحدة من مدير اللغة
language_manager = LanguageManager()