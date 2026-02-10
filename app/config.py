"""
Главная конфигурация Polymarket_bot_V2.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Загружаем .env файл
load_dotenv()

# === РЕЖИМ РАБОТЫ ===
SIM_MODE = True  # True = симуляция, False = реальная торговля

# === ВЫБОР СТРАТЕГИИ ===
# "default" - стандартная стратегия с auto_entry и position_manager
# "soft_trading" - мягкая стратегия без auto_entry (position_manager_soft_trading)
TRADING_STRATEGY = os.getenv("TRADING_STRATEGY", "default")  # "default" или "soft_trading"

# === POLYMARKET API ===
POLYMARKET_API_URL = os.getenv("POLYMARKET_API_URL", "https://clob.polymarket.com")

# Активный аккаунт
POLYMARKET_ACTIVE_ACCOUNT = int(os.getenv("POLYMARKET_ACTIVE_ACCOUNT", "1"))

# Аккаунт 1
POLYMARKET_WALLET_ADDRESS_1 = os.getenv("POLYMARKET_WALLET_ADDRESS_1", "")
POLYMARKET_PRIVATE_KEY_1 = os.getenv("POLYMARKET_PRIVATE_KEY_1", "")
POLYMARKET_API_KEY_1 = os.getenv("POLYMARKET_API_KEY_1", "")
POLYMARKET_API_SECRET_1 = os.getenv("POLYMARKET_API_SECRET_1", "")
POLYMARKET_API_PASSPHRASE_1 = os.getenv("POLYMARKET_API_PASSPHRASE_1", "")

# Аккаунт 2
POLYMARKET_WALLET_ADDRESS_2 = os.getenv("POLYMARKET_WALLET_ADDRESS_2", "")
POLYMARKET_PRIVATE_KEY_2 = os.getenv("POLYMARKET_PRIVATE_KEY_2", "")
POLYMARKET_API_KEY_2 = os.getenv("POLYMARKET_API_KEY_2", "")
POLYMARKET_API_SECRET_2 = os.getenv("POLYMARKET_API_SECRET_2", "")
POLYMARKET_API_PASSPHRASE_2 = os.getenv("POLYMARKET_API_PASSPHRASE_2", "")
ACCOUNT_2_TYPE = os.getenv("ACCOUNT_2_TYPE", "polymarket")  # 'polymarket' или 'web3'

# Активные настройки (для обратной совместимости)
POLYMARKET_WALLET_ADDRESS = globals()[f"POLYMARKET_WALLET_ADDRESS_{POLYMARKET_ACTIVE_ACCOUNT}"]
POLYMARKET_PRIVATE_KEY = globals()[f"POLYMARKET_PRIVATE_KEY_{POLYMARKET_ACTIVE_ACCOUNT}"]
POLYMARKET_API_KEY = globals()[f"POLYMARKET_API_KEY_{POLYMARKET_ACTIVE_ACCOUNT}"]
POLYMARKET_API_SECRET = globals()[f"POLYMARKET_API_SECRET_{POLYMARKET_ACTIVE_ACCOUNT}"]
POLYMARKET_API_PASSPHRASE = globals()[f"POLYMARKET_API_PASSPHRASE_{POLYMARKET_ACTIVE_ACCOUNT}"]

# === BINANCE API ===
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
BINANCE_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# === MARKETS FILTERS ===
AUTO_GENERATE_FILTERS = True  # Автоматическая генерация фильтров
COINS = ["Bitcoin", "Ethereum", "Solana"]
# NOTE: Bitcoin Up/Down markets have NO tags! Tag filtering blocks them.
# Set to None when using AUTO_GENERATE_FILTERS to avoid filtering out these markets
GAMMA_API_TAG = None  # Was: "cryptocurrency" - but Up/Down markets aren't tagged!
GAMMA_API_ACTIVE_ONLY = True
GAMMA_API_CLOSED = False

# Интервал обновления кэша рынков
MARKETS_UPDATE_INTERVAL_MINUTES = 15  # Обновлять кэш рынков каждые N минут

# Фильтрация по времени начала рынка
FILTER_MARKETS_STARTED_MINUTES_AGO = 10  # Удалить рынки, начавшиеся более N минут назад
FILTER_MARKETS_STARTING_WITHIN_MINUTES = 10  # Удалить рынки, начинающиеся позже чем через N минут

# === SIMULATION ===
SIMULATION_INITIAL_BALANCE = 1000.0
SIMULATION_TRADING_FEE_PCT = 0.02  # 2%
SIMULATION_MAX_POSITION_PCT = 0.3  # Максимум 30% баланса на одну позицию
SIMULATION_POSITION_SIZE_PCT = 0.1  # Размер входа 10% баланса

# === AUTO-ENTRY SYSTEM ===
# Размер первой позиции (% от баланса)
FIRST_POSITION_SIZE_PCT = 10.0  # 10% от баланса

# Максимальная цена для входа
MAX_PRICE_FOR_FIRST_ENTRY = 0.52

# Настройки времени входа
FIRST_ENTRY_MINUTES_BEFORE_START = 1  # Минуты до старта рынка для запуска входа

# Настройки постепенной покупки
FIRST_ENTRY_ITERATIONS = 2  # Количество итераций покупки
FIRST_ENTRY_ITERATION_DELAY = 20.0  # Секунды между итерациями

# === POSITION MANAGEMENT ===
# Настройки для управления позициями после первого входа
MATH_PROB_FOR_OPPOSITE = 0.35  # Минимальная вероятность для входа в противоположную сторону
PRICE_ENTRY_FOR_OPPOSITE = 0.35  # Максимальная цена для входа в противоположную сторону
W1_PROFIT_PCT = 20.0  # Гарантированная прибыль (%) от первого входа при входе в противоположную сторону
W2_ADDITIONAL_PROFIT_PCT = 10.0  # Дополнительная прибыль (%) для второго входа в исходную сторону
PERCENT_FOR_PRICE_REDUCE = 15.0  # Минимальное снижение цены (%) для дополнительного входа в исходную сторону

# Настройки входа в рынки
ENTER_TO_1H_MARKETS = True  # Входить ли в 1h рынки
ENTER_TO_15M_MARKETS = True  # Входить ли в 15m рынки
H1_MARKETS_NUMBER_TO_ENTER = 1  # Сколько 1h рынков
M15_MARKETS_NUMBER_TO_ENTER = 1  # Сколько 15m рынков

# Настройки покупки
AMOUNT_OF_ONE_BUY_IN_LOOP = 5.0  # $ за одну покупку в цикле
LOOP_DELAY = 1.0  # Задержка между покупками (сек)

# === PRICE MONITORING ===
PRICE_BUFFER_SIZE = 1000  # Размер буфера цен
KLINE_BUFFER_SIZE_1M = 200  # Буфер 1m свечей
KLINE_BUFFER_SIZE_5M = 100  # Буфер 5m свечей
KLINE_HISTORY_LIMIT_1M = 1000  # Загружать N исторических 1m свечей

# Источник данных: Binance для индикаторов, Polymarket для текущих цен

# === INDICATORS ===
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
ATR_PERIOD = 14
SMA_PERIOD = 5

# Momentum таймфреймы: (value, type) пары
MOMENTUM_TIMEFRAMES = [
    (1, "minute"),    # 1m
    (5, "minute"),    # 5m
    (15, "minute"),   # 15m
    (1, "hour"),      # 1h
]

# Volatility
VOLATILITY_TIMEFRAMES = ["1m", "5m", "15m", "1h"]
VOLATILITY_PERIOD = 14
VOLATILITY_EWM_ALPHA = 0.1

# Hybrid volatility для KF расчетов
VOLATILITY_FOR_KF_WEIGHT_ATR = 0.6  # 60% ATR
VOLATILITY_FOR_KF_WEIGHT_CURRENT = 0.4  # 40% текущая
VOLATILITY_FLOOR = 0.005  # Минимум 0.5%

# === PROBABILITY ANALYSIS ===
EXIT_HIT_THRESHOLD = 0.3  # p_hit должен быть >= 30%
EXIT_TERMINAL_THRESHOLD = 0.45  # p_terminal должен быть >= 45%

# === MARKET MONITORING ===
MARKET_MONITOR_INTERVAL = 1  # Интервал проверки завершенных рынков в минутах

# === WEB UI ===
WEB_HOST = "0.0.0.0"
WEB_PORT = 8000

# === LOGGING ===
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LITE_LOGS = True  # Упрощенные логи (убирает детальные логи PriceMonitor)

# === PROBABILITY LOGGING ===
PROBABILITY_LOG_INTERVAL_SECONDS = 15  # Интервал логирования REACH CALC (секунды)
PROBABILITY_LOG_VOLATILITY = True  # Выводить волатильность в логах

# === PRICE MONITORING ===
PRICE_BUFFER_SIZE = 1000  # Размер буфера цен
KLINE_BUFFER_SIZE_1M = 200  # Буфер 1m свечей
KLINE_BUFFER_SIZE_5M = 100  # Буфер 5m свечей
KLINE_HISTORY_LIMIT_1M = 100  # Загружать N исторических 1m свечей

# === CANDLE ANALYSIS ===
CANDLE_COLORS = {
    'bullish': '#00C853',  # Зеленый для бычьих свечей
    'bearish': '#D32F2F',  # Красный для медвежьих свечей
    'doji': '#FF9800',     # Оранжевый для дожи
    'neutral': '#9E9E9E'   # Серый для нейтральных
}

CANDLE_STREAK_TIMEFRAMES = ["1m", "5m", "15m", "1h"]  # Таймфреймы для анализа свечей
CANDLE_LOG_INTERVAL_SECONDS = 30  # Интервал логирования анализа свечей
LOG_CANDLE_ANALYSIS = False  # Включить логирование анализа свечей
MIN_CANDLES_FOR_ANALYSIS = 10  # Минимальное количество свечей для анализа

# === MONITORING ===
MONITOR_LOG_INTERVAL_SECONDS = 60  # Интервал логирования мониторинга

# === MOMENTUM ===
MOMENTUM_RULE_ENABLE = True  # Включить правила momentum
MOMENTUM_RULE_SETS = [
    {"1m": 0.5, "5m": 0.3, "15m": 0.2},  # Все положительные с порогами
    {"1m": -0.5, "5m": -0.3, "15m": -0.2},  # Все отрицательные с порогами
]

# === SIGNALS ===
SIGNAL_CHECK_INTERVAL_SECONDS = 60  # Интервал проверки сигналов
SIGNAL_COOLDOWN = 300  # Перезарядка сигналов (секунды)

# === SOFT TRADING STRATEGY ===
# Арбитражная стратегия через усреднение позиций обеих сторон
SOFT_TRADE_EDGE_ENTER = 5.0  # Минимальный edge для входа (%)
SOFT_TRADE_FIRST_POSITION_USD = 10.0  # Размер первой позиции ($)
SOFT_TRADE_MAX_LOSS_PCT = 5.0  # Максимальный убыток от текущей позиции при докупке (%)
SOFT_TRADE_MIN_IMPROVEMENT_PCT = 2.0  # Минимальное улучшение средней цены для докупки (%)
SOFT_TRADE_CHECK_INTERVAL = 1.0  # Интервал проверки рынков (сек)
SOFT_TRADE_TARGET_SUM = 0.98  # Целевая сумма avg_UP + avg_DOWN для логирования
SOFT_TRADE_COOLDOWN_AFTER_BUY = 5.0  # Задержка после покупки перед следующей (сек)

# Убрано дублирование - все определения выше


# Создаем объект settings для совместимости
class Settings:
    """Класс настроек для совместимости с импортами."""

    def __init__(self):
        self.polymarket_api_url = POLYMARKET_API_URL
        self.polymarket_wallet_address = POLYMARKET_WALLET_ADDRESS
        self.polymarket_private_key = POLYMARKET_PRIVATE_KEY
        self.polymarket_api_key = POLYMARKET_API_KEY
        self.polymarket_api_secret = POLYMARKET_API_SECRET
        self.polymarket_api_passphrase = POLYMARKET_API_PASSPHRASE
        self.binance_api_key = BINANCE_API_KEY
        self.binance_api_secret = BINANCE_API_SECRET
        self.binance_symbols = BINANCE_SYMBOLS

        # Добавляем недостающие атрибуты из импортов
        self.price_buffer_size = PRICE_BUFFER_SIZE
        self.kline_buffer_size_1m = KLINE_BUFFER_SIZE_1M
        self.kline_buffer_size_5m = KLINE_BUFFER_SIZE_5M
        self.kline_history_limit_1m = KLINE_HISTORY_LIMIT_1M
        self.rsi_period = RSI_PERIOD
        self.macd_fast = MACD_FAST
        self.macd_slow = MACD_SLOW
        self.macd_signal = MACD_SIGNAL
        self.atr_period = ATR_PERIOD
        self.sma_period = SMA_PERIOD
        self.lite_logs = LITE_LOGS


# Глобальный экземпляр настроек
settings = Settings()
