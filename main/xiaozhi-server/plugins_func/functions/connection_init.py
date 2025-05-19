from config.logger import setup_logging
import asyncio
from plugins_func.functions.handle_device import _set_device_property

TAG = __name__
logger = setup_logging()

async def initialize_default_settings(conn):
    """初始化设备默认设置"""
    try:
        # 等待功能处理程序和IoT描述符初始化完成
        max_wait = 10  # 最大等待秒数
        while (conn.func_handler is None or not conn.func_handler.finish_init) and max_wait > 0:
            await asyncio.sleep(0.5)
            max_wait -= 0.5
        
        if max_wait <= 0:
            logger.bind(tag=TAG).warning("功能处理程序未初始化完成，跳过默认设置配置")
            return

        # 等待IoT描述符加载
        await asyncio.sleep(1)
        
        # 设置默认音量为100
        if "Speaker" in conn.iot_descriptors:
            logger.bind(tag=TAG).info("正在设置默认音量为100")
            try:
                volume = await _set_device_property(
                    conn,
                    device_name="音量",
                    device_type="Speaker",
                    method_name="SetVolume",
                    property_name="volume",
                    new_value=100,
                    action="set"
                )
                logger.bind(tag=TAG).info(f"默认音量已设置为: {volume}")
            except Exception as e:
                logger.bind(tag=TAG).error(f"设置默认音量失败: {e}")
        else:
            logger.bind(tag=TAG).info("未发现Speaker设备，跳过音量设置")
            
    except Exception as e:
        logger.bind(tag=TAG).error(f"初始化默认设置失败: {e}")
