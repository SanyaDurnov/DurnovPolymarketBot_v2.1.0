"""
Хранилище состояния веб-интерфейса Polymarket_bot_V2.
"""

from typing import Dict, Any, Optional
import threading
import time


class StatsStore:
    """
    Хранилище статистики и состояния для веб-интерфейса.
    """

    def __init__(self):
        self._stats: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def update_stats(self, key: str, value: Any) -> None:
        """Обновить статистику."""
        with self._lock:
            self._stats[key] = {
                'value': value,
                'timestamp': time.time()
            }

    def get_stats(self, key: str) -> Optional[Dict[str, Any]]:
        """Получить статистику по ключу."""
        with self._lock:
            return self._stats.get(key)

    def get_all_stats(self) -> Dict[str, Any]:
        """Получить всю статистику."""
        with self._lock:
            return self._stats.copy()

    def clear_stats(self) -> None:
        """Очистить всю статистику."""
        with self._lock:
            self._stats.clear()

    def get_recent_stats(self, max_age_seconds: float = 300) -> Dict[str, Any]:
        """Получить статистику, обновленную не позднее чем max_age_seconds секунд назад."""
        current_time = time.time()
        with self._lock:
            return {
                key: data for key, data in self._stats.items()
                if current_time - data.get('timestamp', 0) <= max_age_seconds
            }


# Глобальный экземпляр хранилища статистики
stats_store = StatsStore()