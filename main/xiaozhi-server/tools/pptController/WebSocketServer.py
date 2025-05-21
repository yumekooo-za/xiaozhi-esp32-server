"""
PPT控制服务WebSocket API模块
提供WebSocket实时控制接口
"""

import asyncio
import json
import logging
from dataclasses import asdict
from typing import Set

import websockets

from models import APIResponse, PPTErrorCode
from api import PPTServerAPI

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('PPT_WS_Server')

class WebSocketServer:
    """WebSocket服务器组件"""
    
    def __init__(self, apiInstance: PPTServerAPI):
        """初始化WebSocket服务器
        
        Args:
            apiInstance: PPT API实例
        """
        self.api = apiInstance
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
    
    async def handleWebsocketMessage(self, websocket, message: str):
        """处理WebSocket客户端消息"""
        try:
            data = json.loads(message)
            action = data.get('action')
            payload = data.get('data', {})
            
            response = APIResponse(
                status=False,
                code=PPTErrorCode.INVALID_COMMAND,
                message='无效的操作命令'
            )
            
            if action == 'open':
                filepath = payload.get('filepath')
                response = await self.api.openPresentation(filepath)
            elif action == 'control':
                cmd = payload.get('command')
                if cmd == 'start':
                    response = await self.api.startShow()
                elif cmd == 'next':
                    response = await self.api.nextSlide()
                elif cmd == 'prev':
                    response = await self.api.prevSlide()
            elif action == 'goto':
                slide = payload.get('slide')
                response = await self.api.gotoSlide(slide)
            elif action == 'status':
                response = await self.api.getStatus()
            elif action == 'endShow':
                response = await self.api.stopShow()
            elif action == 'refresh':
                response = await self.api.forceRefresh()
            elif action == 'styleHighlight':
                text = payload.get('text')
                color = payload.get('color')
                response = await self.api.styleHighlight(text, color)
            elif action == 'clearStyleHighlights':
                slide = payload.get('slide')
                response = await self.api.clearStyleHighlights(slide)
            elif action == 'close':
                response = await self.api.closePresentation()
            
            logger.info(f"处理命令: {action}, 结果: {response.message}")
            await websocket.send(json.dumps(asdict(response)))
            
        except Exception as e:
            errorMsg = APIResponse(
                status=False,
                code=PPTErrorCode.UNKNOWN_ERROR,
                message=f'处理命令时发生错误: {str(e)}'
            )
            logger.error(f"处理消息错误: {str(e)}")
            await websocket.send(json.dumps(asdict(errorMsg)))

    async def websocketHandler(self, websocket, path):
        """WebSocket连接处理器"""
        clientAddr = websocket.remote_address
        logger.info(f"新连接来自: {clientAddr}")
        self.clients.add(websocket)
        
        try:
            # 验证WebSocket协议
            if not websocket.request_headers.get('Upgrade', '').lower() == 'websocket':
                logger.warning("非WebSocket连接已拒绝")
                await websocket.close(code=1002)  # 协议错误
                return
                
            async for message in websocket:
                await self.handleWebsocketMessage(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"连接关闭: {clientAddr}")
        except Exception as e:
            logger.error(f"处理错误: {str(e)}")
        finally:
            self.clients.remove(websocket)
            logger.info(f"连接清理: {clientAddr}")

    async def start(self, host='0.0.0.0', port=8765):
        """启动WebSocket服务器"""
        server = await websockets.serve(
            self.websocketHandler,
            host,
            port,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=10
        )
        logger.info(f"WebSocket服务已启动，监听 {host}:{port}")
        return server 