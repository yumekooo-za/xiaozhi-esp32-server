"""
PPT控制服务配置文件
包含控制器配置、服务器配置等
"""

# 控制器配置
CONTROLLER_CONFIG = {
    'load_wait_time': 3,           # WPS加载等待时间(秒)
    'focus_attempts': 5,           # 设置焦点尝试次数
    'default_highlight_color': (255, 0, 0),  # 默认高亮颜色(RGB)
    'font_size_scale': 1.1,        # 字体大小缩放比例
    'click_delay': 0.1,            # 点击延迟时间(秒)
    'window_activation_delay': 0.2 # 窗口激活延迟时间(秒)
}

# HTTP服务器配置
HTTP_CONFIG = {
    'host': '0.0.0.0',
    'port': 8000,
    'cors_origins': ['*'],
    'cors_methods': ['*'],
    'cors_headers': ['*']
}

# WebSocket服务器配置
WS_CONFIG = {
    'host': '0.0.0.0',
    'port': 8765,
    'ping_interval': 20,
    'ping_timeout': 20,
    'close_timeout': 10
}

# 日志配置
LOGGING_CONFIG = {
    'level': 'DEBUG',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'handlers': [
        'console',
        'file'
    ],
    'log_file': 'wps_controller.log'
}

# 支持的PPT文件格式
SUPPORTED_FORMATS = [
    '.pptx',  # PowerPoint 2007及以上版本
    '.ppt',   # PowerPoint 97-2003
    '.pptm',  # 启用宏的PowerPoint
    '.ppsx',  # PowerPoint放映
    '.pps',   # PowerPoint 97-2003放映
    '.ppsm',  # 启用宏的PowerPoint放映
    '.dps',   # WPS演示文稿
    '.dpt',   # WPS演示文稿模板
    '.dpsx',  # WPS演示文稿2007格式
    '.dptx'   # WPS演示文稿2007模板
] 