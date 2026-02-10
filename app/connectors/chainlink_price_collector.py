"""
Polymarket Price Collector Service.

Запускает отдельный сервис для сбора текущих цен BTC, ETH, SOL из Polymarket RTDS.
Сохраняет цены в файл с timestamp для последующего использования в Price to beat.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import websockets

logger = logging.getLogger(__name__)


class ChainlinkPriceCollector:
    """
    Сервис для сбора и хранения исторических цен BTC из Polymarket RTDS.

    Запускает фоновый процесс, который:
    1. Подключается к Polymarket RTDS WebSocket
    2. Получает цены BTC, ETH, SOL в реальном времени
    3. Сохраняет в JSON файл с timestamp
    4. Обновляет файл каждую минуту
    """

    # Символы для сбора
    SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    # Polymarket RTDS настройки
    RTDS_ENDPOINT = "wss://ws-live-data.polymarket.com"
    RTDS_TOPIC = "crypto_prices_chainlink"

    # Файл для хранения цен
    PRICE_DATA_FILE = Path("data/chainlink_btc_prices.json")

    # Lock файл для предотвращения запуска нескольких экземпляров
    COLLECTOR_LOCK_FILE = Path("data/chainlink_collector.lock")

    # Интервалы
    SAVE_INTERVAL = 1 * 60     # Сохранять каждую минуту
    MAX_ENTRIES = 100000       # Максимум 100k записей (~27 часов)

    # Периодический сбор для price_to_beat
    COLLECTION_INTERVAL = 15 * 60  # Каждые 15 минут
    COLLECTION_DURATION = 30        # Собирать 30 секунд
    SAMPLES_TO_AVERAGE = 3          # Усреднять 3 значения

    def __init__(self):
        """
        Инициализация коллектора цен.
        """
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        self.price_buffers: Dict[str, List[Dict]] = {}  # symbol -> buffer
        self.last_prices: Dict[str, float] = {}  # Текущие цены
        self.last_save_time = time.time()

        # Переменные для периодического сбора
        self.collection_active = False
        self.collection_start_time = 0
        self.collection_prices: Dict[str, List[float]] = {}  # symbol -> [prices]
        self.last_collection_time = time.time()

        # Создаем директорию для данных
        self.PRICE_DATA_FILE.parent.mkdir(exist_ok=True)

        # Инициализируем буферы для каждого символа
        for symbol in self.SYMBOLS:
            self.price_buffers[symbol] = []

        # Загружаем существующие данные
        self._load_existing_data()

        logger.info("PolymarketPriceCollector инициализирован")

    def _load_existing_data(self) -> None:
        """Загрузить существующие данные из файла."""
        try:
            if self.PRICE_DATA_FILE.exists():
                with open(self.PRICE_DATA_FILE, 'r') as f:
                    data = json.load(f)
                    prices_data = data.get('prices', {})

                    # Распределяем данные по буферам
                    for symbol in self.SYMBOLS:
                        self.price_buffers[symbol] = prices_data.get(symbol, [])

                    total_entries = sum(len(buffer) for buffer in self.price_buffers.values())
                    logger.info(f"Загружено {total_entries} записей цен для {len(self.price_buffers)} символов")
            else:
                logger.info("Файл с данными не найден, начинаем с пустых буферов")
        except Exception as e:
            logger.error(f"Ошибка загрузки данных: {e}")
            # Инициализируем пустые буферы
            for symbol in self.SYMBOLS:
                self.price_buffers[symbol] = []

    def _is_collector_running(self) -> bool:
        """Проверить, запущен ли уже коллектор."""
        try:
            if self.COLLECTOR_LOCK_FILE.exists():
                # Читаем PID из lock файла
                with open(self.COLLECTOR_LOCK_FILE, 'r') as f:
                    pid_str = f.read().strip()

                try:
                    pid = int(pid_str)
                except ValueError:
                    logger.warning("Некорректный PID в lock файле, удаляем его")
                    self.COLLECTOR_LOCK_FILE.unlink(missing_ok=True)
                    return False

                # Проверяем, жив ли процесс с этим PID
                try:
                    os.kill(pid, 0)  # Не отправляет сигнал, только проверяет существование
                    return True  # Процесс существует
                except OSError:
                    # Процесс не существует, удаляем устаревший lock файл
                    logger.warning(f"Процесс с PID {pid} не найден, удаляем lock файл")
                    self.COLLECTOR_LOCK_FILE.unlink(missing_ok=True)
                    return False

            return False
        except Exception as e:
            logger.warning(f"Ошибка при проверке lock файла: {e}")
            return False

    def _create_lock_file(self) -> bool:
        """Создать lock файл с PID процесса."""
        try:
            self.COLLECTOR_LOCK_FILE.parent.mkdir(exist_ok=True)
            self.COLLECTOR_LOCK_FILE.write_text(str(os.getpid()))
            logger.info(f"Создан lock файл: {self.COLLECTOR_LOCK_FILE} (PID: {os.getpid()})")
            return True
        except Exception as e:
            logger.error(f"Ошибка создания lock файла: {e}")
            return False

    def _remove_lock_file(self) -> None:
        """Удалить lock файл."""
        try:
            if self.COLLECTOR_LOCK_FILE.exists():
                self.COLLECTOR_LOCK_FILE.unlink()
                logger.info(f"Удален lock файл: {self.COLLECTOR_LOCK_FILE}")
        except Exception as e:
            logger.warning(f"Ошибка удаления lock файла: {e}")

    def _save_data(self) -> None:
        """Сохранить данные в файл."""
        try:
            # Ограничиваем количество записей для каждого символа
            for symbol in self.price_buffers:
                if len(self.price_buffers[symbol]) > self.MAX_ENTRIES:
                    # Оставляем последние MAX_ENTRIES записей
                    self.price_buffers[symbol] = self.price_buffers[symbol][-self.MAX_ENTRIES:]

            data = {
                'last_updated': datetime.now().isoformat(),
                'symbols': list(self.price_buffers.keys()),
                'prices': self.price_buffers
            }

            with open(self.PRICE_DATA_FILE, 'w') as f:
                json.dump(data, f, indent=2)

            total_entries = sum(len(buffer) for buffer in self.price_buffers.values())
            symbols_info = ", ".join([f"{symbol}: {len(self.price_buffers[symbol])}" for symbol in self.price_buffers])
            logger.info(f"💾 Сохранено {total_entries} записей ({symbols_info}) в {self.PRICE_DATA_FILE}")
            self.last_save_time = time.time()

        except Exception as e:
            logger.error(f"Ошибка сохранения данных: {e}")

    def _start_collection(self) -> None:
        """Начать периодический сбор данных для price_to_beat."""
        if self.collection_active:
            return

        self.collection_active = True
        self.collection_start_time = time.time()
        self.collection_prices = {symbol: [] for symbol in self.SYMBOLS}

        logger.info(f"🎯 Начало сбора данных для price_to_beat (на {self.COLLECTION_DURATION} сек)")

    def _finish_collection(self) -> None:
        """Завершить сбор данных и сохранить усредненные цены."""
        if not self.collection_active:
            return

        collection_time = time.time() - self.collection_start_time
        self.collection_active = False

        # Для каждого символа усредняем последние 3 значения
        for symbol in self.SYMBOLS:
            prices = self.collection_prices.get(symbol, [])
            if len(prices) >= self.SAMPLES_TO_AVERAGE:
                # Берем последние 3 значения
                recent_prices = prices[-self.SAMPLES_TO_AVERAGE:]
                avg_price = sum(recent_prices) / len(recent_prices)

                # Создаем запись с текущим timestamp (время окончания сбора)
                timestamp = int(time.time())
                entry = {
                    'timestamp': timestamp,
                    'price': round(avg_price, 2),
                    'datetime': datetime.fromtimestamp(timestamp).isoformat(),
                    'samples': len(recent_prices),
                    'collection_duration': round(collection_time, 1)
                }

                # Добавляем в основной буфер
                self.price_buffers[symbol].append(entry)

                logger.info(f"📊 {symbol}: усреднено {len(recent_prices)} значений → ${avg_price:.2f} (время сбора: {collection_time:.1f} сек)")
                logger.info(f"💾 Сохранено в буфер: {symbol} timestamp={timestamp} price=${avg_price:.2f}")
            else:
                logger.warning(f"⚠️ {symbol}: недостаточно данных для усреднения ({len(prices)} < {self.SAMPLES_TO_AVERAGE})")
                if prices:
                    logger.info(f"📋 Доступные цены для {symbol}: {prices}")

        # Сохраняем данные
        self._save_data()
        self.last_collection_time = time.time()

        logger.info(f"✅ Сбор данных завершен (длительность: {collection_time:.1f} сек)")

    def _should_start_collection(self) -> bool:
        """
        Проверить, пора ли начать новый сбор данных.
        Начинаем сбор за 45 секунд до открытия рынков (каждые 15 мин).

        Returns:
            True если нужно начать сбор
        """
        current_time = time.time()
        dt = datetime.fromtimestamp(current_time)

        # Не начинать новый сбор, если уже идет
        if self.collection_active:
            return False

        # Не начинать слишком часто (минимум 10 мин между сборами)
        if current_time - self.last_collection_time < 600:  # 10 минут
            return False

        # Получаем секунды в текущей минуте (0-59)
        current_second = dt.second

        # Целевые минуты: 14:14:45, 29:14:45, 44:14:45, 59:14:45 (за 45 сек до открытия)
        target_times = [
            (14, 45),  # 14:45 (за 45 сек до :15)
            (29, 45),  # 29:45 (за 45 сек до :30)
            (44, 45),  # 44:45 (за 45 сек до :45)
            (59, 45),  # 59:45 (за 45 сек до :00 следующего часа)
        ]

        current_minute = dt.minute

        for target_minute, target_second in target_times:
            if current_minute == target_minute and abs(current_second - target_second) <= 5:  # ±5 сек
                # Дополнительная проверка - не собирали ли мы уже в этом интервале
                hours_since_last = (current_time - self.last_collection_time) / 3600
                if hours_since_last >= 0.2:  # Минимум 12 минут (0.2 часа) с последнего сбора
                    return True

        return False

    def _normalize_symbol(self, raw_symbol: str) -> str:
        """Нормализовать символ из RTDS."""
        sym = raw_symbol.strip()
        if not sym:
            return ""
        if "/" in sym:
            base = sym.split("/", 1)[0].upper()
            return f"{base}USDT"
        return sym.upper()

    async def _handle_price_update(self, msg: dict) -> None:
        """
        Обработать обновление цены от RTDS.

        {
          "topic": "crypto_prices_chainlink",
          "type": "update",
          "timestamp": 123,
          "payload": {
            "symbol": "btc/usd",
            "timestamp": 123,
            "value": 42500.5
          }
        }
        """
        payload = msg.get("payload", {}) or {}
        symbol_raw = payload.get("symbol", "")
        symbol = self._normalize_symbol(symbol_raw)
        price = payload.get("value")
        ts_ms = payload.get("timestamp", 0)

        if not symbol or price is None or symbol not in self.SYMBOLS:
            return

        ts = datetime.fromtimestamp(ts_ms / 1000)
        timestamp = int(ts.timestamp())

        # Сохраняем текущую цену
        self.last_prices[symbol] = float(price)

        # Если активен периодический сбор, добавляем цену в коллекцию
        if self.collection_active:
            if symbol not in self.collection_prices:
                self.collection_prices[symbol] = []
            self.collection_prices[symbol].append(float(price))

            # Проверяем, не пора ли завершить сбор
            collection_elapsed = time.time() - self.collection_start_time
            if collection_elapsed >= self.COLLECTION_DURATION:
                self._finish_collection()

        # Добавляем в основной буфер (для текущих цен и поиска)
        entry = {
            'timestamp': timestamp,
            'price': float(price),
            'datetime': ts.isoformat()
        }

        self.price_buffers[symbol].append(entry)
        logger.debug(f"✅ Цена {symbol} обновлена: ${price:.2f}")

        # Периодически сохраняем данные
        if time.time() - self.last_save_time >= self.SAVE_INTERVAL:
            self._save_data()

        # Проверяем, не пора ли начать новый сбор (синхронизация по часам)
        if self._should_start_collection():
            self._start_collection()

    async def _receive_messages(self) -> None:
        """Получать сообщения от RTDS."""
        while self.running and self.websocket:
            try:
                raw = await self.websocket.recv()
                if not raw:
                    continue

                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")
                if msg_type == "update":
                    await self._handle_price_update(msg)

            except Exception as exc:
                logger.error("Ошибка в receive_messages Polymarket: %s", exc)
                self.running = False
                break

    async def _ping_loop(self) -> None:
        """Отправлять ping каждые 5 секунд."""
        while self.running and self.websocket:
            try:
                await asyncio.sleep(5)
                if self.websocket and self.running:
                    await self.websocket.send(json.dumps({"type": "ping"}))
            except Exception as exc:
                logger.error("Ошибка в ping loop: %s", exc)
                self.running = False
                break

    async def start_collection(self, force_start: bool = False) -> None:
        """Запустить периодический сбор цен (30 сек каждые 15 мин).

        Args:
            force_start: Если True, начать сбор немедленно для тестирования
        """
        # Проверяем, не запущен ли уже коллектор
        if self._is_collector_running():
            logger.info("🚫 Коллектор уже запущен в другом процессе, пропускаем запуск")
            return

        # Создаем lock файл
        if not self._create_lock_file():
            logger.error("❌ Не удалось создать lock файл, коллектор не запущен")
            return

        self.running = True
        symbols_str = ", ".join(self.SYMBOLS)

        if force_start:
            logger.info(f"🧪 Запуск ТЕСТОВОГО сбора цен {symbols_str} из Polymarket RTDS (немедленный старт)...")
        else:
            logger.info(f"🚀 Запуск ПЕРИОДИЧЕСКОГО сбора цен {symbols_str} из Polymarket RTDS...")

        while self.running:
            try:
                # Ждем подходящего времени для сбора (каждые 15 мин от начала часа)
                # Если force_start=True, пропускаем ожидание
                if not force_start:
                    while self.running and not self._should_start_collection():
                        await asyncio.sleep(10)  # Проверяем каждые 10 сек

                if not self.running:
                    break

                # Начинаем сбор данных
                self._start_collection()

                # Подключаемся к RTDS только на время сбора
                logger.info("🔌 Подключение к Polymarket RTDS для сбора данных...")

                try:
                    # Подключаемся к RTDS
                    self.websocket = await websockets.connect(
                        self.RTDS_ENDPOINT,
                        ping_interval=None,
                        close_timeout=5,  # Уменьшаем timeout
                    )

                    # Подписываемся на цены
                    msg = {
                        "action": "subscribe",
                        "subscriptions": [
                            {
                                "topic": self.RTDS_TOPIC,
                                "type": "update",
                            }
                        ],
                    }
                    await self.websocket.send(json.dumps(msg))
                    logger.info("✅ Подписались на Polymarket RTDS цены")

                    # Собираем данные в течение COLLECTION_DURATION секунд
                    collection_end_time = time.time() + self.COLLECTION_DURATION

                    while self.running and time.time() < collection_end_time:
                        try:
                            # Получаем сообщение с timeout
                            raw = await asyncio.wait_for(
                                self.websocket.recv(),
                                timeout=1.0  # 1 сек timeout
                            )

                            if raw:
                                try:
                                    msg = json.loads(raw)
                                    msg_type = msg.get("type", "")
                                    if msg_type == "update":
                                        await self._handle_price_update(msg)
                                except json.JSONDecodeError:
                                    pass

                        except asyncio.TimeoutError:
                            # Нормально - просто проверяем время
                            pass
                        except websockets.exceptions.ConnectionClosed:
                            logger.warning("Соединение закрыто во время сбора")
                            break

                    # Завершаем сбор
                    self._finish_collection()

                except Exception as conn_exc:
                    logger.error("Ошибка подключения к RTDS: %s", conn_exc)
                    # Все равно завершаем сбор даже при ошибке
                    self._finish_collection()

                finally:
                    # Закрываем соединение
                    if self.websocket:
                        try:
                            await self.websocket.close()
                        except:
                            pass
                        self.websocket = None

                # Ждем перед следующей проверкой (минимум 1 мин)
                logger.info("⏰ Ожидание следующего цикла сбора (1 мин)...")
                await asyncio.sleep(60)

            except Exception as exc:
                logger.error("Ошибка в периодическом коллекторе: %s", exc)
                await asyncio.sleep(30)  # Ждем 30 сек при ошибке

        logger.info("🛑 Периодический сбор цен остановлен")
        # Финальное сохранение
        self._save_data()

    def stop_collection(self) -> None:
        """Остановить сбор цен."""
        self.running = False
        symbols_str = ", ".join(self.SYMBOLS)
        logger.info(f"🛑 Остановка сбора цен {symbols_str}")

        # Удаляем lock файл
        self._remove_lock_file()

    def get_price_at_time(self, symbol: str, timestamp: int) -> Optional[float]:
        """
        Получить цену актива на указанное время.
        Сначала ищет в памяти (price_buffers), потом в файле.

        Args:
            symbol: Символ (BTCUSDT, ETHUSDT, SOLUSDT)
            timestamp: Unix timestamp

        Returns:
            Цена или None
        """
        target_ts = timestamp

        # 1. Сначала ищем в памяти (price_buffers) - самые свежие данные
        if symbol in self.price_buffers and self.price_buffers[symbol]:
            closest_price = None
            min_diff = float('inf')

            for entry in self.price_buffers[symbol]:
                diff = abs(entry['timestamp'] - target_ts)
                if diff < min_diff:
                    min_diff = diff
                    closest_price = entry['price']

            # Возвращаем если нашли в памяти и разница не больше 5 минут
            if closest_price is not None and min_diff <= 300:
                logger.debug(f"✅ Найдена цена {symbol} ${closest_price:.2f} в ПАМЯТИ для timestamp {timestamp} (разница: {min_diff} сек)")
                return closest_price

        # 2. Если не нашли в памяти, ищем в файле
        try:
            if self.PRICE_DATA_FILE.exists():
                with open(self.PRICE_DATA_FILE, 'r') as f:
                    data = json.load(f)
                    prices_data = data.get('prices', {})

                    if symbol in prices_data and prices_data[symbol]:
                        closest_price = None
                        min_diff = float('inf')

                        for entry in prices_data[symbol]:
                            entry_ts = entry.get('timestamp', 0)
                            diff = abs(entry_ts - target_ts)
                            if diff < min_diff:
                                min_diff = diff
                                closest_price = entry.get('price')

                        # Возвращаем если нашли в файле и разница не больше 5 минут
                        if closest_price is not None and min_diff <= 300:
                            logger.debug(f"📁 Найдена цена {symbol} ${closest_price:.2f} в ФАЙЛЕ для timestamp {timestamp} (разница: {min_diff} сек)")
                            return closest_price

        except Exception as e:
            logger.warning(f"Ошибка чтения файла для {symbol}: {e}")

        logger.debug(f"❌ Не найдена подходящая цена {symbol} для timestamp {timestamp}")
        return None

    def get_price(self, symbol: str) -> Optional[float]:
        """
        Получить последнюю известную цену для символа.

        Сначала проверяет в памяти (last_prices),
        если пусто - читает из файла (для случая когда коллектор запущен в отдельном процессе).

        Args:
            symbol: Символ (BTCUSDT, ETHUSDT, SOLUSDT)

        Returns:
            Последняя цена или None если нет данных
        """
        # Сначала пробуем из памяти (если WebSocket запущен в этом процессе)
        price = self.last_prices.get(symbol)
        if price:
            return price

        # Fallback: читаем из файла (если коллектор запущен в отдельном процессе)
        try:
            if self.PRICE_DATA_FILE.exists():
                with open(self.PRICE_DATA_FILE, 'r') as f:
                    data = json.load(f)
                    prices_data = data.get('prices', {})
                    symbol_prices = prices_data.get(symbol, [])

                    if symbol_prices:
                        # Возвращаем последнюю цену
                        return symbol_prices[-1].get('price')
        except Exception as e:
            logger.debug(f"Ошибка чтения цены {symbol} из файла: {e}")

        return None

    def get_stats(self) -> Dict:
        """
        Получить статистику по собранным данным для всех символов.

        Returns:
            {
                'total_entries': int,
                'symbols': {
                    'BTCUSDT': {'entries': int, 'last_price': float},
                    'ETHUSDT': {'entries': int, 'last_price': float},
                    ...
                }
            }
        """
        total_entries = sum(len(buffer) for buffer in self.price_buffers.values())

        symbols_stats = {}
        for symbol, buffer in self.price_buffers.items():
            last_price = self.last_prices.get(symbol)
            symbols_stats[symbol] = {
                'entries': len(buffer),
                'last_price': last_price
            }

        return {
            'total_entries': total_entries,
            'symbols': symbols_stats
        }


async def main(force_start: bool = False):
    """Основная функция для запуска коллектора.

    Args:
        force_start: Если True, начать сбор немедленно для тестирования
    """
    collector = ChainlinkPriceCollector()

    try:
        await collector.start_collection(force_start=force_start)
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания")
    finally:
        collector.stop_collection()


if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    # Запуск
    asyncio.run(main())
