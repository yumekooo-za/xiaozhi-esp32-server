"""
PPT演示制作HTTP API模块
提供REST API接口供客户端调用
"""

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from models import APIResponse, PPTErrorCode
from api import PPTServerAPI

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('PPT_HTTP_Server')

# 请求模型
class OpenRequest(BaseModel):
    filepath: str

class GotoRequest(BaseModel):
    slide: int

class HighlightRequest(BaseModel):
    text: str
    color: Optional[list[int]] = None

class HttpServer:
    """提供HTTP API的服务组件"""
    
    def __init__(self, apiInstance: PPTServerAPI):
        """初始化HTTP服务器
        
        Args:
            apiInstance: PPT API实例
        """
        self.api = apiInstance
        self.app = self.createApp()
        self.should_exit = False
        
    def createApp(self) -> FastAPI:
        """创建FastAPI应用"""
        app = FastAPI(
            title="PPT演示API", 
            description="提供PPT演示的HTTP API"
        )
        
        # 允许跨域
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # 注册路由
        self.registerRoutes(app)
        
        return app
    
    def registerRoutes(self, app: FastAPI):
        """注册路由处理函数"""
        
        @app.on_event("startup")
        async def startup():
            """启动服务"""
            logger.info("服务启动中...")
            
        @app.on_event("shutdown") 
        async def shutdown():
            """关闭服务"""
            logger.info("服务已关闭")

        @app.post("/api/ppt/open")
        async def openPpt(request: OpenRequest):
            """打开PPT文件"""
            res = await self.api.openPresentation(request.filepath)
            if not res.status:
                raise HTTPException(status_code=400, detail=res.message)
            return {"status": "success"}

        @app.post("/api/ppt/start")
        async def startShow():
            """开始演示"""
            res = await self.api.startShow()
            if not res.status:
                raise HTTPException(status_code=400, detail=res.message)
            return {"status": "success"}

        @app.post("/api/ppt/next")
        async def nextSlide():
            """下一页"""
            res = await self.api.nextSlide()
            if not res.status:
                raise HTTPException(status_code=400, detail=res.message)
            return {"status": "success"}

        @app.post("/api/ppt/prev") 
        async def prevSlide():
            """上一页"""
            res = await self.api.prevSlide()
            if not res.status:
                raise HTTPException(status_code=400, detail=res.message)
            return {"status": "success"}

        @app.post("/api/ppt/goto")
        async def gotoSlide(request: GotoRequest):
            """跳转到指定页"""
            res = await self.api.gotoSlide(request.slide)
            if not res.status:
                raise HTTPException(status_code=400, detail=res.message)
            return {"status": "success"}

        @app.post("/api/ppt/stop")
        async def stopShow():
            """结束演示"""
            res = await self.api.stopShow()
            if not res.status:
                raise HTTPException(status_code=400, detail=res.message)
            return {"status": "success"}

        @app.get("/api/ppt/status")
        async def getStatus():
            """获取当前状态"""
            try:
                res = await self.api.getStatus()
                if not res.status:
                    raise HTTPException(status_code=400, detail=res.message)
                
                # 过滤掉敏感数据，只返回COM对象
                safeData = {
                    "is_ready": bool(res.data.get("is_ready", False)),
                    "current_slide": int(res.data.get("current_slide", 0)),
                    "slide_count": int(res.data.get("slide_count", 0))
                }
                logger.info(f"获取状态成功: {safeData}")
                return safeData
            except Exception as e:
                logger.error(f"获取状态失败: {str(e)}")
                raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")

        @app.post("/api/ppt/refresh")
        async def forceRefresh():
            """强制刷新当前页面视图，用于样式高亮后刷新"""
            res = await self.api.forceRefresh()
            if not res.status:
                raise HTTPException(status_code=400, detail=res.message)
            return {"status": "success"}

        @app.post("/api/ppt/styleHighlight")
        async def styleHighlight(request: HighlightRequest):
            """文本样式高亮"""
            res = await self.api.styleHighlight(request.text, request.color)
            if not res.status:
                raise HTTPException(status_code=400, detail=res.message)
            return {"status": "success"}
            
        @app.post("/api/ppt/clearStyleHighlights")
        async def clearStyleHighlights(slide: Optional[int] = None):
            """清除文本样式高亮"""
            res = await self.api.clearStyleHighlights(slide)
            if not res.status:
                raise HTTPException(status_code=400, detail=res.message)
            return {"status": "success"}

        @app.post("/api/ppt/close")
        async def closePpt():
            """关闭当前打开的PPT，不保存修改"""
            res = await self.api.closePresentation()
            if not res.status:
                raise HTTPException(status_code=400, detail=res.message)
            return {"status": "success"}

        @app.post("/api/server/shutdown")
        async def shutdownServer():
            """关闭服务器"""
            logger.info("收到关闭服务器请求")
            self.should_exit = True
            return {"status": "success", "message": "服务器正在关闭..."} 