"""
PPT演示制作服务端入口
提供HTTP和WebSocket服务
"""

import asyncio
import argparse
import logging
from typing import Optional

import uvicorn
from fastapi import FastAPI

from HttpServer import HttpServer
from WebSocketServer import WebSocketServer
from api import PPTServerAPI
from controller import WPSPresentationController

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('PPT_Server')

def parseArgs():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='PPT演示制作服务端')
    parser.add_argument('--mode', type=str, default='both',
                      choices=['http', 'ws', 'both'],
                      help='服务模式: http, ws, 或 both (默认)')
    parser.add_argument('--http-port', type=int, default=8000,
                      help='HTTP服务端口 (默认: 8000)')
    parser.add_argument('--ws-port', type=int, default=8765,
                      help='WebSocket服务端口 (默认: 8765)')
    return parser.parse_args()

async def runHttpServer(port: int = 8000):
    """运行HTTP服务器
    
    Args:
        port: 服务端口
    """
    controller = WPSPresentationController()
    api = PPTServerAPI(controller)
    server = HttpServer(api)
    config = uvicorn.Config(server.app, host="0.0.0.0", port=port, log_level="info")
    server_instance = uvicorn.Server(config)
    
    # 创建一个任务来检查关闭标志
    async def check_shutdown():
        while not server.should_exit:
            await asyncio.sleep(1)
        logger.info("检测到关闭信号，正在关闭服务器...")
        server_instance.should_exit = True
    
    # 启动关闭检查任务
    shutdown_task = asyncio.create_task(check_shutdown())
    
    try:
        await server_instance.serve()
    finally:
        shutdown_task.cancel()
        try:
            await shutdown_task
        except asyncio.CancelledError:
            pass

async def runWebSocketServer(port: int = 8765):
    """运行WebSocket服务器
    
    Args:
        port: 服务端口
    """
    controller = WPSPresentationController()
    api = PPTServerAPI(controller)
    server = WebSocketServer(api)
    await server.start(port)

async def runUnifiedServer(mode: str = 'both', http_port: int = 8000, ws_port: int = 8765):
    """运行统一服务器
    
    Args:
        mode: 服务模式 ('http', 'ws', 或 'both')
        http_port: HTTP服务端口
        ws_port: WebSocket服务端口
    """
    tasks = []
    http_server = None
    ws_server = None
    
    try:
        if mode in ['http', 'both']:
            controller = WPSPresentationController()
            api = PPTServerAPI(controller)
            http_server = HttpServer(api)
            config = uvicorn.Config(http_server.app, host="0.0.0.0", port=http_port, log_level="info")
            server_instance = uvicorn.Server(config)
            tasks.append(asyncio.create_task(server_instance.serve()))
            
            # 添加关闭检查任务
            async def check_http_shutdown():
                while not http_server.should_exit:
                    await asyncio.sleep(1)
                logger.info("检测到HTTP服务器关闭信号，正在关闭...")
                server_instance.should_exit = True
            tasks.append(asyncio.create_task(check_http_shutdown()))
            
        if mode in ['ws', 'both']:
            controller = WPSPresentationController()
            api = PPTServerAPI(controller)
            ws_server = WebSocketServer(api)
            tasks.append(asyncio.create_task(ws_server.start(ws_port)))
            
        if not tasks:
            logger.error("未指定有效的服务模式")
            return
            
        # 等待所有任务完成
        await asyncio.gather(*tasks)
        
    except asyncio.CancelledError:
        logger.info("收到取消信号，正在关闭服务...")
    except Exception as e:
        logger.error(f"服务器运行出错: {str(e)}")
    finally:
        logger.info("服务正在关闭...")
        
        # 取消所有任务
        for task in tasks:
            if not task.done():
                task.cancel()
        
        # 等待所有任务完成
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # 关闭HTTP服务器
        if http_server and hasattr(http_server, 'app'):
            try:
                await http_server.app.shutdown()
            except:
                pass
        
        # 关闭WebSocket服务器
        if ws_server:
            try:
                await ws_server.stop()
            except:
                pass
        
        logger.info("服务已关闭")

if __name__ == "__main__":
    try:
        args = parseArgs()
        logger.info(f"启动服务: 模式={args.mode}, HTTP端口={args.http_port}, WS端口={args.ws_port}")
        asyncio.run(runUnifiedServer(args.mode, args.http_port, args.ws_port))
    except KeyboardInterrupt:
        logger.info("收到键盘中断信号，正在关闭服务...")
    except Exception as e:
        logger.error(f"服务启动失败: {str(e)}")
    finally:
        logger.info("服务已完全关闭")