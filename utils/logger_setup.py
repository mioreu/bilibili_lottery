import logging
import sys
import os
import re
from logging.handlers import RotatingFileHandler

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_LOG_FILE_NAME = 'bili.log'
_DEFAULT_ERROR_LOG_FILE_NAME = 'output/error.log'

class LogColors:
    RESET = '\033[0m'
    GREEN = '\033[92m'      # 绿色
    YELLOW = '\033[93m'     # 黄色
    RED = '\033[91m'        # 红色
    BLUE = '\033[94m'       # 蓝色
    PINK = '\033[95m'       # 粉色
    YELLOW_BOLD = '\033[1;33m'  # 粗体黄色

class ColoredConsoleFormatter(logging.Formatter):
    """控制台日志格式"""
    PROGRESS_PATTERN = re.compile(r'\[进度')
    
    LOG_LEVEL_COLORS = {
        logging.DEBUG: LogColors.YELLOW_BOLD,
        logging.INFO: LogColors.RESET,
        logging.WARNING: LogColors.YELLOW,
        logging.ERROR: LogColors.RED,
        logging.CRITICAL: LogColors.RED,
    }

    # 语义关键词配置
    SUCCESS_LOAD = ["加载成功", "个帐号", "检测到", "正在处理", "正在执行操作"]
    SUCCESS_KEYWORDS = ["已关注", "成功", "运行完成", "处理完成", "生成成功", "操作完成"]
    LOAD_PROCESS = ["开始", "检测", "正在爬取"]
    ING = ["正在为动态"]

    def format(self, record):
        log_color = self.LOG_LEVEL_COLORS.get(record.levelno, LogColors.RESET)
        message_content = record.getMessage()

        if "----" in message_content:
            log_color = LogColors.PINK
        elif self.PROGRESS_PATTERN.search(message_content):
            log_color = LogColors.PINK
        elif any(key in message_content for key in self.SUCCESS_LOAD):
            log_color = LogColors.BLUE
        elif any(key in message_content for key in self.ING):
            log_color = LogColors.YELLOW
        elif any(key in message_content for key in self.SUCCESS_KEYWORDS):
            log_color = LogColors.GREEN
        elif any(key in message_content for key in self.LOAD_PROCESS):
            log_color = LogColors.YELLOW
        elif record.levelname == 'ERROR' or '失败' in message_content or '错误' in message_content:
            log_color = LogColors.RED

        try:
            formatter = logging.Formatter(self._fmt, datefmt=self.datefmt)
            base_message = formatter.format(record)
        except Exception as e:
            base_message = f"{record.levelname}: {message_content}"
            logging.error(f"日志格式化异常: {e}", exc_info=True)

        return f"{log_color}{base_message}{LogColors.RESET}"

def setup_logger(log_level="INFO", log_file=None, error_file=None): # 增加error_file参数
    """配置全局日志记录器"""
    logger = logging.getLogger("Bilibili")
    if logger.hasHandlers():
        return logger

    # 确保日志文件路径有效
    if log_file is None:
        log_file = os.path.join(project_root, _DEFAULT_LOG_FILE_NAME)
    if error_file is None:
        error_file = os.path.join(project_root, _DEFAULT_ERROR_LOG_FILE_NAME)

    # 控制台输出配置
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColoredConsoleFormatter(
        '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(console_handler)

    # 文件输出配置
    file_handler = None
    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=1*1024*1024, # 1MB
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - [%(name)s] - %(funcName)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        logger.addHandler(file_handler)
    except Exception as e:
        logger.error(f"主文件日志初始化失败({log_file}): {e}", exc_info=False)


    # 文件输出配置 (错误日志)
    error_file_handler = None
    try:
        os.makedirs(os.path.dirname(error_file), exist_ok=True)
        error_file_handler = RotatingFileHandler(
            error_file,
            maxBytes=1*1024*1024, # 1MB
            backupCount=3,
            encoding='utf-8'
        )
        error_file_handler.setLevel(logging.ERROR) # 只记录 ERROR 及以上
        error_file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - [%(name)s] - %(funcName)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        logger.addHandler(error_file_handler)
    except Exception as e:
        logger.error(f"错误文件日志初始化失败({error_file}): {e}", exc_info=False)


    # 组装日志处理器
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    # 抑制第三方库日志
    for lib in ["requests", "urllib3"]:
        logging.getLogger(lib).setLevel(logging.WARNING)

    return logger