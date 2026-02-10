"""
Мониторинг и автоматический перезапуск Chainlink коллектора.
"""

import asyncio
import logging
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional

import psutil

from app.config import settings

logger = logging.getLogger(__name__)


class CollectorMonitor:
    """
    Класс для мониторинга и управления Chainlink коллектором.
    """

    def __init__(self, check_interval: int = 300):  # 5 минут по умолчанию
        """
        Инициализация монитора коллектора.

        Args:
            check_interval: Интервал проверки в секундах (по умолчанию 300 = 5 мин)
        """
        self.check_interval = check_interval
        self.monitoring_task: Optional[asyncio.Task] = None
        self.is_monitoring = False
        self.last_restart_time = 0
        self.restart_cooldown = 60  # Не перезапускать чаще чем раз в минуту

        # Пути к файлам
        self.data_file = Path("data/chainlink_btc_prices.json")
        self.start_script = Path("start_chainlink_collector.sh")

        # Статистика
        self.stats = {
            "checks": 0,
            "restarts": 0,
            "last_check": 0,
            "last_restart": 0,
            "status": "unknown"
        }

    def start_monitoring(self) -> None:
        """Запустить фоновый мониторинг коллектора."""
        if self.is_monitoring:
            logger.warning("Мониторинг коллектора уже запущен")
            return

        self.is_monitoring = True
        self.monitoring_task = asyncio.create_task(self._monitor_loop())
        logger.info("Запущен мониторинг коллектора (проверка каждые %s сек)", self.check_interval)

    def stop_monitoring(self) -> None:
        """Остановить мониторинг коллектора."""
        self.is_monitoring = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            logger.info("Мониторинг коллектора остановлен")

    async def _monitor_loop(self) -> None:
        """Основной цикл мониторинга."""
        while self.is_monitoring:
            try:
                await self._check_and_restart_collector()
                await asyncio.sleep(self.check_interval)
            except Exception as exc:
                logger.error("Ошибка в цикле мониторинга коллектора: %s", exc)
                await asyncio.sleep(60)  # Подождать минуту при ошибке

    async def _check_and_restart_collector(self) -> None:
        """Проверить статус коллектора и перезапустить при необходимости."""
        self.stats["checks"] += 1
        self.stats["last_check"] = time.time()

        is_running = self._check_collector_running()
        data_fresh = self._check_data_freshness()

        logger.debug("Проверка коллектора: running=%s, data_fresh=%s", is_running, data_fresh)

        # Определяем статус
        if is_running and data_fresh:
            self.stats["status"] = "healthy"
            logger.debug("Коллектор в норме")
        elif not is_running:
            self.stats["status"] = "stopped"
            logger.warning("Коллектор остановлен, перезапуск...")
            await self._restart_collector()
        elif not data_fresh:
            self.stats["status"] = "stale_data"
            logger.warning("Данные устарели, перезапуск коллектора...")
            await self._restart_collector()
        else:
            self.stats["status"] = "unknown"
            logger.warning("Неизвестный статус коллектора")

    def _check_collector_running(self) -> bool:
        """
        Проверить, запущен ли процесс коллектора.

        Returns:
            True если коллектор запущен
        """
        try:
            # Ищем процессы с chainlink_collector в командной строке
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info.get('cmdline', [])
                    if cmdline and any('chainlink_collector' in str(arg) for arg in cmdline):
                        logger.debug("Найден процесс коллектора: PID=%s, CMD=%s",
                                   proc.info['pid'], ' '.join(cmdline))
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # Также проверяем по имени процесса
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if 'python' in proc.info['name'].lower():
                        # Проверяем командную строку Python процесса
                        cmdline = proc.cmdline()
                        if any('chainlink_price_collector.py' in str(arg) for arg in cmdline):
                            logger.debug("Найден Python процесс коллектора: PID=%s", proc.info['pid'])
                            return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        except Exception as exc:
            logger.warning("Ошибка при проверке процессов: %s", exc)

        return False

    def _check_data_freshness(self, max_age_minutes: int = 10) -> bool:
        """
        Проверить свежесть данных коллектора.

        Args:
            max_age_minutes: Максимальный возраст данных в минутах

        Returns:
            True если данные свежие
        """
        try:
            if not self.data_file.exists():
                logger.debug("Файл данных не существует: %s", self.data_file)
                return False

            # Проверяем время модификации файла
            stat = self.data_file.stat()
            file_age_seconds = time.time() - stat.st_mtime
            file_age_minutes = file_age_seconds / 60

            logger.debug("Возраст файла данных: %.1f минут", file_age_minutes)

            if file_age_minutes > max_age_minutes:
                logger.warning("Файл данных устарел: %.1f минут > %s минут",
                             file_age_minutes, max_age_minutes)
                return False

            return True

        except Exception as exc:
            logger.warning("Ошибка при проверке свежести данных: %s", exc)
            return False

    async def _restart_collector(self) -> None:
        """Перезапустить коллектор."""
        current_time = time.time()

        # Проверяем cooldown
        if current_time - self.last_restart_time < self.restart_cooldown:
            logger.warning("Перезапуск слишком частый, пропускаем (cooldown: %s сек)",
                         self.restart_cooldown)
            return

        try:
            self.stats["restarts"] += 1
            self.stats["last_restart"] = current_time
            self.last_restart_time = current_time

            logger.info("Перезапуск коллектора (попытка %s)", self.stats["restarts"])

            # Проверяем, запущен ли коллектор вручную (по lock файлу)
            from app.connectors.chainlink_price_collector import ChainlinkPriceCollector
            temp_collector = ChainlinkPriceCollector()

            if temp_collector._is_collector_running():
                logger.info("Коллектор запущен вручную (найден lock файл), не перезапускаем автоматически")
                return

            # Сначала останавливаем старый процесс
            await self._stop_collector()

            # Ждем немного
            await asyncio.sleep(2)

            # Запускаем новый процесс
            await self._start_collector()

            logger.info("Коллектор успешно перезапущен")

        except Exception as exc:
            logger.error("Ошибка при перезапуске коллектора: %s", exc)

    async def _stop_collector(self) -> None:
        """Остановить коллектор."""
        try:
            # Используем pkill для остановки всех процессов chainlink_collector
            result = await asyncio.create_subprocess_exec(
                'pkill', '-f', 'chainlink_collector',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.wait()

            if result.returncode == 0:
                logger.info("Старый процесс коллектора остановлен")
            else:
                logger.debug("pkill вернул код %s (возможно, процесс уже остановлен)",
                           result.returncode)

        except Exception as exc:
            logger.warning("Ошибка при остановке коллектора: %s", exc)

    async def _start_collector(self) -> None:
        """Запустить коллектор."""
        try:
            if not self.start_script.exists():
                raise FileNotFoundError(f"Скрипт запуска не найден: {self.start_script}")

            # Запускаем скрипт в фоне
            process = await asyncio.create_subprocess_exec(
                'bash', str(self.start_script),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Не ждем завершения, так как скрипт должен работать в фоне
            logger.info("Скрипт запуска коллектора выполнен: %s", self.start_script)

            # Даем время на запуск
            await asyncio.sleep(5)

            # Проверяем, запустился ли процесс
            if self._check_collector_running():
                logger.info("Коллектор успешно запущен")
            else:
                logger.warning("Коллектор не запустился после выполнения скрипта")

        except Exception as exc:
            logger.error("Ошибка при запуске коллектора: %s", exc)
            raise

    def get_status(self) -> Dict:
        """
        Получить текущий статус коллектора.

        Returns:
            Словарь со статусом и статистикой
        """
        is_running = self._check_collector_running()
        data_fresh = self._check_data_freshness()

        # Определяем общий статус
        if is_running and data_fresh:
            overall_status = "healthy"
        elif not is_running:
            overall_status = "stopped"
        elif not data_fresh:
            overall_status = "stale_data"
        else:
            overall_status = "unknown"

        # Информация о данных
        data_info = {}
        if self.data_file.exists():
            stat = self.data_file.stat()
            data_info = {
                "exists": True,
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "age_minutes": (time.time() - stat.st_mtime) / 60
            }
        else:
            data_info = {"exists": False}

        return {
            "status": overall_status,
            "is_running": is_running,
            "data_fresh": data_fresh,
            "data_info": data_info,
            "stats": self.stats.copy(),
            "monitoring_active": self.is_monitoring
        }

    async def manual_restart(self) -> Dict:
        """
        Ручной перезапуск коллектора.

        Returns:
            Результат перезапуска
        """
        try:
            logger.info("Ручной перезапуск коллектора")
            await self._restart_collector()

            # Проверяем результат
            await asyncio.sleep(3)  # Даем время на запуск
            final_status = self.get_status()

            return {
                "success": final_status["status"] == "healthy",
                "status": final_status["status"],
                "message": "Коллектор перезапущен" if final_status["status"] == "healthy" else "Перезапуск завершен с проблемами"
            }

        except Exception as exc:
            logger.error("Ошибка при ручном перезапуске: %s", exc)
            return {
                "success": False,
                "status": "error",
                "message": f"Ошибка перезапуска: {exc}"
            }


# Глобальный экземпляр монитора
collector_monitor = CollectorMonitor()