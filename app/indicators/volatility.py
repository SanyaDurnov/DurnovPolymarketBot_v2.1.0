import numpy as np
import pandas as pd
from typing import Optional


class VolatilityCalculator:
    """
    Расчет исторической волатильности для прогнозирования движения цен.

    Использует exponential weighted standard deviation логарифмических доходов
    для учета volatility clustering (свойство крипторынков, где периоды
    высокой волатильности следуют друг за другом).
    """

    @staticmethod
    def calculate_volatility(
        close_prices: pd.Series,
        period: int = 10,
        ewm_alpha: float = 0.2,
    ) -> Optional[float]:
        """
        Рассчитать историческую волатильность на последних N свечах.

        Args:
            close_prices: Series с ценами закрытия
            period: количество последних свечей для расчета (по умолчанию 10)
            ewm_alpha: параметр для exponential weighting (0.1–0.3)
        Returns:
            Волатильность в процентах (например, 2.45 для 2.45%)
            или None, если данных недостаточно.
        """
        if close_prices is None or len(close_prices) < period:
            return None

        recent = close_prices.tail(period)

        # Логарифмические доходности
        returns = np.log(recent / recent.shift(1)).dropna()
        if len(returns) < 2:
            return None

        # EWMA-стандартное отклонение
        ewm_std = returns.ewm(alpha=ewm_alpha, adjust=False).std()
        volatility = ewm_std.iloc[-1]

        return float(volatility * 100.0)

    @staticmethod
    def calculate_for_df(
        df: pd.DataFrame,
        period: int = 20,
        ewm_alpha: float = 0.2,
    ) -> Optional[float]:
        """
        Рассчитать волатильность за период одной свечи df.

        Если df это 1m свечи → вернёт волатильность за 1 минуту (% в минуту)
        Если df это 1h свечи → вернёт волатильность за 1 час (% в час)
        Если df это 15m свечи → вернёт волатильность за 15 минут (% в 15 минут)

        Args:
            df: DataFrame с OHLCV данными
            period: период для расчётов
            ewm_alpha: alpha для exponential weighted moving

        Returns:
            Волатильность в процентах или None
        """
        if df is None or df.empty or len(df) < 2:
            return None
        if "close" not in df.columns:
            return None

        df = df.copy()

        # Логарифмические возвраты
        df["log_return"] = np.log(df["close"] / df["close"].shift(1))

        returns = df["log_return"].dropna()

        if len(returns) < 2:
            return None

        # EWM волатильность (стандартное отклонение)
        ewm_var = returns.ewm(alpha=ewm_alpha, adjust=False).var()
        volatility = np.sqrt(ewm_var.iloc[-1])

        return max(0.0, volatility * 100.0) if not np.isnan(volatility) else None
