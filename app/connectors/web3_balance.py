"""
Web3 коннектор для получения баланса USDC на Polygon.
"""

import logging
from typing import Optional

from web3 import Web3
from web3.exceptions import ContractLogicError, BadFunctionCallOutput

logger = logging.getLogger(__name__)


class Web3BalanceChecker:
    """
    Класс для получения баланса USDC через Web3 на Polygon.
    """

    # ERC20 ABI для функции balanceOf
    ERC20_ABI = [
        {
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "type": "function"
        }
    ]

    def __init__(self, rpc_url: str = "https://polygon-rpc.com"):
        """
        Инициализация Web3 коннектора.

        Args:
            rpc_url: URL RPC ноды Polygon
        """
        self.rpc_url = rpc_url
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))

        # USDC.e контракт на Polygon (новый стандарт)
        self.usdc_contract_address = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"

        # USDC (старый) на Polygon
        self.usdc_legacy_address = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

        # Инициализируем контракты
        self.usdc_contract = self.w3.eth.contract(
            address=self.usdc_contract_address,
            abi=self.ERC20_ABI
        )

        self.usdc_legacy_contract = self.w3.eth.contract(
            address=self.usdc_legacy_address,
            abi=self.ERC20_ABI
        )

    def is_connected(self) -> bool:
        """Проверка подключения к RPC."""
        try:
            return self.w3.is_connected()
        except Exception as exc:
            logger.warning("Ошибка проверки подключения к RPC: %s", exc)
            return False

    def get_usdc_balance(self, wallet_address: str) -> float:
        """
        Получить баланс USDC для кошелька.

        Проверяет оба контракта USDC (новый и старый) и возвращает сумму.

        Args:
            wallet_address: Адрес кошелька

        Returns:
            Баланс в USDC (float)
        """
        if not self.is_connected():
            logger.error("Нет подключения к Polygon RPC")
            return 0.0

        if not self.w3.is_address(wallet_address):
            logger.error("Неверный адрес кошелька: %s", wallet_address)
            return 0.0

        # Конвертируем адрес в checksum формат для совместимости с web3.py
        try:
            wallet_address = self.w3.to_checksum_address(wallet_address)
            logger.debug("Адрес конвертирован в checksum формат: %s", wallet_address)
        except Exception as checksum_exc:
            logger.warning("Не удалось конвертировать адрес в checksum формат: %s", checksum_exc)
            # Продолжаем с оригинальным адресом

        total_balance = 0.0

        # Проверяем USDC.e (новый контракт)
        try:
            balance_wei = self.usdc_contract.functions.balanceOf(wallet_address).call()
            balance_usdc = balance_wei / 1_000_000  # USDC имеет 6 decimals
            total_balance += balance_usdc
            logger.debug("USDC.e баланс: %.6f", balance_usdc)
        except (ContractLogicError, BadFunctionCallOutput) as exc:
            logger.debug("Ошибка получения USDC.e баланса: %s", exc)
        except Exception as exc:
            logger.warning("Неожиданная ошибка при получении USDC.e баланса: %s", exc)

        # Проверяем USDC (старый контракт)
        try:
            balance_wei = self.usdc_legacy_contract.functions.balanceOf(wallet_address).call()
            balance_usdc = balance_wei / 1_000_000  # USDC имеет 6 decimals
            total_balance += balance_usdc
            logger.debug("USDC legacy баланс: %.6f", balance_usdc)
        except (ContractLogicError, BadFunctionCallOutput) as exc:
            logger.debug("Ошибка получения USDC legacy баланса: %s", exc)
        except Exception as exc:
            logger.warning("Неожиданная ошибка при получении USDC legacy баланса: %s", exc)

        logger.info("Общий USDC баланс для %s: %.6f", wallet_address, total_balance)
        return total_balance

    def get_token_balance(self, token_address: str, wallet_address: str, decimals: int = 18) -> float:
        """
        Получить баланс любого ERC20 токена.

        Args:
            token_address: Адрес контракта токена
            wallet_address: Адрес кошелька
            decimals: Количество decimals токена

        Returns:
            Баланс в токенах (float)
        """
        if not self.is_connected():
            logger.error("Нет подключения к Polygon RPC")
            return 0.0

        try:
            contract = self.w3.eth.contract(
                address=token_address,
                abi=self.ERC20_ABI
            )

            balance_wei = contract.functions.balanceOf(wallet_address).call()
            balance_tokens = balance_wei / (10 ** decimals)

            logger.debug("Баланс токена %s: %.6f", token_address, balance_tokens)
            return balance_tokens

        except Exception as exc:
            logger.warning("Ошибка получения баланса токена %s: %s", token_address, exc)
            return 0.0


# Глобальный экземпляр для использования в приложении
web3_balance_checker = Web3BalanceChecker()