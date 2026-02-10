 #!/usr/bin/env python3
"""
Тест получения баланса Polymarket.
"""

import os
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from polymarket.client import PolymarketClient
from app.config import settings

def test_balance():
    """Тестируем получение баланса."""
    print("🔍 Тестируем получение баланса Polymarket...")
    print(f"Wallet Address: {settings.polymarket_wallet_address}")
    print(f"Private Key: {'*' * len(settings.polymarket_private_key) if settings.polymarket_private_key else 'None'}")

    # Создаем клиент
    client = PolymarketClient()

    # Проверяем инициализацию
    print(f"Client initialized: {client._client is not None}")

    # Пытаемся получить баланс
    print("📊 Получаем баланс...")
    balance = client.get_balance()

    if balance:
        print(f"✅ Баланс получен: {balance}")
        if isinstance(balance, dict):
            usdc_balance = balance.get("usdc", balance.get("USDC"))
            if usdc_balance:
                print(f"💰 USDC баланс: {usdc_balance}")
    else:
        print("❌ Не удалось получить баланс")

    return balance

if __name__ == "__main__":
    test_balance()