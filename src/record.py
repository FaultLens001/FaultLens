from loguru import logger
from rich.console import Console

console = Console()


def print_and_log(msg):
    console.print(msg)
    logger.info(msg)


def log_exception(e):
    logger.exception(e)
