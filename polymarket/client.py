import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from py_clob_client.client import ClobClient

from app.app_config import app_config
from app.config import settings
from app.filter_generator import generate_filters, get_polymarket_time


logger = logging.getLogger(__name__)

# Путь к файлу кэша рынков
MARKETS_CACHE_FILE = Path(__file__).parent.parent / "markets_cache.json"
# Путь к файлу времени последнего обновления
MARKETS_LAST_UPDATE_FILE = Path(__file__).parent.parent / "markets_last_update.json"
# Интервал обновления рынков (в минутах)
MARKETS_UPDATE_INTERVAL_MINUTES = 30


def check_geoblock() -> Optional[dict]:
    """Проверить геоблок на Polymarket и вывести результат в лог."""
    url = "https://polymarket.com/api/geoblock"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            logger.warning("Geoblock check: статус %s", response.status_code)
            return None
        data = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Geoblock check: ошибка запроса: %s", exc)
        return None

    ip_addr = data.get("ip")
    country = data.get("country")
    region = data.get("region")
    blocked = data.get("blocked")
    logger.info(
        "Geoblock: ip=%s country=%s region=%s blocked=%s",
        ip_addr,
        country,
        region,
        blocked,
    )
    if blocked:
        logger.warning("Geoblock: доступ заблокирован для страны %s", country)
    return data


class PolymarketClient:
    """
    Простая обёртка над официальным Polymarket CLOB Python client.
    """

    def __init__(self) -> None:
        # Проверяем, есть ли валидные API ключи (CLOB API keys имеют приоритет)
        has_clob_keys = (
            settings.polymarket_api_key
            and settings.polymarket_api_secret
            and settings.polymarket_api_passphrase
            and not settings.polymarket_api_key.startswith("your_")
            and not settings.polymarket_api_secret.startswith("your_")
            and not settings.polymarket_api_passphrase.startswith("your_")
        )

        # Проверяем приватный ключ (для генерации API ключей)
        has_private_key = (
            settings.polymarket_private_key
            and settings.polymarket_private_key.strip()
            and not settings.polymarket_private_key.startswith("your_")
        )

        if has_clob_keys:
            # Используем CLOB API ключи
            logger.info("Найдены CLOB API ключи, инициализируем клиент для торговли")
            try:
                # Проверяем версию py_clob_client и правильные параметры
                import py_clob_client
                from py_clob_client.clob_types import ApiCreds
                logger.info("py_clob_client version: %s", getattr(py_clob_client, '__version__', 'unknown'))

                # Используем правильный способ инициализации с ApiCreds
                creds = ApiCreds(
                    api_key=settings.polymarket_api_key,
                    api_secret=settings.polymarket_api_secret,
                    api_passphrase=settings.polymarket_api_passphrase
                )

                self._client = ClobClient(
                    host=settings.polymarket_api_url,
                    creds=creds,
                    chain_id=137,
                )

                logger.info("✅ Polymarket клиент инициализирован с CLOB API ключами через ApiCreds")
            except Exception as exc:  # noqa: BLE001
                logger.error("Не удалось инициализировать Polymarket клиент с CLOB ключами: %s", exc)
                logger.error("Полная ошибка:", exc_info=True)
                self._client = None
        elif has_private_key:
            # Используем приватный ключ для генерации API ключей
            logger.info("Найден приватный ключ, генерируем CLOB API ключи...")
            try:
                # Создаем временный клиент для генерации API ключей
                temp_client = ClobClient(
                    host=settings.polymarket_api_url,
                    key=settings.polymarket_private_key,
                    funder=settings.polymarket_wallet_address,
                    chain_id=137,
                )

                # Генерируем API ключи
                api_creds = temp_client.create_api_key()
                logger.info("🎉 API ключи сгенерированы из приватного ключа")

                # Создаем основной клиент с API ключами
                self._client = ClobClient(
                    host=settings.polymarket_api_url,
                    key=api_creds.api_key,
                    secret=api_creds.api_secret,
                    passphrase=api_creds.api_passphrase,
                    chain_id=137,
                )
                logger.info("✅ Polymarket клиент инициализирован с новыми API ключами")
            except Exception as exc:  # noqa: BLE001
                logger.error("Не удалось сгенерировать API ключи из приватного ключа: %s", exc)
                self._client = None
        else:
            logger.warning("Не найдены ни CLOB API ключи, ни приватный ключ. Работаем в режиме только для чтения")
            self._client = None
        
        # Кэш для тегов (чтобы не запрашивать каждый раз)
        self._tags_cache: Dict[str, int] | None = None
        
        # Путь к файлу кэша рынков
        self._markets_cache_file = MARKETS_CACHE_FILE
        # Путь к файлу времени последнего обновления
        self._last_update_file = MARKETS_LAST_UPDATE_FILE
        # Интервал обновления (в минутах)
        self._update_interval_minutes = int(
            getattr(app_config, "markets_update_interval_minutes", MARKETS_UPDATE_INTERVAL_MINUTES)
        )
        # Флаг для остановки фонового обновления
        self._stop_update_thread = False
        self._update_thread: threading.Thread | None = None

    def _get_tag_id(self, tag_name: str | None, tag_id: int | None) -> int | None:
        """
        Получить tag_id по названию тега или вернуть переданный tag_id.
        
        Args:
            tag_name: Название тега (например, "Crypto", "Politics")
            tag_id: Прямой tag_id (если задан, используется напрямую)
        
        Returns:
            tag_id или None
        """
        # Если задан прямой tag_id, используем его
        if tag_id is not None:
            return tag_id
        
        # Если название тега не задано, возвращаем None
        if not tag_name or not tag_name.strip():
            return None
        
        # Загружаем кэш тегов, если еще не загружен
        if self._tags_cache is None:
            self._tags_cache = {}
            try:
                tags_url = "https://gamma-api.polymarket.com/tags"
                # Загружаем все теги с пагинацией (без ограничений)
                all_tags = []
                offset = 0
                limit_per_page = 1000  # Лимит на страницу
                max_iterations = 1000  # Защита от бесконечного цикла (достаточно для большого количества тегов)
                iteration = 0
                
                # Если ищем конкретный тег, сначала пробуем использовать параметр search
                if tag_name and tag_name.strip():
                    try:
                        search_params = {"search": tag_name.strip(), "limit": 1000}
                        search_response = requests.get(tags_url, params=search_params, timeout=10)
                        if search_response.status_code == 200:
                            search_data = search_response.json()
                            search_tags = search_data if isinstance(search_data, list) else (
                                search_data.get("data") or search_data.get("results") or search_data.get("tags") or []
                            )
                            if search_tags:
                                logger.debug("Найдено %s тегов через параметр search='%s'", len(search_tags), tag_name)
                                all_tags.extend(search_tags)
                    except Exception as search_exc:
                        logger.debug("Поиск через параметр search не сработал: %s", search_exc)
                
                # Если через search ничего не нашли или не использовали search, загружаем все теги
                if not all_tags:
                    # Всегда используем пагинацию для загрузки всех тегов
                    while iteration < max_iterations:
                        iteration += 1
                        params = {"limit": limit_per_page, "offset": offset}
                        
                        response = requests.get(tags_url, params=params, timeout=10)
                        if response.status_code == 200:
                            tags_data = response.json()
                            tags_list = tags_data if isinstance(tags_data, list) else (
                                tags_data.get("data") or tags_data.get("results") or tags_data.get("tags") or []
                            )
                            
                            if not tags_list:
                                logger.debug("Получен пустой список тегов, прекращаем загрузку")
                                break
                            
                            all_tags.extend(tags_list)
                            logger.debug("Загружено %s тегов (всего: %s, offset: %s)", len(tags_list), len(all_tags), offset)
                            
                            # Если получили меньше чем limit, значит это последняя страница
                            if len(tags_list) < limit_per_page:
                                logger.debug("Получено меньше %s тегов, это последняя страница. Всего загружено: %s", limit_per_page, len(all_tags))
                                break
                            
                            # Увеличиваем offset для следующей страницы
                            offset += len(tags_list)
                        else:
                            logger.warning("Ошибка при загрузке тегов (статус %s): %s", response.status_code, response.text[:200])
                            break
                
                tags_list = all_tags
                if tags_list:
                    
                    # Логируем структуру первого тега для отладки
                    if tags_list and isinstance(tags_list[0], dict):
                        logger.debug("Пример структуры тега: ключи=%s", list(tags_list[0].keys())[:10])
                    
                    crypto_found = False
                    for tag in tags_list:
                        if isinstance(tag, dict):
                            tag_id_val = tag.get("id")
                            # Используем label напрямую (как в примере пользователя)
                            tag_label = tag.get("label", "")
                            tag_slug = tag.get("slug", "")
                            
                            if tag_id_val:
                                # Сохраняем по label (как в примере пользователя)
                                if tag_label:
                                    tag_label_lower = tag_label.lower().strip()
                                    self._tags_cache[tag_label_lower] = tag_id_val
                                    # Отслеживаем, нашли ли мы Crypto
                                    if "crypto" in tag_label_lower:
                                        crypto_found = True
                                        logger.debug("Найден тег с 'crypto' в названии: '%s' -> tag_id=%s", tag_label, tag_id_val)
                                # Сохраняем по slug (если есть)
                                if tag_slug:
                                    tag_slug_lower = tag_slug.lower().strip()
                                    self._tags_cache[tag_slug_lower] = tag_id_val
                                    if "crypto" in tag_slug_lower:
                                        crypto_found = True
                                        logger.debug("Найден тег с 'crypto' в slug: '%s' -> tag_id=%s", tag_slug, tag_id_val)
                    
                    logger.debug("Загружено %s тегов в кэш (уникальных ключей: %s)", len(tags_list), len(self._tags_cache))
                    
                    # Выводим все теги, содержащие искомое имя тега, для отладки
                    tag_query = tag_name.strip().lower()
                    matched_tags = []
                    for tag in tags_list:
                        if isinstance(tag, dict):
                            tag_label = tag.get("label", "").lower()
                            tag_slug = tag.get("slug", "").lower()
                            if tag_query and (tag_query in tag_label or tag_query in tag_slug):
                                matched_tags.append({
                                    "label": tag.get("label", ""),
                                    "slug": tag.get("slug", ""),
                                    "id": tag.get("id")
                                })
                    if matched_tags:
                        logger.info("Найдены теги, содержащие '%s': %s", tag_name, matched_tags)
                    elif not crypto_found:
                        logger.warning("Тег 'Crypto' не найден в загруженных тегах. Проверьте структуру данных API.")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Не удалось загрузить список тегов: %s", exc, exc_info=True)
                self._tags_cache = {}
        
        # Ищем тег по названию (без учета регистра) - только точное совпадение
        tag_name_lower = tag_name.strip().lower()
        found_tag_id = self._tags_cache.get(tag_name_lower)
        
        if found_tag_id:
            logger.debug("Найден тег '%s' (точное совпадение) -> tag_id=%s", tag_name, found_tag_id)
            return found_tag_id
        
        # Тег не найден (точное совпадение отсутствует)
        logger.info(
            "Тег '%s' не найден (точное совпадение), получаем все рынки без фильтрации без тега",
            tag_name,
        )
        return None

    def clear_markets_cache(self) -> None:
        """
        Очистить кэш рынков.
        """
        try:
            if self._markets_cache_file.exists():
                self._markets_cache_file.unlink()
                logger.info("Кэш рынков очищен: %s", self._markets_cache_file)
            else:
                logger.debug("Файл кэша не существует: %s", self._markets_cache_file)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ошибка при очистке кэша: %s", exc)

    def _load_markets_cache(self) -> List[Dict[str, Any]] | None:
        """
        Загрузить все рынки из кэша (без фильтрации).
        
        Returns:
            Список всех рынков из кэша или None, если кэш не найден.
        """
        if not self._markets_cache_file.exists():
            logger.debug("Файл кэша не найден: %s", self._markets_cache_file)
            return None
        
        try:
            with open(self._markets_cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
            
            cached_markets = cache_data.get("markets", [])
            last_update = cache_data.get("last_update", "")
            
            if cached_markets:
                logger.debug(
                    "Найдены рынки в кэше (обновлено: %s, количество: %s)",
                    last_update,
                    len(cached_markets),
                )
                return cached_markets
            else:
                logger.debug("Кэш пуст")
                return None
        except json.JSONDecodeError as exc:
            logger.warning("Ошибка при чтении кэша (неверный JSON): %s", exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ошибка при загрузке кэша: %s", exc)
            return None

    def _save_markets_cache(self, markets: List[Dict[str, Any]]) -> None:
        """
        Сохранить все рынки в кэш (без фильтрации).
        
        Args:
            markets: Список всех рынков для сохранения.
        """
        try:
            cache_data = {
                "last_update": datetime.now().isoformat(),
                "markets": markets,
            }
            
            # Создаем директорию, если не существует
            self._markets_cache_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self._markets_cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            # Сохраняем время последнего обновления
            self._save_last_update_time()
            
            logger.info(
                "Кэш сохранен: %s рынков",
                len(markets),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ошибка при сохранении кэша: %s", exc)

    def _save_last_update_time(self) -> None:
        """Сохранить время последнего обновления рынков."""
        try:
            update_data = {
                "last_update": datetime.now().isoformat(),
                "update_interval_minutes": self._update_interval_minutes,
            }
            
            # Создаем директорию, если не существует
            self._last_update_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self._last_update_file, "w", encoding="utf-8") as f:
                json.dump(update_data, f, indent=2, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ошибка при сохранении времени обновления: %s", exc)

    def _get_last_update_time(self) -> datetime | None:
        """Получить время последнего обновления рынков."""
        try:
            if not self._last_update_file.exists():
                return None
            
            with open(self._last_update_file, "r", encoding="utf-8") as f:
                update_data = json.load(f)
            
            last_update_str = update_data.get("last_update")
            if not last_update_str:
                return None
            
            return datetime.fromisoformat(last_update_str)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ошибка при чтении времени обновления: %s", exc)
            return None

    def _should_update_markets(self) -> bool:
        """
        Проверить, нужно ли обновлять рынки.
        
        Returns:
            True, если прошло больше 15 минут с последнего обновления.
        """
        last_update = self._get_last_update_time()
        if last_update is None:
            logger.debug("Время последнего обновления не найдено, требуется обновление")
            return True
        
        now = datetime.now()
        time_diff = now - last_update
        
        if time_diff > timedelta(minutes=self._update_interval_minutes):
            logger.info(
                "Прошло %s минут с последнего обновления (лимит: %s минут), требуется обновление",
                int(time_diff.total_seconds() / 60),
                self._update_interval_minutes,
            )
            return True
        
        logger.debug(
            "Обновление не требуется: прошло %s минут, лимит %s минут. Используем кэш.",
            int(time_diff.total_seconds() / 60),
            self._update_interval_minutes,
        )
        return False

    def check_and_update_markets(self, force: bool = False) -> bool:
        """
        Проверить и обновить все рынки, если прошло больше 15 минут.
        Загружает все рынки один раз, без фильтрации по search_term.
        
        Args:
            force: Если True, обновить принудительно, игнорируя время.
        
        Returns:
            True, если обновление было выполнено, False иначе.
        """
        if not force and not self._should_update_markets():
            logger.debug("Обновление не требуется (force=False и не прошел интервал)")
            return False
        
        if force:
            logger.info("Принудительное обновление рынков (force=True)...")
        else:
            logger.info("Начинаем автоматическое обновление всех рынков...")
        
        try:
            # Загружаем ВСЕ рынки с API (без фильтрации по search_term)
            # Используем пустую строку как search_term, чтобы получить все рынки
            logger.info("Начинаем загрузку всех рынков с Gamma API...")
            logger.info("Текущие настройки фильтров по времени: started_minutes_ago=%s, starting_within_minutes=%s",
                       app_config.filter_markets_started_minutes_ago,
                       app_config.filter_markets_starting_within_minutes)
            logger.info("Текущее время Polymarket (ET): %s", get_polymarket_time().strftime("%Y-%m-%d %H:%M:%S %Z"))
            all_markets = self._get_markets_from_gamma("")
            logger.info("✓ Загружено %s рынков с Gamma API", len(all_markets) if all_markets else 0)

            # Сохраняем все рынки в кэш (фильтры по времени теперь в генераторе фильтров)
            if all_markets:
                logger.info("Получено %s рынков с API, сохраняем в кэш...", len(all_markets))
                self._save_markets_cache(all_markets)
                logger.info("✓ Сохранено %s рынков в кэше", len(all_markets))
            else:
                logger.warning("⚠ Не удалось загрузить рынки с API (получен пустой список)")
                return False
        except Exception as exc:  # noqa: BLE001
            logger.error("✗ Ошибка при обновлении рынков: %s", exc, exc_info=True)
            return False
        
        logger.info("Автоматическое обновление рынков завершено")
        return True

    def get_last_update_info(self) -> dict[str, str | int | None]:
        last_update = self._get_last_update_time()
        if last_update is None:
            return {
                "last_update": None,
                "minutes_ago": None,
                "update_interval_minutes": self._update_interval_minutes,
            }
        now = datetime.now()
        minutes_ago = int((now - last_update).total_seconds() / 60)
        return {
            "last_update": last_update.isoformat(),
            "minutes_ago": minutes_ago,
            "update_interval_minutes": self._update_interval_minutes,
        }

    def log_last_update_info(self, prefix: str = "Market cache") -> None:
        info = self.get_last_update_info()
        if info["last_update"] is None:
            logger.info("%s: last_update=none", prefix)
            return
        logger.info(
            "%s: last_update=%s minutes_ago=%s interval=%s",
            prefix,
            info["last_update"],
            info["minutes_ago"],
            info["update_interval_minutes"],
        )


    def start_auto_update(self) -> None:
        """Запустить фоновый поток для автоматического обновления рынков каждые 10 минут."""
        if self._update_thread is not None and self._update_thread.is_alive():
            logger.debug("Фоновый поток обновления уже запущен")
            return
        
        self._stop_update_thread = False
        
        def update_loop() -> None:
            logger.info("Запущен фоновый поток для проверки обновления рынков (каждую минуту)")
            while not self._stop_update_thread:
                try:
                    self.check_and_update_markets()
                except Exception as exc:  # noqa: BLE001
                    logger.error("Ошибка в фоновом потоке обновления: %s", exc)
                
                # Ждем 10 минут перед следующей проверкой
                for _ in range(600):  # 600 секунд = 10 минут
                    if self._stop_update_thread:
                        break
                    time.sleep(1)
            
            logger.info("Фоновый поток обновления остановлен")
        
        self._update_thread = threading.Thread(target=update_loop, daemon=True)
        self._update_thread.start()
        logger.info("Фоновый поток обновления запущен")

    def stop_auto_update(self) -> None:
        """Остановить фоновый поток обновления."""
        self._stop_update_thread = True
        if self._update_thread is not None:
            self._update_thread.join(timeout=5)
            logger.info("Фоновый поток обновления остановлен")

    def _extract_start_time_from_title(self, title: str, current_time: datetime) -> datetime | None:
        """
        Извлечь время начала рынка из названия.

        Примеры:
        - "Bitcoin Up or Down - January 13, 10:30AM-10:45AM ET" -> 10:30AM
        - "Ethereum Up or Down - January 13, 10AM ET" -> 10:00AM

        Args:
            title: Название рынка
            current_time: Текущее время в ET для определения года

        Returns:
            datetime объект с временем начала или None, если не удалось извлечь
        """
        logger.debug("🔍 Парсинг времени из названия: '%s'", title)
        if not title or not isinstance(title, str):
            logger.debug("Название рынка пустое или не является строкой: %s", title)
            return None

        # Паттерны для поиска времени
        # Паттерн 1: "January 13, 10:30AM-10:45AM ET" или "January 13, 10:30AM ET"
        # Паттерн 2: "January 13, 10AM ET"
        # Паттерн 3: "February 4, 9:00AM-9:15AM ET"
        month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]

        # Ищем паттерн: месяц день, время (запятая опциональна)
        # Примеры: "January 13, 10:30AM", "January 13 10AM", "February 4, 9:00AM"
        pattern = r"({})\s+(\d{{1,2}})(?:,)?\s+(\d{{1,2}}(?::\d{{2}})?)(AM|PM)".format("|".join(month_names))
        match = re.search(pattern, title, re.IGNORECASE)

        if not match:
            logger.warning("❌ Не удалось распарсить время из названия рынка: '%s' (паттерн не найден)", title)
            logger.warning("Паттерн искал: месяц день, время (запятая опциональна)")
            logger.warning("Примеры ожидаемых форматов: 'January 13, 10:30AM', 'February 4 9:00AM'")
            return None
        
        month_name = match.group(1)
        day = int(match.group(2))
        time_str = match.group(3)  # "10:30" или "10"
        period = match.group(4).upper()  # "AM" или "PM"
        
        # Определяем месяц
        month = month_names.index(month_name.capitalize()) + 1
        
        # Парсим время
        if ":" in time_str:
            hour_str, minute_str = time_str.split(":")
            hour = int(hour_str)
            minute = int(minute_str)
        else:
            hour = int(time_str)
            minute = 0
        
        # Конвертируем в 24-часовой формат
        if period == "PM" and hour != 12:
            hour += 12
        elif period == "AM" and hour == 12:
            hour = 0
        
        # Определяем год (используем текущий год, но проверяем, не прошло ли уже)
        year = current_time.year
        
        # Создаем datetime объект
        try:
            start_time = datetime(year, month, day, hour, minute, tzinfo=current_time.tzinfo)
            
            # Если дата в прошлом (больше чем на месяц назад), возможно это прошлый год
            # Например, если сейчас январь 2026, а рынок на декабрь 2025
            if start_time < current_time - timedelta(days=32):
                start_time = datetime(year - 1, month, day, hour, minute, tzinfo=current_time.tzinfo)
            # Если дата в будущем (больше чем на месяц вперед), возможно это следующий год
            elif start_time > current_time + timedelta(days=32):
                start_time = datetime(year + 1, month, day, hour, minute, tzinfo=current_time.tzinfo)
            
            return start_time
        except ValueError:
            # Некорректная дата (например, 31 февраля)
            return None
    
    def _extract_end_time_from_title(self, title: str, current_time: datetime) -> datetime | None:
        """
        Извлечь время окончания рынка из названия.
        Примеры:
        - "Bitcoin Up or Down - January 13, 10:30AM-10:45AM ET" -> 10:45AM
        - "Ethereum Up or Down - January 13, 10AM ET" -> 11:00AM (по умолчанию +60 минут)
        """
        if not title or not isinstance(title, str):
            return None

        month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        range_pattern = r"({})\s+(\d{{1,2}}),\s+(\d{{1,2}}(?::\d{{2}})?)(AM|PM)\s*-\s*(\d{{1,2}}(?::\d{{2}})?)(AM|PM)".format("|".join(month_names))
        match = re.search(range_pattern, title, re.IGNORECASE)

        start_time = self._extract_start_time_from_title(title, current_time)
        if not start_time:
            return None

        if not match:
            return start_time + timedelta(minutes=60)

        month_name = match.group(1)
        day = int(match.group(2))
        end_time_str = match.group(5)
        end_period = match.group(6).upper()

        month = month_names.index(month_name.capitalize()) + 1

        if ":" in end_time_str:
            hour_str, minute_str = end_time_str.split(":")
            hour = int(hour_str)
            minute = int(minute_str)
        else:
            hour = int(end_time_str)
            minute = 0

        if end_period == "PM" and hour != 12:
            hour += 12
        elif end_period == "AM" and hour == 12:
            hour = 0

        year = current_time.year
        try:
            end_time = datetime(year, month, day, hour, minute, tzinfo=current_time.tzinfo)
            if end_time <= start_time:
                end_time = end_time + timedelta(days=1)
            if end_time < current_time - timedelta(days=32):
                end_time = end_time.replace(year=year - 1)
            elif end_time > current_time + timedelta(days=32):
                end_time = end_time.replace(year=year + 1)
            return end_time
        except ValueError:
            return None

    def get_market_start_time(self, title: str) -> datetime | None:
        """Публичный хелпер: получить время старта рынка из названия."""
        current_time = get_polymarket_time()
        return self._extract_start_time_from_title(title, current_time)

    def get_market_end_time(self, title: str) -> datetime | None:
        """Публичный хелпер: получить время окончания рынка из названия."""
        current_time = get_polymarket_time()
        return self._extract_end_time_from_title(title, current_time)

    def _filter_markets_by_start_time(
        self,
        markets: List[Dict[str, Any]],
        max_minutes_ago: int
    ) -> List[Dict[str, Any]]:
        """
        Отфильтровать рынки по времени начала.
        Удаляет рынки, которые начались больше чем max_minutes_ago минут назад.
        
        Args:
            markets: Список рынков для фильтрации
            max_minutes_ago: Максимальное количество минут назад (0 = не фильтровать)
        
        Returns:
            Отфильтрованный список рынков
        """
        if max_minutes_ago <= 0:
            return markets
        
        current_time = get_polymarket_time()
        cutoff_time = current_time - timedelta(minutes=max_minutes_ago)
        
        filtered = []
        for market in markets:
            if not isinstance(market, dict):
                continue
            
            # Получаем название рынка
            title = (
                market.get("title") 
                or market.get("question") 
                or market.get("name") 
                or market.get("slug", "")
                or ""
            )
            
            if not title:
                # Если нет названия, оставляем рынок (не фильтруем)
                filtered.append(market)
                continue
            
            # Извлекаем время начала
            start_time = self._extract_start_time_from_title(title, current_time)
            
            if start_time is None:
                # Если не удалось извлечь время, оставляем рынок (не фильтруем)
                filtered.append(market)
                continue
            
            # Проверяем, не начался ли рынок слишком давно
            if start_time >= cutoff_time:
                filtered.append(market)
            else:
                logger.debug("Рынок отфильтрован по времени начала: '%s' (начало: %s, лимит: %s минут назад)", 
                           title[:50], start_time.strftime("%Y-%m-%d %H:%M"), max_minutes_ago)
        
        return filtered
    
    def _filter_markets_by_starting_time(
        self,
        markets: List[Dict[str, Any]],
        within_minutes: int
    ) -> List[Dict[str, Any]]:
        """
        Отфильтровать рынки по времени начала (удалять те, что начнутся слишком далеко).
        Удаляет рынки, которые начнутся позже чем через within_minutes минут.
        
        Например, если рынок начинается в 11:00, а within_minutes = 5:
        - В 10:54: до начала 6 минут > 5 -> удаляем (слишком далеко)
        - В 10:56: до начала 4 минуты <= 5 -> оставляем (достаточно близко)
        
        Args:
            markets: Список рынков для фильтрации
            within_minutes: Максимальное количество минут до начала (0 = не фильтровать)
        
        Returns:
            Отфильтрованный список рынков
        """
        if within_minutes <= 0:
            return markets
        
        current_time = get_polymarket_time()
        cutoff_time = current_time + timedelta(minutes=within_minutes)
        
        filtered = []
        for market in markets:
            if not isinstance(market, dict):
                continue
            
            # Получаем название рынка
            title = (
                market.get("title") 
                or market.get("question") 
                or market.get("name") 
                or market.get("slug", "")
                or ""
            )
            
            if not title:
                # Если нет названия, оставляем рынок (не фильтруем)
                filtered.append(market)
                continue
            
            # Извлекаем время начала
            start_time = self._extract_start_time_from_title(title, current_time)
            
            if start_time is None:
                # Если не удалось извлечь время, оставляем рынок (не фильтруем)
                filtered.append(market)
                continue
            
            # Проверяем, не начнется ли рынок слишком далеко
            # Удаляем рынки, которые начнутся позже чем через within_minutes минут
            # То есть start_time > current_time + within_minutes -> удалить
            # Оставляем рынки, которые начнутся не позже чем через within_minutes минут
            minutes_until_start = (start_time - current_time).total_seconds() / 60
            
            if start_time <= cutoff_time:
                # Рынок начнется не позже чем через within_minutes минут -> оставляем
                filtered.append(market)
            else:
                # Рынок начнется позже чем через within_minutes минут -> удаляем (слишком далеко)
                logger.debug("Рынок отфильтрован (начнется слишком далеко): '%s' (начало: %s, через %s минут, лимит: %s минут)", 
                           title[:50], start_time.strftime("%Y-%m-%d %H:%M"), int(minutes_until_start), within_minutes)
        
        return filtered

    def _filter_markets_by_search_term(
        self,
        markets: List[Dict[str, Any]],
        search_term: str
    ) -> List[Dict[str, Any]]:
        """
        Отфильтровать рынки по поисковому запросу (частичное совпадение).

        Args:
            markets: Список всех рынков для фильтрации.
            search_term: Строка для поиска в названии рынка.

        Returns:
            Отфильтрованный список рынков.
        """
        if not search_term or not search_term.strip():
            return markets

        # Нормализуем поисковый запрос
        search_lower = search_term.lower().strip()

        logger.debug("Фильтрация: ищем частичное совпадение '%s' в %s рынках", search_term, len(markets))

        filtered = []
        for m in markets:
            if not isinstance(m, dict):
                continue

            # Проверяем разные возможные поля с названием
            title = (
                m.get("title")
                or m.get("question")
                or m.get("name")
                or m.get("slug", "")
                or ""
            )

            if not isinstance(title, str):
                continue

            title_lower = title.lower()

            # Частичное совпадение (без учета регистра)
            matched = search_lower in title_lower

            if matched:
                filtered.append(m)

        logger.debug("Результат фильтрации: найдено %s из %s рынков по запросу '%s'", len(filtered), len(markets), search_term)
        return filtered

    def _log_filtered_markets_preview(self, markets: List[Dict[str, Any]], limit: int = 10) -> None:
        if not markets:
            logger.info("Рынки после фильтрации: 0")
            return
        logger.info("Рынки после фильтрации: %s (показываю первые %s)", len(markets), min(limit, len(markets)))
        for idx, market in enumerate(markets[:limit], 1):
            title = (
                market.get("title")
                or market.get("question")
                or market.get("name")
                or market.get("slug", "")
                or "N/A"
            )
            market_id = market.get("id", "N/A")
            logger.info("  %s) %s [id=%s]", idx, title, market_id)

    def get_markets(
        self, 
        search_term: str | list[str] | None = None,
        use_gamma_api: bool | None = None,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Получить список рынков и отфильтровать по подстроке в названии.
        
        Логика работы:
        1. Сначала проверяет кэш всех рынков
        2. Если кэш есть и актуален - фильтрует из него по search_term
        3. Если кэша нет или он устарел - загружает все рынки с API, сохраняет в кэш, затем фильтрует
        
        Args:
            search_term: Строка или список строк для поиска в названии рынка. Если None, используется из app_config.
            use_gamma_api: Если True, использует Gamma API (рекомендуется для получения рынков),
                          если False, использует CLOB API. Если None, используется из app_config.
            use_cache: Если True, сначала проверяет кэш перед запросом к API.
        """
        # Если включена автоматическая генерация фильтров, генерируем их
        # market_search_filter игнорируется, если auto_generate_filters = True
        search_filters = []
        if app_config.auto_generate_filters:
            if search_term is None:
                if not getattr(app_config, 'disable_polymarket_verbose_logs', False):
                    logger.info("Автоматическая генерация фильтров на основе текущего времени (ET)...")
                search_filters = generate_filters(app_config.coins)
                if not getattr(app_config, 'disable_polymarket_verbose_logs', False):
                    logger.info("Примеры сгенерированных фильтров: %s", search_filters[:3])
            else:
                # Если search_term передан явно, используем его (но это не рекомендуется при auto_generate_filters = True)
                logger.warning("auto_generate_filters = True, но search_term передан явно. Используется переданный search_term.")
                if isinstance(search_term, str):
                    search_filters = [search_term.strip()] if search_term.strip() else []
                elif isinstance(search_term, list):
                    search_filters = [f.strip() for f in search_term if f and f.strip()]
        elif search_term is None:
            # Используем фильтры из конфига (только если auto_generate_filters = False)
            search_term = app_config.market_search_filter
            # Нормализуем search_term: преобразуем в список, если это строка
            if isinstance(search_term, str):
                search_filters = [search_term.strip()] if search_term.strip() else []
            elif isinstance(search_term, list):
                search_filters = [f.strip() for f in search_term if f and f.strip()]
        else:
            # search_term передан явно и auto_generate_filters = False
            # Нормализуем search_term: преобразуем в список, если это строка
            if isinstance(search_term, str):
                search_filters = [search_term.strip()] if search_term.strip() else []
            elif isinstance(search_term, list):
                search_filters = [f.strip() for f in search_term if f and f.strip()]
        
        if use_gamma_api is None:
            use_gamma_api = app_config.use_gamma_api
        
        if not search_filters:
            logger.warning("Фильтр поиска пустой, возвращаем пустой список")
            return []
        
        # Сначала проверяем кэш всех рынков
        all_cached_markets = None
        if use_cache:
            # Проверяем, нужно ли обновить кэш перед чтением
            if self._should_update_markets():
                logger.info("Кэш устарел, обновляем перед чтением...")
                self.check_and_update_markets(force=False)
                # После обновления загружаем свежий кэш
                all_cached_markets = self._load_markets_cache()
            else:
                all_cached_markets = self._load_markets_cache()

        # Если кэш есть, фильтруем из него
        if all_cached_markets is not None:
            # Логируем время последнего обновления кэша
            if not getattr(app_config, 'disable_polymarket_verbose_logs', False):
                last_update_info = self.get_last_update_info()
                if last_update_info["minutes_ago"] is not None:
                    logger.info("📊 КЭШ: обновлен %s минут назад (%s рынков)",
                               last_update_info["minutes_ago"], len(all_cached_markets))
                else:
                    logger.info("📊 КЭШ: время обновления неизвестно (%s рынков)", len(all_cached_markets))

            if not app_config.lite_logs:
                logger.info(
                    "Используем рынки из кэша (количество: %s), фильтруем по %s фильтрам",
                    len(all_cached_markets),
                    len(search_filters),
                )
            
            # Фильтруем по каждому фильтру и объединяем результаты
            all_filtered_markets = []
            seen_ids = set()
            
            for filter_term in search_filters:
                filtered = self._filter_markets_by_search_term(all_cached_markets, filter_term)
                # Добавляем уникальные рынки (по ID)
                for market in filtered:
                    market_id = str(market.get("id", ""))
                    if market_id and market_id not in seen_ids:
                        seen_ids.add(market_id)
                        all_filtered_markets.append(market)
            
            if not app_config.lite_logs:
                logger.info(
                    "Отфильтровано %s уникальных рынков из кэша",
                    len(all_filtered_markets),
                )

            # Применяем фильтры по времени повторно, так как время могло измениться с момента кэширования
            if app_config.filter_markets_started_minutes_ago > 0:
                logger.info("⏰ Повторный фильтр 'начались давно' (%s минут)...", app_config.filter_markets_started_minutes_ago)
                before_filter = len(all_filtered_markets)
                all_filtered_markets = self._filter_markets_by_start_time(
                    all_filtered_markets,
                    app_config.filter_markets_started_minutes_ago
                )
                filtered_count = before_filter - len(all_filtered_markets)
                logger.info("✅ Повторный фильтр 'начались давно': %s -> %s рынков (отфильтровано: %s)",
                           before_filter, len(all_filtered_markets), filtered_count)

            if app_config.filter_markets_starting_within_minutes > 0:
                logger.info("⏰ Повторный фильтр 'начнутся далеко' (%s минут)...", app_config.filter_markets_starting_within_minutes)
                before_filter = len(all_filtered_markets)
                all_filtered_markets = self._filter_markets_by_starting_time(
                    all_filtered_markets,
                    app_config.filter_markets_starting_within_minutes
                )
                filtered_count = before_filter - len(all_filtered_markets)
                logger.info("✅ Повторный фильтр 'начнутся далеко': %s -> %s рынков (отфильтровано: %s)",
                           before_filter, len(all_filtered_markets), filtered_count)

            if not app_config.lite_logs:
                self._log_filtered_markets_preview(all_filtered_markets)
            return all_filtered_markets
        
        # Если кэша нет, загружаем все рынки с API
        if not app_config.lite_logs:
            logger.info("Кэш не найден или устарел, загружаем все рынки с API...")

        # Загружаем ВСЕ рынки (без фильтрации)
        if use_gamma_api:
            all_markets = self._get_markets_from_gamma("")
        else:
            all_markets = self._get_markets_from_clob("")

        # Применяем фильтры по времени СРАЗУ после загрузки
        if all_markets:
            logger.info("📊 ФИЛЬТРАЦИЯ: Получено %s рынков с API", len(all_markets))

            # Фильтрация по времени начала (рынки, которые начались слишком давно)
            if app_config.filter_markets_started_minutes_ago > 0:
                logger.info("⏰ Фильтр 'начались давно' (%s минут)...", app_config.filter_markets_started_minutes_ago)
                before_filter = len(all_markets)
                all_markets = self._filter_markets_by_start_time(
                    all_markets,
                    app_config.filter_markets_started_minutes_ago
                )
                filtered_count = before_filter - len(all_markets)
                logger.info("✅ Фильтр 'начались давно': %s -> %s рынков (отфильтровано: %s)",
                           before_filter, len(all_markets), filtered_count)
            else:
                logger.info("⏰ Фильтр 'начались давно' отключен (значение = %s)", app_config.filter_markets_started_minutes_ago)

            # Фильтрация по времени начала (рынки, которые начнутся слишком далеко)
            if app_config.filter_markets_starting_within_minutes > 0:
                logger.info("⏰ Фильтр 'начнутся далеко' (%s минут)...", app_config.filter_markets_starting_within_minutes)
                before_filter = len(all_markets)
                all_markets = self._filter_markets_by_starting_time(
                    all_markets,
                    app_config.filter_markets_starting_within_minutes
                )
                filtered_count = before_filter - len(all_markets)
                logger.info("✅ Фильтр 'начнутся далеко': %s -> %s рынков (отфильтовано: %s)",
                           before_filter, len(all_markets), filtered_count)
            else:
                logger.info("⏰ Фильтр 'начнутся далеко' отключен (значение = %s)", app_config.filter_markets_starting_within_minutes)

            logger.info("📊 После фильтров по времени: %s рынков", len(all_markets))

            # Сохраняем отфильтрованные рынки в кэш
            logger.info("Сохраняем %s отфильтрованных рынков в кэш...", len(all_markets))
            if use_cache:
                self._save_markets_cache(all_markets)
        else:
            logger.warning("⚠ Не удалось загрузить рынки с API (получен пустой список)")
            return []
        
        # Теперь фильтруем по запрошенным фильтрам
        all_filtered_markets = []
        seen_ids = set()
        
        for filter_term in search_filters:
            filtered = self._filter_markets_by_search_term(all_markets, filter_term)
            # Добавляем уникальные рынки (по ID)
            for market in filtered:
                market_id = str(market.get("id", ""))
                if market_id and market_id not in seen_ids:
                    seen_ids.add(market_id)
                    all_filtered_markets.append(market)
        
        if not app_config.lite_logs:
            logger.info(
                "Отфильтровано %s уникальных рынков из %s загруженных",
                len(all_filtered_markets),
                len(all_markets),
            )
        
        # Фильтры по времени уже применены при генерации фильтров в filter_generator.py
        
        if not app_config.lite_logs:
            self._log_filtered_markets_preview(all_filtered_markets)
        return all_filtered_markets
    
    def _get_markets_from_gamma(self, search_term: str) -> List[Dict[str, Any]]:
        """
        Получить рынки через Gamma API (рекомендуется для market discovery).
        Gamma API не требует аутентификации для публичных данных.
        
        Использует /markets endpoint с параметром tag_id для фильтрации по категории.
        Gamma API имеет ограничение в 100 рынков на запрос, поэтому используем пагинацию.
        """
        try:
            all_markets: List[Dict[str, Any]] = []
            offset = 0
            limit_per_page = 500  # Gamma API поддерживает до 500 рынков на страницу (пагинация)
            
            # Определяем, сколько рынков нужно получить
            target_limit = app_config.max_markets_limit if app_config.max_markets_limit > 0 else 0
            
            # Вычисляем максимальное количество страниц на основе target_limit и clob_api_max_pages
            if target_limit > 0:
                # Нужно загрузить достаточно страниц для достижения target_limit
                required_pages = (target_limit + limit_per_page - 1) // limit_per_page  # Округление вверх
                max_pages = min(required_pages, app_config.clob_api_max_pages)
            else:
                # Если лимит не задан, используем clob_api_max_pages
                max_pages = app_config.clob_api_max_pages
            
            logger.debug("Лимит рынков: %s, требуется страниц: %s, максимум страниц: %s", target_limit, max_pages, app_config.clob_api_max_pages)
            
            # Всегда пытаемся получить tag_id из конфига
            # Если тег найден (точное совпадение) - используем для фильтрации
            # Если тег не найден - получаем все рынки без фильтрации по тегу
            resolved_tag_id = self._get_tag_id(app_config.gamma_api_tag, app_config.gamma_api_tag_id)

            if resolved_tag_id is not None:
                logger.debug(
                    "Тег найден (точное совпадение), используем фильтрацию по тегу: tag_id=%s",
                    resolved_tag_id,
                )
            else:
                logger.debug("Тег не найден, получаем все рынки без фильтрации по тегу")

            # Используем /markets endpoint
            gamma_url = "https://gamma-api.polymarket.com/markets"

            # Приоритет: сначала пробуем с тегом "crypto", потом без тега
            # Это должно быть быстрее и эффективнее
            attempt_tag_ids = [resolved_tag_id] if resolved_tag_id is not None else [None]
            # Если тег найден, пробуем сначала с тегом, потом без тега
            if resolved_tag_id is not None:
                attempt_tag_ids = [resolved_tag_id, None]

            for attempt_tag_id in attempt_tag_ids:
                filter_sets = [
                    ("with_filters", app_config.gamma_api_active_only, app_config.gamma_api_closed),
                ]
                if attempt_tag_id is not None and (
                    app_config.gamma_api_active_only or app_config.gamma_api_closed
                ):
                    filter_sets.append(("tag_only", False, False))

                for filter_label, use_active, use_closed in filter_sets:
                    all_markets = []
                    offset = 0

                    for page in range(max_pages):
                        # Параметры запроса
                        params: Dict[str, Any] = {
                            "limit": limit_per_page,  # Gamma API поддерживает до 500
                            "offset": offset,
                        }
                        # Добавляем tag_id только если он найден (точное совпадение)
                        if attempt_tag_id is not None:
                            params["tag_id"] = attempt_tag_id
                        # Параметр active (как в примере: active=True)
                        if use_active:
                            params["active"] = True  # Используем boolean
                        # Параметр closed (ИСПРАВЛЕНО: инвертированная логика)
                        # use_closed=False означает "не хотим закрытые", поэтому closed=False
                        if not use_closed:
                            params["closed"] = False  # Только НЕзакрытые рынки

                        logger.debug(
                            "Запрос к Gamma API (страница %s): %s с параметрами %s",
                            page + 1,
                            gamma_url,
                            params,
                        )
                        response = requests.get(gamma_url, params=params, timeout=10)
                        response.raise_for_status()

                        data = response.json()
                        logger.debug("Gamma API ответ (страница %s): тип=%s", page + 1, type(data))

                        # Обработка ответа (как в примере: response.json() возвращает список markets)
                        page_markets = []
                        if isinstance(data, list):
                            page_markets = data
                        elif isinstance(data, dict):
                            # Возможные ключи: "data", "results", "markets"
                            page_markets = data.get("data") or data.get("results") or data.get("markets") or []
                        else:
                            logger.warning("Неожиданный формат ответа Gamma API: %s", type(data))
                            page_markets = []

                        if not isinstance(page_markets, list):
                            logger.warning("Данные не в формате списка: %s", type(page_markets))
                            break

                        if not page_markets:
                            # Нет больше данных (как в примере: if not markets: break)
                            logger.debug("Нет больше данных на странице %s", page + 1)
                            break

                        # Добавляем рынки (как в примере: all_markets.extend(markets))
                        all_markets.extend(page_markets)
                        logger.debug(
                            "Добавлено %s рынков со страницы %s (всего: %s)",
                            len(page_markets),
                            page + 1,
                            len(all_markets),
                        )

                        # Если получили меньше чем limit, значит это последняя страница (как в примере)
                        if len(page_markets) < limit_per_page:
                            logger.debug("Получено меньше %s рынков, это последняя страница", limit_per_page)
                            break

                        # Если достигли целевого лимита, прекращаем
                        if target_limit > 0 and len(all_markets) >= target_limit:
                            logger.debug("Достигнут целевой лимит %s рынков", target_limit)
                            break

                        # Увеличиваем offset для следующей страницы (как в примере: offset += limit)
                        offset += len(page_markets)

                    if all_markets:
                        break
                    if attempt_tag_id is not None and filter_label == "with_filters":
                        logger.warning(
                            "Gamma API вернул 0 рынков с tag_id=%s и фильтрами, пробуем только тег",
                            attempt_tag_id,
                        )
                        continue
                if all_markets:
                    break
                if attempt_tag_id is not None:
                    logger.warning(
                        "Gamma API вернул 0 рынков с tag_id=%s, повторяем без тега",
                        attempt_tag_id,
                    )
                    continue
                break
            
            if not isinstance(all_markets, list):
                logger.warning("Рынки не в формате списка: %s", type(all_markets))
                return []
            
            # Применяем лимит из конфига после загрузки всех страниц
            if app_config.max_markets_limit > 0 and len(all_markets) > app_config.max_markets_limit:
                logger.debug("Применяем лимит: обрезаем с %s до %s рынков", len(all_markets), app_config.max_markets_limit)
                all_markets = all_markets[: app_config.max_markets_limit]
            
            logger.info("Получено %s рынков из Gamma API (после пагинации и применения лимита)", len(all_markets))

            # Если search_term пустой, возвращаем все (уже с примененным лимитом)
            if not search_term or not search_term.strip():
                return all_markets
            
            # Клиентская фильтрация по поисковому запросу
            # Строгая фильтрация: ищем точное совпадение подстроки
            search_lower = search_term.lower().strip()
            
            # Убираем лишние пробелы и нормализуем запрос
            search_normalized = " ".join(search_lower.split())
            
            logger.debug("Строгая фильтрация: ищем точное совпадение '%s' в %s рынках", search_term, len(all_markets))
            
            filtered = []
            sample_titles = []  # Для отладки - первые несколько названий
            for idx, m in enumerate(all_markets):
                if not isinstance(m, dict):
                    continue
                
                # Проверяем разные возможные поля с названием
                title = (
                    m.get("title") 
                    or m.get("question") 
                    or m.get("name") 
                    or m.get("slug", "")
                    or ""
                )
                
                if not isinstance(title, str):
                    continue
                
                # Сохраняем первые несколько названий для отладки
                if idx < 10:
                    sample_titles.append(title)
                
                title_lower = title.lower()
                
                # Полное совпадение: название должно точно совпадать с запросом
                # Убираем лишние пробелы и сравниваем
                title_normalized = " ".join(title_lower.split())
                search_normalized_clean = " ".join(search_normalized.split())
                
                # Точное совпадение (без учета регистра)
                matched = title_normalized == search_normalized_clean
                
                if matched:
                    filtered.append(m)
            
            # Отладочная информация
            if sample_titles:
                logger.debug("Примеры названий рынков (первые 5): %s", sample_titles)
            logger.debug("Результат фильтрации: найдено %s из %s рынков", len(filtered), len(all_markets))
            
            # Если ничего не найдено, выводим примеры для отладки
            if not filtered and len(all_markets) > 0:
                logger.debug("Не найдено совпадений. Примеры названий для отладки:")
                for idx, m in enumerate(all_markets[:10], 1):
                    title = m.get("title") or m.get("question") or m.get("name") or "N/A"
                    logger.debug("  %s. %s", idx, title)
            
            logger.info(
                "Получено %s рынков из API, отфильтровано по '%s': %s",
                len(all_markets),
                search_term,
                len(filtered),
            )
            
            # Применяем лимит к отфильтрованным результатам
            if app_config.max_markets_limit > 0 and len(filtered) > app_config.max_markets_limit:
                filtered = filtered[: app_config.max_markets_limit]
            
            return filtered
            
        except requests.exceptions.RequestException as exc:
            logger.error("Ошибка HTTP при запросе к Gamma API: %s", exc)
            # Fallback на CLOB API
            logger.info("Пробуем получить рынки через CLOB API...")
            return self._get_markets_from_clob(search_term)
        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка при получении рынков из Gamma API: %s", exc, exc_info=True)
            # Fallback на CLOB API
            return self._get_markets_from_clob(search_term)
    
    def _get_markets_from_clob(self, search_term: str) -> List[Dict[str, Any]]:
        """
        Получить рынки через CLOB API (с поддержкой пагинации).
        """
        try:
            all_markets: List[Dict[str, Any]] = []
            cursor = None
            max_pages = app_config.clob_api_max_pages
            
            # CLOB API использует cursor-based pagination
            for page in range(max_pages):
                try:
                    # Вызываем get_markets с cursor, если он есть
                    if cursor:
                        # Некоторые версии клиента поддерживают параметр cursor
                        raw_response = self._client.get_markets(cursor=cursor)  # type: ignore[call-arg]
                    else:
                        raw_response = self._client.get_markets()
                    
                    logger.debug("CLOB API страница %s: тип ответа=%s", page + 1, type(raw_response))
                    
                    # Обработка формата ответа
                    if isinstance(raw_response, dict):
                        # Проверяем наличие данных и cursor для пагинации
                        markets = raw_response.get("data") or raw_response.get("results") or []
                        cursor = raw_response.get("next_cursor") or raw_response.get("cursor")
                        
                        # Если нет стандартных ключей, ищем список в значениях
                        if not markets:
                            for key, value in raw_response.items():
                                if isinstance(value, list) and value:
                                    markets = value
                                    break
                    elif isinstance(raw_response, list):
                        markets = raw_response
                        cursor = None
                    else:
                        logger.warning("Неожиданный формат ответа CLOB API: %s", type(raw_response))
                        markets = []
                    
                    if isinstance(markets, list):
                        all_markets.extend(markets)
                        logger.debug("Добавлено %s рынков со страницы %s (всего: %s)", len(markets), page + 1, len(all_markets))
                    
                    # Если нет cursor или пустой список, прекращаем пагинацию
                    if not cursor or not markets:
                        break
                        
                except TypeError:
                    # Если метод не поддерживает cursor, пробуем без него
                    if page == 0:
                        raw_response = self._client.get_markets()
                        if isinstance(raw_response, list):
                            all_markets = raw_response
                        elif isinstance(raw_response, dict):
                            all_markets = raw_response.get("data") or raw_response.get("results") or []
                        break
                    else:
                        break
            
            logger.info("Получено %s рынков из CLOB API", len(all_markets))
            
            # Применяем лимит из конфига
            if app_config.max_markets_limit > 0 and len(all_markets) > app_config.max_markets_limit:
                all_markets = all_markets[: app_config.max_markets_limit]
                logger.debug("Применен лимит: оставлено %s рынков", len(all_markets))
            
            # Если search_term пустой, возвращаем все
            if not search_term or not search_term.strip():
                return all_markets
            
            # Фильтрация по поисковому запросу
            filtered = []
            for m in all_markets:
                if not isinstance(m, dict):
                    continue
                
                title = m.get("title") or m.get("question") or m.get("name") or ""
                if isinstance(title, str) and search_term.lower() in title.lower():
                    filtered.append(m)
            
            logger.info("Отфильтровано %s рынков по запросу '%s'", len(filtered), search_term)
            return filtered
            
        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка при получении рынков из CLOB API: %s", exc, exc_info=True)
            return []

    def get_orderbook_by_token_id(self, token_id: str) -> Optional[Dict[str, Any]]:
        """Получить orderbook по token_id через CLOB REST API."""
        if not token_id:
            return None
        try:
            clob_url = f"{settings.polymarket_api_url}/book"
            response = requests.get(clob_url, params={"token_id": token_id}, timeout=10)
            if response.status_code != 200:
                logger.debug(
                    "CLOB API вернул статус %s для token_id=%s: %s",
                    response.status_code,
                    token_id,
                    response.text[:200],
                )
                return None
            return response.json()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Ошибка при запросе orderbook token_id=%s: %s", token_id, exc)
            return None

    def get_market_data(self, market_id: str) -> Optional[Dict[str, Any]]:
        """Получить данные рынка через Gamma API."""
        if not market_id:
            return None
        try:
            gamma_url = f"https://gamma-api.polymarket.com/markets/{market_id}"
            response = requests.get(gamma_url, timeout=10)
            if response.status_code != 200:
                logger.debug(
                    "Gamma API вернул статус %s для market_id=%s: %s",
                    response.status_code,
                    market_id,
                    response.text[:200],
                )
                return None
            data = response.json()
            return data if isinstance(data, dict) else None
        except Exception as exc:  # noqa: BLE001
            logger.debug("Ошибка при запросе market_data=%s: %s", market_id, exc)
            return None

    def get_market_token_ids(self, market_id: str) -> tuple[list[str], list[str]]:
        """
        Получить token_id и outcomes для рынка через Gamma API.
        Возвращает (token_ids, outcomes).
        """
        token_ids: list[str] = []
        outcomes: list[str] = []
        try:
            gamma_url = f"https://gamma-api.polymarket.com/markets/{market_id}"
            response = requests.get(gamma_url, timeout=10)
            if response.status_code != 200:
                logger.warning(
                    "Gamma API вернул статус %s для market_id=%s",
                    response.status_code,
                    market_id,
                )
                return token_ids, outcomes

            market_data = response.json()
            if not isinstance(market_data, dict):
                logger.warning("Неожиданный формат данных рынка: %s", type(market_data))
                return token_ids, outcomes

            raw_token_ids = (
                market_data.get("clobTokenIds")
                or market_data.get("clob_token_ids")
                or market_data.get("token_ids")
            )
            if isinstance(raw_token_ids, list):
                token_ids = [str(tid) for tid in raw_token_ids if tid]
            elif isinstance(raw_token_ids, str):
                try:
                    parsed = json.loads(raw_token_ids)
                    if isinstance(parsed, list):
                        token_ids = [str(tid).strip() for tid in parsed if tid]
                    else:
                        token_ids = [raw_token_ids.strip()]
                except Exception:
                    token_ids = [raw_token_ids.strip()]

            raw_outcomes = market_data.get("outcomes")
            if isinstance(raw_outcomes, list):
                outcomes = [str(o) for o in raw_outcomes]

            return token_ids, outcomes
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ошибка при получении token_ids для market_id=%s: %s", market_id, exc)
            return token_ids, outcomes

    def get_orderbook(self, market_id: str) -> Optional[Dict[str, Any]]:
        """
        Получить orderbook для заданного рынка через CLOB API.

        Polymarket возвращает orderbook для одного outcome за раз.
        Для бинарных рынков нужно получить orderbook для каждого outcome отдельно.

        Args:
            market_id: ID рынка на Polymarket

        Returns:
            Dict с orderbook для каждого outcome или None
        """
        try:
            # Сначала получаем информацию о рынке из Gamma API, чтобы найти token_id
            gamma_url = f"https://gamma-api.polymarket.com/markets/{market_id}"
            try:
                response = requests.get(gamma_url, timeout=10)
                if response.status_code == 200:
                    market_data = response.json()
                    logger.debug("Данные рынка из Gamma API: ключи=%s", list(market_data.keys())[:15] if isinstance(market_data, dict) else "N/A")

                    token_ids = []
                    if isinstance(market_data, dict):
                        # ПРИОРИТЕТ 1: Пробуем получить через endpoint /tokens
                        tokens_url = f"https://gamma-api.polymarket.com/markets/{market_id}/tokens"
                        logger.debug("Попытка получить token_id через %s", tokens_url)
                        try:
                            tokens_response = requests.get(tokens_url, timeout=10)
                            logger.debug("Ответ /tokens endpoint: статус=%s", tokens_response.status_code)
                            if tokens_response.status_code == 200:
                                tokens_data = tokens_response.json()
                                if isinstance(tokens_data, list):
                                    for idx, token in enumerate(tokens_data):
                                        if isinstance(token, dict):
                                            token_id = (
                                                token.get("token_id")
                                                or token.get("id")
                                                or token.get("clobTokenId")
                                                or token.get("clob_token_id")
                                                or token.get("tokenId")
                                            )
                                            if token_id:
                                                token_ids.append(str(token_id))
                                                logger.debug("Найден token_id в токене %s: %s", idx, token_id)
                        except Exception as tokens_exc:
                            logger.debug("Ошибка при запросе токенов: %s", tokens_exc)

                        # ПРИОРИТЕТ 2: Пробуем получить clobTokenIds из данных рынка
                        if not token_ids:
                            clob_token_ids = (
                                market_data.get("clobTokenIds")
                                or market_data.get("clob_token_ids")
                                or market_data.get("clobTokenId")
                                or market_data.get("tokenIds")
                                or market_data.get("token_ids")
                            )
                            if clob_token_ids:
                                if isinstance(clob_token_ids, list):
                                    token_ids.extend([str(tid) for tid in clob_token_ids if tid])
                                elif isinstance(clob_token_ids, str):
                                    try:
                                        parsed = json.loads(clob_token_ids)
                                        if isinstance(parsed, list):
                                            token_ids.extend([str(tid).strip() for tid in parsed if tid])
                                    except:
                                        token_ids.append(str(clob_token_ids).strip())

                    # Проверяем статус рынка
                    if isinstance(market_data, dict):
                        active = market_data.get("active")
                        closed = market_data.get("closed")
                        logger.debug("Статус рынка: active=%s, closed=%s", active, closed)

                    # Получаем orderbook для каждого token_id отдельно
                    if token_ids:
                        logger.debug("Пробуем получить orderbook для %s token_id: %s", len(token_ids), token_ids)

                        orderbooks = {}
                        for idx, token_id in enumerate(token_ids):
                            clean_token_id = str(token_id).strip()
                            logger.debug("Запрос orderbook для token_id[%s]=%s", idx, clean_token_id)

                            clob_url = f"{settings.polymarket_api_url}/book"
                            params = {"token_id": clean_token_id}

                            try:
                                orderbook_response = requests.get(clob_url, params=params, timeout=10)
                                if orderbook_response.status_code == 200:
                                    orderbook_data = orderbook_response.json()
                                    orderbooks[f"outcome_{idx}"] = orderbook_data
                                    logger.debug("✓ Orderbook получен для token_id=%s", clean_token_id)
                                elif orderbook_response.status_code == 404:
                                    error_text = orderbook_response.text[:200]
                                    logger.warning("CLOB API вернул 404 для рынка %s, token_id=%s: рынок может быть неактивен", market_id, clean_token_id)
                                else:
                                    logger.debug("CLOB API вернул статус %s для token_id=%s", orderbook_response.status_code, clean_token_id)
                            except Exception as req_exc:
                                logger.debug("Ошибка при запросе orderbook для token_id=%s: %s", clean_token_id, req_exc)

                        if orderbooks:
                            # Возвращаем все полученные orderbooks
                            result = {
                                "token_ids": token_ids,
                                "orderbooks": orderbooks
                            }
                            logger.debug("✓ Получено %s orderbook(s) для рынка %s", len(orderbooks), market_id)
                            return result
                        else:
                            logger.warning("Не удалось получить ни один orderbook для рынка %s, token_ids: %s", market_id, token_ids)
                    else:
                        logger.warning("Не удалось найти token_id для рынка %s", market_id)

            except requests.exceptions.RequestException as req_exc:
                logger.warning("Ошибка HTTP при получении данных рынка: %s", req_exc)

            return None

        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка при получении orderbook для market_id=%s: %s", market_id, exc, exc_info=True)
            return None

    def buy_outcome(
        self,
        market_id: str,
        outcome: int,
        amount_usdc: float,
        max_price: float,
        dry_run: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Создать лимитный ордер на покупку исхода.

        outcome: индекс исхода (обычно 0/1 для бинарных рынков).
        amount_usdc: размер позиции в USDC (size).
        max_price: максимальная цена (лимит).
        dry_run: если True, только валидирует параметры без отправки ордера.
        """
        if self._client is None:
            logger.warning("Polymarket клиент не инициализирован (режим только чтения)")
            return None

        if dry_run:
            logger.info(
                "[DRY RUN] Симуляция buy: market_id=%s, outcome=%s, amount_usdc=%s, max_price=%s",
                market_id,
                outcome,
                amount_usdc,
                max_price,
            )
            return {
                "dry_run": True,
                "side": "buy",
                "market_id": market_id,
                "outcome": outcome,
                "size": amount_usdc,
                "price": max_price,
            }

        try:
            order: Dict[str, Any] = self._client.create_order(  # type: ignore[assignment]
                market_id=market_id,
                outcome=outcome,
                size=amount_usdc,
                price=max_price,
                side="buy",
            )
            return order
        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка при создании ордера на покупку: %s", exc)
            return None

    def sell_outcome(
        self,
        market_id: str,
        outcome: int,
        amount_usdc: float,
        min_price: float,
        dry_run: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Создать лимитный ордер на продажу исхода.

        outcome: индекс исхода (обычно 0/1 для бинарных рынков).
        amount_usdc: размер позиции в USDC (size).
        min_price: минимальная цена (лимит).
        dry_run: если True, только валидирует параметры без отправки ордера.
        """
        if self._client is None:
            logger.warning("Polymarket клиент не инициализирован (режим только чтения)")
            return None

        if dry_run:
            logger.info(
                "[DRY RUN] Симуляция sell: market_id=%s, outcome=%s, amount_usdc=%s, min_price=%s",
                market_id,
                outcome,
                amount_usdc,
                min_price,
            )
            return {
                "dry_run": True,
                "side": "sell",
                "market_id": market_id,
                "outcome": outcome,
                "size": amount_usdc,
                "price": min_price,
            }

        try:
            order: Dict[str, Any] = self._client.create_order(  # type: ignore[assignment]
                market_id=market_id,
                outcome=outcome,
                size=amount_usdc,
                price=min_price,
                side="sell",
            )
            return order
        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка при создании ордера на продажу: %s", exc)
            return None

    def test_connection(self) -> Dict[str, Any]:
        """
        Проверить подключение к Polymarket API.
        Возвращает словарь с результатами проверки.
        """
        result: Dict[str, Any] = {
            "client_initialized": True,
            "api_creds_set": False,
            "markets_accessible": False,
            "markets_count": 0,
            "errors": [],
        }

        try:
            # Проверка, что API credentials установлены
            result["api_creds_set"] = True
            logger.info("API credentials установлены успешно")
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"Ошибка API credentials: {exc}")
            logger.error("Ошибка при проверке API credentials: %s", exc)

        # Проверка доступности рынков (делаем минимальный запрос для проверки, без полной загрузки)
        try:
            # Делаем один небольшой запрос для проверки доступности API (не загружаем все рынки)
            logger.info("Проверка доступности рынков через Gamma API...")
            
            # Получаем tag_id (из названия или напрямую)
            resolved_tag_id = self._get_tag_id(app_config.gamma_api_tag, app_config.gamma_api_tag_id)
            
            # Если задан tag_id, используем /events endpoint
            if resolved_tag_id is not None:
                gamma_url = "https://gamma-api.polymarket.com/events"
                params = {"limit": 1, "active": "true", "closed": "false", "tag_id": resolved_tag_id}
            else:
                gamma_url = "https://gamma-api.polymarket.com/markets"
                params = {"limit": 1, "active": "true", "closed": "false"}
            
            response = requests.get(gamma_url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                markets_count = len(data) if isinstance(data, list) else 0
                if markets_count > 0:
                    result["markets_accessible"] = True
                    result["markets_count"] = markets_count  # Это только для проверки, не полное количество
                    logger.info("Доступ к рынкам успешен через Gamma API (проверка: получено %s рынков)", markets_count)
                else:
                    result["errors"].append("Gamma API вернул пустой ответ")
            else:
                result["errors"].append(f"Gamma API вернул статус {response.status_code}")
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"Ошибка при проверке доступности рынков: {exc}")
            logger.error("Ошибка при проверке доступности рынков: %s", exc, exc_info=True)

        return result

    def get_balance(self) -> Optional[Dict[str, Any]]:
        """
        Получить баланс кошелька (USDC и другие токены) через CLOB API.
        """
        # Пробуем различные возможные методы для получения баланса
        methods_to_try = [
            "get_balance",
            "get_user_balance", 
            "get_account_balance",
            "balance",
        ]
        
        for method_name in methods_to_try:
            if hasattr(self._client, method_name):
                try:
                    method = getattr(self._client, method_name)
                    balance = method()
                    if balance is not None:
                        logger.info("Баланс получен через метод клиента: %s", method_name)
                        return balance
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Метод %s не сработал: %s", method_name, exc)
                    continue
        
        # Если прямых методов нет, пробуем получить через CLOB API с аутентификацией
        try:
            # Пробуем различные методы получения баланса через аутентифицированный клиент
            balance_methods = [
                "get_balance",
                "get_user_balance",
                "get_account_balance",
                "get_balance_allowance",
                "balance",
            ]

            for method_name in balance_methods:
                if hasattr(self._client, method_name):
                    try:
                        method = getattr(self._client, method_name)
                        # Пробуем вызвать метод с разными параметрами
                        balance = None

                        # Для get_balance_allowance пробуем с параметрами
                        if method_name == "get_balance_allowance":
                            try:
                                # Пробуем без параметров
                                balance = method()
                            except TypeError:
                                try:
                                    # Пробуем с параметрами для collateral
                                    balance = method({"asset_type": "COLLATERAL"})
                                except (TypeError, Exception):
                                    try:
                                        # Пробуем с токеном USDC
                                        balance = method({"token_id": "USDC"})
                                    except (TypeError, Exception):
                                        pass
                        else:
                            # Для других методов пробуем без параметров
                            balance = method()

                        if balance is not None:
                            # Обрабатываем ответ
                            if isinstance(balance, dict):
                                # Ищем поле с балансом
                                for key in ["balance", "amount", "value", "usdc", "collateral"]:
                                    if key in balance and isinstance(balance[key], (int, float)):
                                        balance_value = float(balance[key])
                                        logger.info("Баланс получен через CLOB API %s: %s", method_name, balance_value)
                                        return balance_value
                                # Если нашли числовое значение в словаре
                                for value in balance.values():
                                    if isinstance(value, (int, float)):
                                        balance_value = float(value)
                                        logger.info("Баланс получен через CLOB API %s (dict): %s", method_name, balance_value)
                                        return balance_value
                            elif isinstance(balance, (int, float)):
                                balance_value = float(balance)
                                logger.info("Баланс получен через CLOB API %s: %s", method_name, balance_value)
                                return balance_value
                            elif isinstance(balance, str):
                                try:
                                    balance_value = float(balance)
                                    logger.info("Баланс получен через CLOB API %s (str): %s", method_name, balance_value)
                                    return balance_value
                                except ValueError:
                                    pass

                    except Exception as method_exc:  # noqa: BLE001
                        logger.debug("Метод %s не сработал: %s", method_name, method_exc)
                        continue

            # Пробуем получить баланс через прямой API call с аутентификацией
            clob_url = f"{settings.polymarket_api_url}/balance"

            # Получаем API credentials для заголовков
            headers = {}
            if hasattr(self._client, "get_api_creds"):
                try:
                    api_creds = self._client.get_api_creds()
                    if api_creds and isinstance(api_creds, dict):
                        api_key = api_creds.get("apiKey") or api_creds.get("api_key")
                        if api_key:
                            headers["Authorization"] = f"Bearer {api_key}"
                except Exception as creds_exc:  # noqa: BLE001
                    logger.debug("Не удалось получить API credentials: %s", creds_exc)

            if headers.get("Authorization"):
                balance_response = requests.get(clob_url, headers=headers, timeout=10)
                if balance_response.status_code == 200:
                    balance_data = balance_response.json()
                    logger.info("Баланс получен через CLOB API /balance с аутентификацией")

                    # Обрабатываем ответ
                    if isinstance(balance_data, dict):
                        # Ищем поле с балансом (может быть "balance", "usdc", "collateral" и т.д.)
                        for key in ["balance", "usdc", "collateral", "total"]:
                            if key in balance_data:
                                return float(balance_data[key])
                        # Если нашли числовое значение в ответе
                        for value in balance_data.values():
                            if isinstance(value, (int, float)):
                                return float(value)
                    return balance_data
                else:
                    logger.debug(
                        "CLOB API /balance вернул статус %s: %s",
                        balance_response.status_code,
                        balance_response.text[:200],
                    )
        except Exception as clob_exc:  # noqa: BLE001
            logger.debug("Ошибка при получении баланса через CLOB API: %s", clob_exc)

        # Fallback: пробуем получить через Data API (работает без аутентификации)
        try:
            # Data API endpoint для баланса: GET /value
            data_api_url = "https://data-api.polymarket.com/value"

            # Параметры: нужен user_id (адрес кошелька)
            params = {"user": settings.polymarket_wallet_address}
            balance_response = requests.get(data_api_url, params=params, timeout=10)
            if balance_response.status_code == 200:
                balance_data = balance_response.json()
                logger.info("Баланс получен через Data API /value")

                # Обрабатываем ответ: возвращаем значение value
                if isinstance(balance_data, list) and len(balance_data) > 0:
                    user_balance = balance_data[0].get("value", 0)
                    return float(user_balance)
                elif isinstance(balance_data, dict):
                    user_balance = balance_data.get("value", 0)
                    return float(user_balance)
                else:
                    return float(balance_data) if isinstance(balance_data, (int, float)) else 0.0
            else:
                logger.debug(
                    "Data API /value вернул статус %s: %s",
                    balance_response.status_code,
                    balance_response.text[:200],
                )
        except Exception as data_api_exc:  # noqa: BLE001
            logger.debug("Ошибка при получении баланса через Data API: %s", data_api_exc)
            
            # Fallback: пробуем CLOB API endpoint для баланса (если есть)
            clob_url = f"{settings.polymarket_api_url}/balance"
            
            # Пробуем получить API credentials для заголовков
            headers = {}
            try:
                if hasattr(self._client, "get_api_creds"):
                    api_creds = self._client.get_api_creds()
                    if api_creds and isinstance(api_creds, dict):
                        api_key = api_creds.get("apiKey") or api_creds.get("api_key")
                        if api_key:
                            headers["Authorization"] = f"Bearer {api_key}"
                elif hasattr(self._client, "_api_key"):
                    # Альтернативный способ получения API ключа
                    api_key = getattr(self._client, "_api_key", None)
                    if api_key:
                        headers["Authorization"] = f"Bearer {api_key}"
            except Exception as creds_exc:  # noqa: BLE001
                logger.debug("Не удалось получить API credentials для заголовков: %s", creds_exc)
            
            balance_response = requests.get(clob_url, headers=headers, timeout=10)
            if balance_response.status_code == 200:
                balance_data = balance_response.json()
                logger.info("Баланс получен через CLOB API /balance endpoint")
                return balance_data
            elif balance_response.status_code == 401:
                logger.debug("Требуется аутентификация для получения баланса (статус 401)")
            else:
                logger.debug(
                    "CLOB API /balance вернул статус %s: %s",
                    balance_response.status_code,
                    balance_response.text[:200],
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Ошибка при получении баланса через HTTP: %s", exc)
        
        # Если прямых методов нет, пробуем получить через orders или positions
        try:
            # Некоторые клиенты возвращают баланс через get_positions или get_orders
            if hasattr(self._client, "get_positions"):
                positions = self._client.get_positions()
                if positions:
                    logger.info("Информация о позициях получена (может содержать баланс)")
                    return {"positions": positions, "note": "Баланс через позиции"}
        except Exception as exc:  # noqa: BLE001
            logger.debug("Не удалось получить баланс через позиции: %s", exc)
        
        logger.warning("Методы получения баланса недоступны. Возможно требуется аутентификация или другой endpoint.")
        return None

    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """
        Получить информацию об аккаунте (адрес, статус и т.д.).
        Примечание: метод может быть недоступен в некоторых версиях py-clob-client.
        """
        # Пробуем различные возможные методы
        methods_to_try = [
            "get_account",
            "get_user",
            "get_user_info",
            "account",
            "user",
        ]
        
        for method_name in methods_to_try:
            if hasattr(self._client, method_name):
                try:
                    method = getattr(self._client, method_name)
                    account = method()
                    if account is not None:
                        logger.info("Информация об аккаунте получена через метод: %s", method_name)
                        return account
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Метод %s не сработал: %s", method_name, exc)
                    continue
        
        # Если прямых методов нет, возвращаем базовую информацию из настроек
        logger.info("Методы получения информации об аккаунте недоступны, используем данные из конфига")
        return {
            "wallet_address": settings.polymarket_wallet_address,
            "api_url": settings.polymarket_api_url,
            "note": "Информация из конфигурации (методы API недоступны)",
        }

