import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Optional

import websockets

logger = logging.getLogger(__name__)


class PolymarketConnector:
    """
    WebSocket-коннектор для получения цен BTC, ETH, SOL с Polymarket RTDS.

    - Endpoint: wss://ws-live-data.polymarket.com
    - Без аутентификации
    - Topic: crypto_prices_chainlink (Chainlink source)
    - Символы: btc/usd, eth/usd, sol/usd
    """

    RTDS_ENDPOINT = "wss://ws-live-data.polymarket.com"
    RTDS_TOPIC = "crypto_prices_chainlink"
    SYMBOLS = ["btc/usd", "eth/usd", "sol/usd"]
    PING_INTERVAL = 5  # сек
    PRICE_STALENESS_THRESHOLD = 30  # Если цена не обновлялась 30 сек - считается застывшей
    WATCHDOG_INTERVAL = 15  # Проверка живости каждые 15 сек

    def __init__(self) -> None:
        self.is_connected = False
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.last_prices: dict[str, float] = {}
        self.last_timestamps: dict[str, datetime] = {}
        self._last_log_ts: dict[str, float] = {}
        self._last_any_log_ts: float = 0.0
        self._last_update_ts: float = 0.0
        self._raw_logged: bool = False
        self._filters_disabled: bool = False
        self._logged_first_price: bool = False
        self._reconnect_in_progress: bool = False
        self._stale_price_warnings: dict[str, float] = {}  # Когда последний раз предупреждали о застывшей цене
        logger.info("PolymarketConnector инициализирован")

    async def connect(self) -> None:
        """
        Подключиться к Polymarket RTDS WebSocket и подписаться на цены.
        """
        try:
            logger.info("Подключение к Polymarket RTDS: %s", self.RTDS_ENDPOINT)

            self.websocket = await websockets.connect(
                self.RTDS_ENDPOINT,
                ping_interval=None,
                close_timeout=10,
            )

            self.is_connected = True
            logger.info("✅ Подключено к Polymarket RTDS")

            await self._subscribe()

            asyncio.create_task(self._receive_messages())
            asyncio.create_task(self._ping_loop())
            asyncio.create_task(self._watchdog_loop())

        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка подключения к Polymarket: %s", exc)
            self.is_connected = False
            raise

    async def _subscribe(self) -> None:
        """
        Подписаться на цены BTC, ETH, SOL.
        """
        if not self.websocket:
            logger.warning("Cannot subscribe: websocket is None")
            return

        use_filters = False if self.RTDS_TOPIC == "crypto_prices_chainlink" else not self._filters_disabled
        msg = {
            "action": "subscribe",
            "subscriptions": [
                {
                    "topic": self.RTDS_TOPIC,
                    "type": "*" if self.RTDS_TOPIC == "crypto_prices_chainlink" else "update",
                    **(
                        {"filters": json.dumps({"symbol": self.SYMBOLS[0]})}
                        if use_filters and self.SYMBOLS
                        else {}
                    ),
                }
            ],
        }

        logger.info("Sending subscription request: %s", msg)
        await self.websocket.send(json.dumps(msg))
        logger.info("Subscription request sent successfully")

        if use_filters:
            logger.info("Подписались на Polymarket цены (filters): %s", ",".join(self.SYMBOLS))
        else:
            logger.info("Подписались на Polymarket цены (без filters)")

    async def _ping_loop(self) -> None:
        """
        Отправлять ping каждые 5 секунд.
        """
        while self.is_connected and self.websocket:
            try:
                await asyncio.sleep(self.PING_INTERVAL)
                if self.websocket and self.is_connected:
                    await self.websocket.send(json.dumps({"type": "ping"}))
            except Exception as exc:  # noqa: BLE001
                logger.error("Ошибка в ping loop Polymarket: %s", exc)
                self.is_connected = False
                break

    async def _watchdog_loop(self) -> None:
        """
        Watchdog: проверяет свежесть цен и переподключается если нужно.
        ВАЖНО: Работает ВСЕГДА, независимо от is_connected!
        """
        logger.info("🐕 Watchdog запущен (интервал: %ds, порог застывания: %ds)",
                   self.WATCHDOG_INTERVAL, self.PRICE_STALENESS_THRESHOLD)

        while True:  # Работаем ВСЕГДА, не зависимо от is_connected
            try:
                await asyncio.sleep(self.WATCHDOG_INTERVAL)

                # Если отключены, пытаемся переподключиться
                if not self.is_connected and not self._reconnect_in_progress:
                    logger.warning("🐕 Watchdog: RTDS отключен, инициируем переподключение...")
                    await self._reconnect()
                    continue

                # Проверяем свежесть всех цен
                now = time.time()
                stale_symbols = []

                for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
                    sym = self._normalize_symbol(symbol)
                    last_ts = self.last_timestamps.get(sym)

                    if last_ts:
                        age_seconds = (datetime.now() - last_ts).total_seconds()
                        if age_seconds > self.PRICE_STALENESS_THRESHOLD:
                            stale_symbols.append((symbol, age_seconds))

                # Если есть застывшие цены, переподключаемся
                if stale_symbols and not self._reconnect_in_progress:
                    logger.warning(
                        "🐕 Watchdog: Обнаружены застывшие цены: %s. Переподключение к RTDS...",
                        ", ".join([f"{s} ({a:.0f}s)" for s, a in stale_symbols])
                    )
                    await self._reconnect()

            except Exception as exc:  # noqa: BLE001
                logger.error("❌ Ошибка в watchdog loop Polymarket: %s", exc, exc_info=True)
                # НЕ выходим из цикла - продолжаем работать
                await asyncio.sleep(self.WATCHDOG_INTERVAL)

    async def _reconnect(self) -> None:
        """
        Переподключиться к RTDS.
        """
        if self._reconnect_in_progress:
            logger.info("Переподключение уже выполняется, пропускаем")
            return

        try:
            self._reconnect_in_progress = True
            logger.info("🔄 Начало переподключения к RTDS...")

            # Закрываем старое соединение
            old_ws = self.websocket
            self.is_connected = False

            if old_ws:
                try:
                    await old_ws.close()
                except Exception as e:
                    logger.debug(f"Ошибка при закрытии старого WebSocket: {e}")

            await asyncio.sleep(2)  # Короткая пауза

            # Создаем новое соединение
            logger.info("Подключение к Polymarket RTDS: %s", self.RTDS_ENDPOINT)

            self.websocket = await websockets.connect(
                self.RTDS_ENDPOINT,
                ping_interval=None,
                close_timeout=10,
            )

            self.is_connected = True
            logger.info("✅ Переподключено к Polymarket RTDS")

            # Сбрасываем флаги для логирования
            self._raw_logged = False

            # Подписываемся
            await self._subscribe()

            # Перезапускаем только _receive_messages и _ping_loop
            # НЕ создаем новый watchdog - он уже работает!
            asyncio.create_task(self._receive_messages())
            asyncio.create_task(self._ping_loop())

            logger.info("✅ Таски _receive_messages и _ping_loop перезапущены")

        except Exception as exc:
            logger.error("❌ Ошибка переподключения к RTDS: %s", exc, exc_info=True)
            self.is_connected = False
            # Попробуем переподключиться снова через 30 секунд
            await asyncio.sleep(30)
            self._reconnect_in_progress = False
            logger.info("Повторная попытка переподключения...")
            await self._reconnect()
        finally:
            self._reconnect_in_progress = False

    async def _receive_messages(self) -> None:
        """
        Слушать сообщения Polymarket RTDS и обновлять цены.
        """
        logger.info("🔄 _receive_messages started, is_connected=%s", self.is_connected)
        message_count = 0
        timeout_count = 0
        MAX_TIMEOUTS = 3  # После 3 таймаутов подряд считаем соединение мертвым

        while self.is_connected and self.websocket:
            try:
                # Добавляем timeout 60 секунд - если за это время не пришло ни одного сообщения, что-то не так
                raw = await asyncio.wait_for(self.websocket.recv(), timeout=60.0)
                message_count += 1
                timeout_count = 0  # Сбрасываем счетчик таймаутов при успешном получении

                # Логируем только первые 3 сообщения и каждое 500-е для подтверждения работы
                if message_count <= 3 or message_count % 500 == 0:
                    logger.info(f"📥 RTDS: получено сообщение #{message_count}")

                if not raw:
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    # Некоторые сообщения могут быть не-JSON (ping/pong/keepalive)
                    if raw not in {"ping", "pong"}:
                        now = time.monotonic()
                        if self._last_any_log_ts == 0.0 or (now - self._last_any_log_ts) >= 10:
                            self._last_any_log_ts = now
                            logger.info("Polymarket RTDS non-JSON msg: %s", raw)
                    continue
                msg_type = msg.get("type", "")
                if msg.get("statusCode") == 400:
                    body = msg.get("body", {}) or {}
                    message = body.get("message", "")
                    if "Subscription.Filters" in message and not self._filters_disabled:
                        self._filters_disabled = True
                        logger.warning(
                            "RTDS filters rejected, retrying without filters: %s",
                            message,
                        )
                        await self._subscribe()
                        continue
                if not self._raw_logged:
                    self._raw_logged = True
                    logger.info("Polymarket RTDS raw message: %s", msg)

                if msg_type == "update":
                    await self._handle_price_update(msg)
                    self._last_update_ts = time.monotonic()
                else:
                    now = time.monotonic()
                    if self._last_any_log_ts == 0.0 or (now - self._last_any_log_ts) >= 10:
                        self._last_any_log_ts = now
                        logger.info(
                            "Polymarket RTDS msg type=%s topic=%s",
                            msg_type or "unknown",
                            msg.get("topic", ""),
                        )

            except asyncio.TimeoutError:
                timeout_count += 1
                logger.warning(
                    "⏱️  RTDS: timeout при получении сообщения (%d/%d). Получено %d сообщений всего.",
                    timeout_count, MAX_TIMEOUTS, message_count
                )
                if timeout_count >= MAX_TIMEOUTS:
                    logger.error(
                        "❌ RTDS: %d таймаутов подряд! Соединение мертво, переподключаемся...",
                        MAX_TIMEOUTS
                    )
                    self.is_connected = False
                    break
                # Продолжаем попытки если еще не достигли лимита
                continue

            except Exception as exc:  # noqa: BLE001
                logger.error("Ошибка в receive_messages Polymarket: %s", exc, exc_info=True)
                self.is_connected = False
                break

        logger.warning("❌ Отключено от Polymarket RTDS (received %d messages total)", message_count)

    def _normalize_symbol(self, raw_symbol: str) -> str:
        sym = raw_symbol.strip()
        if not sym:
            return ""
        if "/" in sym:
            base = sym.split("/", 1)[0].upper()
            return f"{base}USDT"
        return sym.upper()

    async def _handle_price_update(self, msg: dict) -> None:
        """
        Обновление цены:

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

        if not symbol or price is None:
            return

        ts = datetime.fromtimestamp(ts_ms / 1000)
        self.last_prices[symbol] = float(price)
        self.last_timestamps[symbol] = ts

        if not self._logged_first_price:
            self._logged_first_price = True
            logger.info(
                "✅ Polymarket RTDS first price: %s $%.2f",
                symbol,
                price,
            )



    async def disconnect(self) -> None:
        """
        Отключиться от Polymarket.
        """
        self.is_connected = False
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        logger.info("Отключено от Polymarket RTDS")

    def get_price(self, symbol: str) -> Optional[float]:
        """
        Получить последнюю цену Polymarket для BTCUSDT/ETHUSDT/SOLUSDT.
        Проверяет свежесть цены перед возвратом.
        """
        sym = self._normalize_symbol(symbol)
        price = self.last_prices.get(sym)
        last_ts = self.last_timestamps.get(sym)

        if not price:
            logger.warning(f"❌ RTDS: нет цены для {symbol}")
            return None

        # Проверяем свежесть цены
        if last_ts:
            age_seconds = (datetime.now() - last_ts).total_seconds()
            if age_seconds > self.PRICE_STALENESS_THRESHOLD:
                # Предупреждаем, но не чаще чем раз в 60 секунд
                now = time.time()
                last_warning = self._stale_price_warnings.get(sym, 0)
                if now - last_warning > 60:
                    self._stale_price_warnings[sym] = now
                    logger.warning(
                        f"⚠️  RTDS: цена {symbol} застыла! Последнее обновление: {age_seconds:.0f}s назад (${price:.2f})"
                    )

        return price

    def get_timestamp(self, symbol: str) -> Optional[datetime]:
        sym = self._normalize_symbol(symbol)
        return self.last_timestamps.get(sym)
