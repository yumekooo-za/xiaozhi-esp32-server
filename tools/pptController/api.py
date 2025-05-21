"""
PPT控制服务API实现
提供针对PPT操作的各种API方法
"""

from typing import List, Optional, Tuple

from models import APIResponse, PPTErrorCode
from controller import WPSPresentationController
import logging
import psutil

logger = logging.getLogger(__name__)

class PPTServerAPI:
    """PPT控制服务器API"""
    
    def __init__(self, controller):
        """初始API"""
        self.controller = controller
        
    async def openPresentation(self, filepath: str) -> APIResponse:
        """打开指定PPT文件"""
        if not filepath:
            return APIResponse(
                status=False,
                code=PPTErrorCode.FILE_NOT_FOUND,
                message='未提供文件路径'
            )
        elif self.controller.openPresentation(filepath):
            return APIResponse(
                status=True,
                code=PPTErrorCode.SUCCESS,
                message=f'成功打开PPT文件: {filepath}',
                data={'slide_count': self.controller.slideCount()}
            )
        else:
            return APIResponse(
                status=False,
                code=PPTErrorCode.FILE_NOT_FOUND,
                message=f'无法打开PPT文件: {filepath}'
            )
    
    async def startShow(self) -> APIResponse:
        """开始放映PPT"""
        success = self.controller.startSlideshow()
        return APIResponse(
            status=success,
            code=PPTErrorCode.SUCCESS if success else PPTErrorCode.UNKNOWN_ERROR,
            message='开始放映成功' if success else '开始放映失败'
        )
    
    async def nextSlide(self) -> APIResponse:
        """切换到下一页"""
        success = self.controller.nextSlide()
        return APIResponse(
            status=success,
            code=PPTErrorCode.SUCCESS if success else PPTErrorCode.UNKNOWN_ERROR,
            message='下一页成功' if success else '下一页失败'
        )
    
    async def prevSlide(self) -> APIResponse:
        """切换到上一页"""
        success = self.controller.prevSlide()
        return APIResponse(
            status=success,
            code=PPTErrorCode.SUCCESS if success else PPTErrorCode.UNKNOWN_ERROR,
            message='上一页成功' if success else '上一页失败'
        )
    
    async def gotoSlide(self, slide_number: int) -> APIResponse:
        """跳转到指定幻灯片"""
        if not slide_number:
            return APIResponse(
                status=False,
                code=PPTErrorCode.SLIDE_OUT_OF_RANGE,
                message='未提供幻灯片编号'
            )
        elif self.controller.gotoSlide(slide_number):
            return APIResponse(
                status=True,
                code=PPTErrorCode.SUCCESS,
                message=f'成功跳转到第{slide_number}页'
            )
        else:
            return APIResponse(
                status=False,
                code=PPTErrorCode.SLIDE_OUT_OF_RANGE,
                message=f'无效的幻灯片编号: {slide_number}'
            )
    
    async def stopShow(self) -> APIResponse:
        """结束放映"""
        success = self.controller.closeSlideshow()
        return APIResponse(
            status=success,
            code=PPTErrorCode.SUCCESS if success else PPTErrorCode.UNKNOWN_ERROR,
            message='放映已结束' if success else '结束放映失败'
        )
        
    async def getStatus(self) -> APIResponse:
        """获取当前状态"""
        try:
            is_ready = bool(self.controller.isReady())
            current_slide = int(self.controller.current_slide)
            slide_count = int(self.controller.slideCount() or 0)
            
            return APIResponse(
                status=True,
                code=PPTErrorCode.SUCCESS,
                message='获取状态成功',
                data={
                    'is_ready': is_ready,
                    'current_slide': current_slide,
                    'slide_count': slide_count
                }
            )
        except Exception as e:
            return APIResponse(
                status=False,
                code=PPTErrorCode.UNKNOWN_ERROR,
                message=f'获取状态失败: {str(e)}'
            )
            
    async def forceRefresh(self) -> APIResponse:
        """强制刷新当前幻灯片视图，用于样式高亮后刷新显示"""
        success = self.controller._refreshView()
        return APIResponse(
            status=success,
            code=PPTErrorCode.SUCCESS if success else PPTErrorCode.UNKNOWN_ERROR,
            message='刷新成功' if success else '刷新失败'
        )
            
    async def styleHighlight(self, text: str, color: List[int] = None) -> APIResponse:
        """通过直接修改文本样式实现持久高亮"""
        if not text or not isinstance(text, str):
            return APIResponse(
                status=False,
                code=PPTErrorCode.INVALID_COMMAND,
                message='无效的文本输入'
            )
        
        highlight_color = (255, 0, 0)  # 默认红色
        if color and isinstance(color, list) and len(color) == 3:
            highlight_color = tuple(color)
        
        success = self.controller.styleHighlight(text, highlight_color)
        
        return APIResponse(
            status=success,
            code=PPTErrorCode.SUCCESS if success else PPTErrorCode.UNKNOWN_ERROR,
            message=f'样式高亮成功: "{text}"' if success else f'样式高亮失败: "{text}"'
        )
    
    async def clearStyleHighlights(self, slide_number: Optional[int] = None) -> APIResponse:
        """清除文本样式高亮"""
        success = self.controller.clearStyleHighlights(slide_number)
        
        return APIResponse(
            status=success,
            code=PPTErrorCode.SUCCESS if success else PPTErrorCode.UNKNOWN_ERROR,
            message='样式高亮清除成功' if success else '样式高亮清除失败'
        )

    async def closePresentation(self) -> APIResponse:
        """关闭当前打开的PPT，不保存修改
        
        Returns:
            APIResponse: 操作结果
        """
        try:
            success = self.controller.closePresentation()
            
            # 检查WPS进程是否真的关闭了
            try:
                wps_running = False
                for proc in psutil.process_iter(['name']):
                    if proc.info['name'] and proc.info['name'].lower() == 'wpp.exe':
                        wps_running = True
                        break
                if not wps_running:
                    logger.info("确认WPS已完全关闭")
                    return APIResponse(
                        status=True,
                        code=PPTErrorCode.SUCCESS,
                        message='关闭PPT成功'
                    )
            except:
                pass
                
            return APIResponse(
                status=success,
                code=PPTErrorCode.SUCCESS if success else PPTErrorCode.UNKNOWN_ERROR,
                message='关闭PPT成功' if success else '关闭PPT失败'
            )
        except Exception as e:
            # 即使发生异常，也检查WPS是否真的关闭了
            try:
                wps_running = False
                for proc in psutil.process_iter(['name']):
                    if proc.info['name'] and proc.info['name'].lower() == 'wpp.exe':
                        wps_running = True
                        break
                if not wps_running:
                    logger.info("确认WPS已完全关闭")
                    return APIResponse(
                        status=True,
                        code=PPTErrorCode.SUCCESS,
                        message='关闭PPT成功'
                    )
            except:
                pass
                
            logger.error(f"关闭PPT失败: {str(e)}")
            return APIResponse(
                status=False,
                code=PPTErrorCode.UNKNOWN_ERROR,
                message=f'关闭PPT失败: {str(e)}'
            ) 