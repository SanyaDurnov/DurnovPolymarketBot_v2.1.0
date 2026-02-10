#!/usr/bin/env python3
"""
Тест автоматического входа в активный рынок.
Находит подходящий рынок и входит в него, затем мониторит цены.
"""
import asyncio
import sys
from datetime import datetime

from polymarket.client import PolymarketClient
from monitoring.price_monitor import PriceMonitor
from analysis.market_analyzer import MarketAnalyzer
from analysis.orderbook_analyzer import OrderbookAnalyzer
from trading.order_manager import OrderManager
from trading.auto_entry import AutoEntry
from app.config import (
    POLYMARKET_ACTIVE_ACCOUNT,
    POLYMARKET_PRIVATE_KEY_1,
    POLYMARKET_PRIVATE_KEY_2,
    POLYMARKET_WALLET_ADDRESS_1,
    POLYMARKET_WALLET_ADDRESS_2,
)


async def test_auto_entry_and_price_monitoring():
    """Тест полного цикла: вход в рынок + мониторинг цен."""
    print("\n" + "="*70)
    print("🧪 ТЕСТ: Автоматический вход в рынок + мониторинг цен")
    print("="*70 + "\n")

    # Инициализация
    print("1️⃣ Инициализация компонентов...")

    pm_client = PolymarketClient()

    # Выбираем аккаунт
    if POLYMARKET_ACTIVE_ACCOUNT == 1:
        private_key = POLYMARKET_PRIVATE_KEY_1
        wallet_address = POLYMARKET_WALLET_ADDRESS_1
    else:
        private_key = POLYMARKET_PRIVATE_KEY_2
        wallet_address = POLYMARKET_WALLET_ADDRESS_2

    print(f"   Аккаунт: {POLYMARKET_ACTIVE_ACCOUNT}")
    print(f"   Wallet: {wallet_address[:10]}...")

    price_monitor = PriceMonitor()
    await price_monitor.start()
    print("   ✅ PriceMonitor запущен\n")

    orderbook_analyzer = OrderbookAnalyzer(pm_client)
    market_analyzer = MarketAnalyzer(pm_client, orderbook_analyzer, price_monitor)
    order_manager = OrderManager(pm_client, wallet_address, private_key)

    # Находим подходящий рынок
    print("2️⃣ Поиск подходящего рынка...")

    markets = pm_client.get_markets()
    if not markets:
        print("❌ Не найдено рынков!")
        await price_monitor.stop()
        return False

    print(f"   Загружено {len(markets)} рынков\n")

    # Ищем активный 15m рынок с хорошей ликвидностью
    suitable_markets = []
    for market in markets:
        market_id = market.get("id")
        title = market.get("title", "")
        state = market.get("state")

        # Проверяем, что это 15m рынок
        if "15 minutes" not in title.lower() and "15m" not in title.lower():
            continue

        # Проверяем, что рынок активен
        if state != "active":
            continue

        # Проверяем ликвидность
        orderbook_prices = orderbook_analyzer.get_best_prices(market_id)
        if not orderbook_prices:
            continue

        up_ask = orderbook_prices.get("up_ask", 1.0)
        down_ask = orderbook_prices.get("down_ask", 1.0)

        # Проверяем, что цены разумные (не слишком низкие)
        if up_ask < 0.1 or down_ask < 0.1:
            continue

        # Проверяем, что спред не слишком большой
        spread = abs(up_ask + down_ask - 1.0)
        if spread > 0.15:
            continue

        suitable_markets.append({
            "market_id": market_id,
            "title": title,
            "up_ask": up_ask,
            "down_ask": down_ask,
            "spread": spread,
        })

    if not suitable_markets:
        print("❌ Не найдено подходящих рынков!")
        await price_monitor.stop()
        return False

    # Выбираем первый подходящий рынок
    selected_market = suitable_markets[0]
    market_id = selected_market["market_id"]

    print(f"✅ Выбран рынок: {selected_market['title']}")
    print(f"   Market ID: {market_id}")
    print(f"   UP: ${selected_market['up_ask']:.2f}, DOWN: ${selected_market['down_ask']:.2f}")
    print(f"   Spread: {selected_market['spread']:.2%}\n")

    # Входим в рынок
    print("3️⃣ Вход в рынок...")

    auto_entry = AutoEntry(
        pm_client=pm_client,
        order_manager=order_manager,
        orderbook_analyzer=orderbook_analyzer,
        market_analyzer=market_analyzer,
        price_monitor=price_monitor,
    )

    try:
        # Начинаем вход
        await auto_entry.execute_entry(market_id, "test-session")

        print("\n✅ Вход в рынок выполнен успешно!\n")

        # Мониторим цены в течение 30 секунд
        print("4️⃣ Мониторинг цен (30 секунд)...\n")

        # Получаем символ для этого рынка
        market_data = pm_client.get_market(market_id)
        if not market_data:
            print("⚠️ Не удалось получить данные рынка")
            await price_monitor.stop()
            return True

        # Определяем символ из title
        title_lower = market_data.get("title", "").lower()
        if "btc" in title_lower or "bitcoin" in title_lower:
            symbol = "BTCUSDT"
        elif "eth" in title_lower or "ethereum" in title_lower:
            symbol = "ETHUSDT"
        elif "sol" in title_lower or "solana" in title_lower:
            symbol = "SOLUSDT"
        else:
            print("⚠️ Не удалось определить символ")
            await price_monitor.stop()
            return True

        print(f"   Символ: {symbol}")
        print(f"   Проверка цены каждые 2 секунды:\n")

        # Мониторим
        start_time = datetime.now()
        last_price = None
        price_changes = 0

        for i in range(15):  # 15 проверок по 2 секунды = 30 секунд
            current_price = price_monitor.get_price(symbol)

            if current_price:
                timestamp = datetime.now().strftime("%H:%M:%S")

                if last_price and last_price != current_price:
                    change = current_price - last_price
                    price_changes += 1
                    print(
                        f"   {timestamp} | {symbol}: ${last_price:.2f} → ${current_price:.2f} "
                        f"(Δ{change:+.2f}) 📊"
                    )
                else:
                    print(f"   {timestamp} | {symbol}: ${current_price:.2f}")

                last_price = current_price
            else:
                print(f"   {datetime.now().strftime('%H:%M:%S')} | Нет цены")

            await asyncio.sleep(2)

        duration = (datetime.now() - start_time).total_seconds()

        print(f"\n✅ Мониторинг завершен!")
        print(f"   Длительность: {duration:.1f}с")
        print(f"   Обновлений цены: {price_changes}")
        print(f"   Частота обновлений: {price_changes / (duration / 60):.1f}/мин")

        await price_monitor.stop()
        return True

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        await price_monitor.stop()
        return False


async def main():
    """Запуск теста."""
    print("\n" + "🚀 ЗАПУСК ТЕСТА AUTO ENTRY 🚀".center(70, "="))

    success = await test_auto_entry_and_price_monitoring()

    print("\n" + "="*70)
    if success:
        print("✅ ТЕСТ ПРОЙДЕН!")
        return 0
    else:
        print("❌ ТЕСТ НЕ ПРОШЕЛ!")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  Тест прерван пользователем")
        sys.exit(1)
