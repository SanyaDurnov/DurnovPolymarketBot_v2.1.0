"""
Модуль для автоматической генерации фильтров поиска рынков на основе текущего времени.

Генерирует фильтры по шаблонам:
1. {coin} Up or Down - {month} {day}, {time1}-{time2} ET (15-минутные интервалы)
2. {coin} Up or Down - {month} {day}, {time} ET (часовые)
3. {coin} Up or Down - {month} {day}, {time1}-{time2} ET (4-часовые)
"""

import logging
from datetime import datetime, timedelta
from typing import List
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Eastern Time (ET) - часовой пояс Polymarket
ET_TIMEZONE = ZoneInfo("America/New_York")

# Названия месяцев
MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


def get_polymarket_time() -> datetime:
    """
    Получить текущее время в часовом поясе Polymarket (Eastern Time).

    Returns:
        datetime объект в часовом поясе ET
    """
    return datetime.now(ET_TIMEZONE)


def format_time_12h(hour: int, minute: int = 0, always_show_minutes: bool = False) -> str:
    """
    Форматировать время в 12-часовом формате с AM/PM.

    Args:
        hour: Час (0-23)
        minute: Минута (0-59)
        always_show_minutes: Если True, всегда показывает минуты (даже если 0)

    Returns:
        Строка в формате "9:15AM" или "12:00PM" или "9AM"
    """
    hour = hour % 24
    if hour == 0:
        period = "AM"
        display_hour = 12
    elif hour < 12:
        period = "AM"
        display_hour = hour
    elif hour == 12:
        period = "PM"
        display_hour = 12
    else:
        period = "PM"
        display_hour = hour - 12

    if minute == 0 and not always_show_minutes:
        return f"{display_hour}{period}"
    else:
        return f"{display_hour}:{minute:02d}{period}"


def generate_filters(coins: List[str], current_time: datetime | None = None) -> List[str]:
    """
    Генерировать список фильтров для поиска рынков на основе текущего времени.

    Args:
        coins: Список монет (например, ["Bitcoin", "Ethereum"])
        current_time: Текущее время в ET (если None, используется текущее время)

    Returns:
        Список фильтров для поиска рынков
    """
    if current_time is None:
        current_time = get_polymarket_time()

    filters = []
    base_date = current_time.date()
    month_name = MONTH_NAMES[current_time.month - 1]
    day = current_time.day
    current_hour = current_time.hour
    current_minute = current_time.minute

    # Генерируем фильтры для большего диапазона времени (прошедшие и будущие часы)
    # Начинаем с прошедших часов и до будущих
    for coin in coins:
        # 1. 15-минутные интервалы для будущих часов
        # Генерируем для часов: current_hour, current_hour+1, current_hour+2, current_hour+3
        for hour_offset in [0, 1, 2, 3]:  # Будущие часы
            target_hour_raw = current_hour + hour_offset
            target_date = base_date
            if target_hour_raw >= 24:
                target_hour = target_hour_raw % 24
                target_date = target_date + timedelta(days=1)
            else:
                target_hour = target_hour_raw
            target_month_name = MONTH_NAMES[target_date.month - 1]
            target_day = target_date.day

            # Генерируем 15-минутные интервалы
            intervals = [
                (0, 15),   # 10:00AM-10:15AM
                (15, 30),  # 10:15AM-10:30AM
                (30, 45),  # 10:30AM-10:45AM
                (45, 60),  # 10:45AM-11:00AM
            ]

            for start_min, end_min in intervals:
                # Для start_min = 0 нужно показывать минуты (10:00AM вместо 10AM)
                start_time = format_time_12h(
                    target_hour,
                    start_min,
                    always_show_minutes=(start_min == 0),
                )
                start_date = target_date
                end_date = target_date
                if end_min == 60:
                    end_hour_raw = target_hour + 1
                    if end_hour_raw >= 24:
                        end_hour = end_hour_raw % 24
                        end_date = end_date + timedelta(days=1)
                    else:
                        end_hour = end_hour_raw
                    # Переход на следующий час - всегда показываем минуты (11:00AM вместо 11AM)
                    end_time = format_time_12h(end_hour, 0, always_show_minutes=True)
                else:
                    end_time = format_time_12h(target_hour, end_min, always_show_minutes=True)

                if end_date != start_date:
                    end_month_name = MONTH_NAMES[end_date.month - 1]
                    filter_str = (
                        f"{coin} Up or Down - {target_month_name} {target_day}, "
                        f"{start_time} ET - {end_month_name} {end_date.day}, {end_time} ET"
                    )
                else:
                    filter_str = (
                        f"{coin} Up or Down - {target_month_name} {target_day}, "
                        f"{start_time}-{end_time} ET"
                    )
                filters.append(filter_str)

        # 2. Часовые интервалы (текущий час и следующий час)
        # Формат: "Bitcoin Up or Down - January 13, 10AM ET"
        for hour_offset in [0, 1]:  # Текущий час и следующий
            target_hour_raw = current_hour + hour_offset
            target_date = base_date
            if target_hour_raw >= 24:
                target_hour = target_hour_raw % 24
                target_date = target_date + timedelta(days=1)
            else:
                target_hour = target_hour_raw
            hour_time = format_time_12h(target_hour, 0)
            hour_month_name = MONTH_NAMES[target_date.month - 1]
            filter_str = f"{coin} Up or Down - {hour_month_name} {target_date.day}, {hour_time} ET"
            filters.append(filter_str)

        # 3. 4-часовые интервалы (текущий 4-часовой интервал)
        # Интервалы начинаются в: 8AM, 12PM, 4PM, 8PM (каждые 4 часа)
        # Определяем, в каком 4-часовом интервале мы находимся
        four_hour_starts = [8, 12, 16, 20]  # 8AM, 12PM, 4PM, 8PM

        # Находим ближайший прошедший 4-часовой интервал
        current_4h_start = None
        for start_hour in reversed(four_hour_starts):  # Проверяем от большего к меньшему
            if current_hour >= start_hour:
                current_4h_start = start_hour
                break

        # Если текущий час меньше 8AM, используем предыдущий день 8PM-12AM
        if current_4h_start is None:
            # Используем 8PM-12AM предыдущего дня
            prev_day = current_time - timedelta(days=1)
            prev_month_name = MONTH_NAMES[prev_day.month - 1]
            prev_day_num = prev_day.day
            start_time = format_time_12h(20, 0)  # 8PM
            end_time = format_time_12h(0, 0)  # 12AM (полночь)
            end_day = prev_day + timedelta(days=1)
            end_month_name = MONTH_NAMES[end_day.month - 1]
            filter_str = (
                f"{coin} Up or Down - {prev_month_name} {prev_day_num}, {start_time} ET - "
                f"{end_month_name} {end_day.day}, {end_time} ET"
            )
            filters.append(filter_str)
        else:
            # Определяем конец 4-часового интервала
            if current_4h_start == 20:  # 8PM
                # 8PM-12AM (полночь следующего дня) - но это уже следующий день
                # Используем текущий день для начала
                start_time = format_time_12h(20, 0)  # 8PM
                end_time = format_time_12h(0, 0)  # 12AM
                # Проверяем, не перешли ли мы уже в следующий день
                if current_hour >= 20:
                    # Используем текущий день
                    end_day = current_time + timedelta(days=1)
                    end_month_name = MONTH_NAMES[end_day.month - 1]
                    filter_str = (
                        f"{coin} Up or Down - {month_name} {day}, {start_time} ET - "
                        f"{end_month_name} {end_day.day}, {end_time} ET"
                    )
                else:
                    # Используем предыдущий день
                    prev_day = current_time - timedelta(days=1)
                    prev_month_name = MONTH_NAMES[prev_day.month - 1]
                    prev_day_num = prev_day.day
                    end_day = prev_day + timedelta(days=1)
                    end_month_name = MONTH_NAMES[end_day.month - 1]
                    filter_str = (
                        f"{coin} Up or Down - {prev_month_name} {prev_day_num}, {start_time} ET - "
                        f"{end_month_name} {end_day.day}, {end_time} ET"
                    )
                filters.append(filter_str)
            else:
                # Обычный 4-часовой интервал в пределах дня
                # Формат: "8:00AM-12:00PM ET"
                end_hour = current_4h_start + 4
                start_time = format_time_12h(current_4h_start, 0, always_show_minutes=True)
                end_time = format_time_12h(end_hour, 0, always_show_minutes=True)
                filter_str = f"{coin} Up or Down - {month_name} {day}, {start_time}-{end_time} ET"
                filters.append(filter_str)

    return filters
