"""
Дополнительная конфигурация приложения Polymarket_bot_V2.
"""

# Импортируем значения из главного config.py
from app import config as main_config

# === КОНФИГУРАЦИЯ ПОИСКА РЫНКОВ ===
# Автоматическая генерация фильтров на основе текущего времени
auto_generate_filters = True

# Список монет для автоматической генерации фильтров
coins = ["Bitcoin", "Ethereum", "Solana"]

# Ручной фильтр поиска рынков (используется если auto_generate_filters = False)
market_search_filter = ["Bitcoin", "Ethereum", "Solana"]

# === НАСТРОЙКИ GAMMA API ===
# Использовать Gamma API для получения рынков
use_gamma_api = True

# Тег для фильтрации рынков в Gamma API
# NOTE: Bitcoin Up/Down markets have NO tags, so we don't use tag filtering
gamma_api_tag = getattr(main_config, 'GAMMA_API_TAG', None)  # Из config.py (None = no tag filter)
gamma_api_tag_id = None  # Если None, будет определен автоматически по gamma_api_tag

# Фильтры состояний рынков
gamma_api_active_only = True
gamma_api_closed = False

# === НАСТРОЙКИ CLOB API ===
# Максимальное количество страниц для загрузки рынков через CLOB API
clob_api_max_pages = 100

# === ОГРАНИЧЕНИЯ ===
# Максимальное количество рынков для загрузки (0 = без ограничений)
max_markets_limit = 0  # Без ограничений

# === КЭШ РЫНКОВ ===
# Интервал обновления кэша рынков в минутах
markets_update_interval_minutes = getattr(main_config, 'MARKETS_UPDATE_INTERVAL_MINUTES', 15)

# === ЛОГИРОВАНИЕ ===
# Упрощенные логи (меньше деталей для лучшей производительности)
lite_logs = True

# Отключить verbose логи polymarket клиента (фильтры, кэш)
disable_polymarket_verbose_logs = True

# === ФИЛЬТРЫ ПО ВРЕМЕНИ ===
# Удалять рынки, которые начались больше чем N минут назад (0 = не фильтровать)
filter_markets_started_minutes_ago = 15  # Отбрасывать рынки, начавшиеся более 15 минут назад

# Удалять рынки, которые начнутся позже чем через N минут (0 = не фильтровать)
filter_markets_starting_within_minutes = 20  # Отбрасывать рынки, которые начнутся позже чем через 20 минут

# === MARKET PRE-SELECTOR ===
# Время поиска лучших рынков для входа (минут)
best_markets_pre_selector_minutes_ahead = 10  # Искать рынки, начинающиеся в ближайшие 10 минут

# === ЦВЕТА СВЕЧЕЙ ===
CANDLE_COLORS = {
    'bullish': '#00C853',  # Зеленый для бычьих свечей
    'bearish': '#D32F2F',  # Красный для медвежьих свечей
    'doji': '#FF9800',     # Оранжевый для дожи
    'neutral': '#9E9E9E'   # Серый для нейтральных
}


# Создаем объект конфигурации для совместимости
class AppConfig:
    """Класс конфигурации приложения."""

    def __init__(self):
        # === КОНФИГУРАЦИЯ ПОИСКА РЫНКОВ ===
        self.auto_generate_filters = auto_generate_filters
        self.market_search_filter = market_search_filter
        self.coins = coins

        # === НАСТРОЙКИ GAMMA API ===
        self.use_gamma_api = use_gamma_api
        self.gamma_api_tag = gamma_api_tag
        self.gamma_api_tag_id = gamma_api_tag_id
        self.gamma_api_active_only = gamma_api_active_only
        self.gamma_api_closed = gamma_api_closed

        # === НАСТРОЙКИ CLOB API ===
        self.clob_api_max_pages = clob_api_max_pages

        # === ОГРАНИЧЕНИЯ ===
        self.max_markets_limit = max_markets_limit

        # === КЭШ РЫНКОВ ===
        self.markets_update_interval_minutes = markets_update_interval_minutes

        # === ЛОГИРОВАНИЕ ===
        self.lite_logs = lite_logs
        self.disable_polymarket_verbose_logs = disable_polymarket_verbose_logs

        # === ФИЛЬТРЫ ПО ВРЕМЕНИ ===
        self.filter_markets_started_minutes_ago = filter_markets_started_minutes_ago
        self.filter_markets_starting_within_minutes = filter_markets_starting_within_minutes

        # === MARKET PRE-SELECTOR ===
        self.best_markets_pre_selector_minutes_ahead = best_markets_pre_selector_minutes_ahead


# Глобальный экземпляр конфигурации
app_config = AppConfig()
