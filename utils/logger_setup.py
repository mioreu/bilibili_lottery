import logging
import sys
import os
import re
from logging.handlers import RotatingFileHandler


class LogColors:
    """定义日志输出的ANSI颜色码"""
    RESET = '\033[0m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    PINK = '\033[95m'
    YELLOW_BOLD = '\033[1;33m'


class ColoredConsoleFormatter(logging.Formatter):
    """
    一个自定义的日志格式化器，根据日志内容和级别添加颜色。
    """
    PROGRESS_PATTERN = re.compile(r'\[进度')

    LOG_LEVEL_COLORS = {
        logging.DEBUG: LogColors.YELLOW_BOLD,
        logging.INFO: LogColors.RESET,
        logging.WARNING: LogColors.YELLOW,
        logging.ERROR: LogColors.RED,
        logging.CRITICAL: LogColors.RED,
    }

    # 语义关键词配置
    KEYWORD_COLORS = {
        LogColors.PINK: ["----", PROGRESS_PATTERN],
        LogColors.BLUE: ["加载成功", "个帐号", "检测到", "正在处理", "正在执行操作"],
        LogColors.YELLOW: ["开始", "检测", "正在爬取", "正在为动态", "正在检查"],
        LogColors.GREEN: ["已关注", "成功", "运行完成", "处理完成", "生成成功", "操作完成"],
        LogColors.RED: ['没有发现新', '错误'],  # 针对特定错误消息
    }

    def format(self, record):
        message_content = record.getMessage()
        log_color = self.LOG_LEVEL_COLORS.get(record.levelno, LogColors.RESET)

        # 基于内容关键词覆盖颜色
        for color, keywords in self.KEYWORD_COLORS.items():
            for keyword in keywords:
                if isinstance(keyword, re.Pattern) and keyword.search(message_content):
                    log_color = color
                    break
                elif isinstance(keyword, str) and keyword in message_content:
                    log_color = color
                    break
            if log_color != self.LOG_LEVEL_COLORS.get(record.levelno, LogColors.RESET):  # 如果颜色被覆盖，则跳出
                break

        # 错误级别特殊处理
        if record.levelname == 'ERROR':
            log_color = LogColors.RED

        try:
            # 使用父类的格式化方法获取基本消息
            base_message = super().format(record)
        except Exception as e:
            # 如果格式化失败，则回退到简单格式
            base_message = f"{record.levelname}: {message_content}"
            logging.error(f"日志格式化异常: {e}", exc_info=True)

        return f"{log_color}{base_message}{LogColors.RESET}"


def _get_project_root():
    """获取项目根目录"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _setup_console_handler(logger):
    """配置控制台日志处理器"""
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColoredConsoleFormatter(
        '%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(console_handler)


def _setup_file_handler(logger, file_path, level, formatter):
    """
    配置并添加一个旋转文件日志处理器。
    """
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        file_handler = RotatingFileHandler(
            file_path,
            maxBytes=1 * 1024 * 1024,  # 1MB
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.error(f"文件日志初始化失败({file_path}): {e}", exc_info=False)


def setup_logger(log_level="INFO", log_file=None, error_file=None):
    """
    配置全局日志记录器。
    """
    logger = logging.getLogger("Bilibili")
    if logger.hasHandlers():
        return logger

    project_root = _get_project_root()
    default_log_file = os.path.join(project_root)
    default_error_file = os.path.join(project_root)

    log_file = log_file if log_file else default_log_file
    error_file = error_file if error_file else default_error_file

    _setup_console_handler(logger)

    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(name)s] - %(funcName)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    _setup_file_handler(logger, log_file, logging.INFO, file_formatter)
    _setup_file_handler(logger, error_file, logging.ERROR, file_formatter)

    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # 抑制第三方库日志
    for lib in ["requests", "urllib3"]:
        logging.getLogger(lib).setLevel(logging.WARNING)

    return logger