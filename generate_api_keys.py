#!/usr/bin/env python3
"""
Генерация API ключей Polymarket из приватного ключа.

Использование:
1. Установите приватный ключ в .env: POLYMARKET_PRIVATE_KEY=ваш_ключ_без_0x
2. Запустите: python3 generate_api_keys.py
3. Скопируйте полученные API_KEY, API_SECRET, API_PASSPHRASE в .env
"""

import os
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from py_clob_client.client import ClobClient
from dotenv import load_dotenv

# Загружаем .env файл
load_dotenv()

def generate_api_keys():
    """Генерируем API ключи из приватного ключа."""
    print("🔑 Генерация API ключей Polymarket...")
    print("=" * 50)

    # Получаем приватный ключ из .env
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY")

    if not private_key:
        print("❌ Ошибка: POLYMARKET_PRIVATE_KEY не найден в .env файле")
        print("💡 Добавьте в .env: POLYMARKET_PRIVATE_KEY=ваш_приватный_ключ_без_0x")
        return

    if private_key.startswith("your_") or private_key == "your_private_key_here":
        print("❌ Ошибка: POLYMARKET_PRIVATE_KEY содержит placeholder значение")
        print("💡 Замените на реальный приватный ключ без префикса 0x")
        return

    print(f"✅ Приватный ключ найден (длина: {len(private_key)} символов)")

    try:
        # Создаем клиента с приватным ключом
        print("🔗 Подключаемся к Polymarket CLOB...")
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=private_key,
            chain_id=137  # Polygon mainnet
        )

        # Генерируем API ключи
        print("🎯 Генерируем API ключи...")
        api_creds = client.create_api_key()

        print("\n" + "=" * 50)
        print("🎉 API ключи успешно сгенерированы!")
        print("=" * 50)

        print(f"API_KEY: {api_creds.api_key}")
        print(f"API_SECRET: {api_creds.api_secret}")
        print(f"API_PASSPHRASE: {api_creds.api_passphrase}")

        print("\n" + "=" * 50)
        print("📝 Добавьте эти ключи в ваш .env файл:")
        print("=" * 50)
        print(f"POLYMARKET_API_KEY={api_creds.api_key}")
        print(f"POLYMARKET_API_SECRET={api_creds.api_secret}")
        print(f"POLYMARKET_API_PASSPHRASE={api_creds.api_passphrase}")

        print("\n⚠️  ВАЖНО:")
        print("- API_SECRET показывается только один раз!")
        print("- Сохраните его в безопасном месте")
        print("- Не коммитьте .env файл в git")

        return api_creds

    except Exception as exc:
        print(f"❌ Ошибка при генерации API ключей: {exc}")
        print("\n💡 Возможные причины:")
        print("- Приватный ключ неправильный")
        print("- Проблемы с сетью или API Polymarket")
        print("- Недостаточно средств на газ в кошельке")
        return None

if __name__ == "__main__":
    generate_api_keys()