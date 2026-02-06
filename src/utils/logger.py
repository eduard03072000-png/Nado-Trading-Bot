"""
Настройка логирования для бота
"""
import io
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime


def setup_logging(log_dir: str = "data/logs", level: str = "DEBUG"):
    """Настроить систему логирования"""

    # Создаем директорию для логов
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    # Формат логов
    log_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Основной лог файл (явно utf-8)
    log_file = Path(log_dir) / f"bot_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(log_format)

    # Консольный вывод — оборачиваем stderr.buffer в utf-8 stream
    # иначе на Windows cp1251 эмодзи в логах crashают процесс
    utf8_stream = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    console_handler = logging.StreamHandler(stream=utf8_stream)
    console_handler.setFormatter(log_format)

    # Настройка корневого логгера
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
