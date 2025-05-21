"""
PPT控制服务端 - WPS演示文稿控制器
提供对WPS演示文稿的底层控制功能
"""

import os
import threading
import time
from typing import Optional, Tuple, Dict

import pythoncom
import win32com.client
import win32gui
import win32con
import win32api
import logging
import win32process

from config import CONTROLLER_CONFIG, SUPPORTED_FORMATS, LOGGING_CONFIG

# 配置日志格式
logging.basicConfig(
    level=getattr(logging, LOGGING_CONFIG['level']),
    format=LOGGING_CONFIG['format'],
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOGGING_CONFIG['log_file'])
    ]
)

logger = logging.getLogger('WPS_Controller')

class WPSPresentationController:
    """演示文稿控制器"""
    
    def __init__(self, config: Dict = None):
        """初始化控制器
        
        Args:
            config: 配置参数，如果为None则使用默认配置
        """
        self.app = None
        self.presentation = None
        self.current_slide = 0
        self.comInitialized = False
        
        # 使用默认配置
        self.config = CONTROLLER_CONFIG.copy()
        
        # 更新用户配置
        if config:
            self.config.update(config)
        
    def findWPSWindow(self) -> Optional[int]:
        """查找WPS窗口句柄
        
        Returns:
            窗口句柄，如果未找到则返回None
        """
        def callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    windows.append((hwnd, title))
            return True
            
        windows = []
        win32gui.EnumWindows(callback, windows)
        
        # 打印所有可见窗口的标题，用于调试
        logger.debug("当前所有可见窗口:")
        for hwnd, title in windows:
            logger.debug(f"窗口句柄: {hwnd}, 标题: {title}")
            
        # 支持的演示文稿格式
        ppt_extensions = [
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
        
        # 查找可能的WPS窗口
        for hwnd, title in windows:
            # 检查标题是否以支持的扩展名结尾并包含WPS Office
            if any(title.endswith(ext + ' - WPS Office') for ext in ppt_extensions):
                logger.info(f"找到WPS窗口: {title}")
                return hwnd
                
            # 检查是否包含"WPS演示"字样（中文版WPS特有）
            if "WPS演示" in title and any(title.endswith(ext) for ext in ppt_extensions):
                logger.info(f"找到WPS窗口(中文版): {title}")
                return hwnd
                
            # 检查窗口类名（WPS特有的类名）
            try:
                class_name = win32gui.GetClassName(hwnd)
                if class_name in ['KWPPFrame', 'KWPPFrameWnd'] and any(title.endswith(ext) for ext in ppt_extensions):
                    logger.info(f"找到WPS窗口(通过类名): {title}")
                    return hwnd
            except:
                pass
                
        return None

    def simulateMouseClick(self, hwnd: int) -> bool:
        """在指定窗口中心位置模拟鼠标点击
        
        Args:
            hwnd: 窗口句柄
            
        Returns:
            是否成功模拟点击
        """
        try:
            # 获取窗口位置
            rect = win32gui.GetWindowRect(hwnd)
            if not rect:
                return False
                
            # 计算窗口中心点
            center_x = (rect[0] + rect[2]) // 2
            center_y = (rect[1] + rect[3]) // 2
            
            # 保存当前鼠标位置
            original_pos = win32gui.GetCursorPos()
            
            # 移动鼠标到窗口中心
            win32api.SetCursorPos((center_x, center_y))
            time.sleep(0.1)
            
            # 模拟鼠标左键点击
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.1)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            
            # 恢复鼠标位置
            win32api.SetCursorPos(original_pos)
            
            logger.info(f"成功在窗口中心模拟点击: ({center_x}, {center_y})")
            return True
            
        except Exception as e:
            logger.error(f"模拟鼠标点击失败: {str(e)}")
            return False

    def setWindowFocus(self, windowTitle: str) -> bool:
        """设置指定标题的窗口为焦点
        
        Args:
            windowTitle: 窗口标题（此参数现在仅用于日志记录）
            
        Returns:
            是否成功设置焦点
        """
        try:
            # 查找WPS窗口
            hwnd = self.findWPSWindow()
            if hwnd is None:
                logger.warning("未找到WPS窗口")
                return False
                
            # 多次尝试设置焦点
            for attempt in range(5):  # 增加到5次尝试
                try:
                    # 如果窗口最小化，恢复它
                    if win32gui.IsIconic(hwnd):
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                        time.sleep(0.2)  # 等待恢复完成
                    
                    # 如果窗口未最大化，最大化它
                    if not win32gui.IsZoomed(hwnd):
                        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                        time.sleep(0.2)  # 等待最大化完成
                    
                    # 强制激活窗口
                    win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                    
                    # 尝试多种方式激活窗口
                    # 1. 使用SetWindowPos
                    win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, 
                                        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                    time.sleep(0.2)  # 增加等待时间
                    win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, 
                                        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                    
                    # 2. 使用SetForegroundWindow
                    win32gui.SetForegroundWindow(hwnd)
                    time.sleep(0.2)
                    
                    # 3. 使用BringWindowToTop
                    win32gui.BringWindowToTop(hwnd)
                    time.sleep(0.2)
                    
                    # 4. 使用AttachThreadInput来强制设置焦点
                    try:
                        # 获取当前线程ID
                        currentThread = win32api.GetCurrentThreadId()
                        # 获取目标窗口线程ID
                        targetThread = win32process.GetWindowThreadProcessId(hwnd)[0]
                        # 附加线程输入
                        win32process.AttachThreadInput(currentThread, targetThread, True)
                        # 设置焦点
                        win32gui.SetFocus(hwnd)
                        # 分离线程输入
                        win32process.AttachThreadInput(currentThread, targetThread, False)
                    except Exception as e:
                        logger.warning(f"AttachThreadInput失败: {str(e)}")
                    
                    # 5. 再次尝试SetForegroundWindow
                    win32gui.SetForegroundWindow(hwnd)
                    
                    # 6. 尝试使用SendMessage
                    try:
                        win32gui.SendMessage(hwnd, win32con.WM_ACTIVATE, win32con.WA_ACTIVE, 0)
                        win32gui.SendMessage(hwnd, win32con.WM_SETFOCUS, 0, 0)
                    except Exception as e:
                        logger.warning(f"SendMessage失败: {str(e)}")
                    
                    # 7. 模拟鼠标点击
                    self.simulateMouseClick(hwnd)
                    
                    # 等待较长时间确保窗口激活
                    time.sleep(0.5)
                    
                    # 检查窗口是否真的在前台
                    if win32gui.GetForegroundWindow() == hwnd:
                        logger.info(f"成功设置窗口焦点: {win32gui.GetWindowText(hwnd)}")
                        return True
                    else:
                        logger.warning(f"尝试 {attempt + 1} 未能获得焦点")
                        
                except Exception as e:
                    logger.warning(f"设置焦点尝试 {attempt + 1} 失败: {str(e)}")
                    time.sleep(0.3)  # 增加失败后的等待时间
            
            logger.warning("无法设置窗口焦点")
            return False
            
        except Exception as e:
            logger.error(f"设置窗口焦点失败: {str(e)}")
            return False
            
    def connect(self) -> bool:
        """连接WPS演示应用"""
        try:
            # 确保先释放已有资源
            self.close()
            
            # 初始COM并连接WPS
            pythoncom.CoInitialize()
            self.app = win32com.client.Dispatch("KWPP.Application")
            self.app.Visible = True  # 可视化便于调试
            return True
        except Exception as e:
            print(f"连接WPS失败: {e}")
            self.close()
            return False
            
    def openPresentation(self, filepath: str) -> bool:
        """打开指定PPT文件"""
        # 先关闭可能存在的旧实例
        self.close()
        
        # 确保文件存在
        import os
        if not os.path.exists(filepath):
            print(f"[ERROR] 文件不存在: {filepath}")
            return False
            
        # 连接WPS
        if not self.connect():
            return False
            
        try:
            # 检查WPS是否响应
            if not self.app or not hasattr(self.app, 'Presentations'):
                print("[ERROR] WPS应用未正确初始化")
                return False
                
            self.presentation = self.app.Presentations.Open(filepath)
            self.current_slide = 1
            print(f"[INFO] 成功打开PPT: {filepath}")
            
            # 等待WPS完全加载
            logger.info("等待WPS完全加载...")
            time.sleep(self.config['load_wait_time'])
            
            # 尝试设置窗口焦点
            hwnd = self.findWPSWindow()
            if hwnd:
                max_attempts = 3  # 最大尝试次数
                for attempt in range(max_attempts):
                    try:
                        # 获取窗口位置
                        rect = win32gui.GetWindowRect(hwnd)
                        if rect:
                            # 计算窗口最左边的中间点
                            left_x = rect[0] + 5  # 距离左边缘5像素
                            center_y = (rect[1] + rect[3]) // 2
                            
                            # 保存当前鼠标位置
                            original_pos = win32gui.GetCursorPos()
                            
                            # 移动鼠标到目标位置
                            win32api.SetCursorPos((left_x, center_y))
                            time.sleep(self.config['click_delay'])
                            
                            # 模拟鼠标左键点击
                            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                            time.sleep(self.config['click_delay'])
                            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                            
                            # 恢复鼠标位置
                            win32api.SetCursorPos(original_pos)
                            
                            logger.info(f"成功在窗口左侧模拟点击: ({left_x}, {center_y})")
                            time.sleep(self.config['window_activation_delay'])  # 等待窗口响应
                            
                            # 检查窗口是否真的获得了焦点
                            if win32gui.GetForegroundWindow() == hwnd:
                                logger.info("窗口成功获得焦点")
                                return True
                            else:
                                logger.warning(f"点击后窗口未获得焦点 (尝试 {attempt + 1}/{max_attempts})")
                    except Exception as e:
                        logger.warning(f"模拟点击失败 (尝试 {attempt + 1}/{max_attempts}): {str(e)}")
                    
                    # 如果不是最后一次尝试，等待后重试
                    if attempt < max_attempts - 1:
                        time.sleep(0.5)
                
                logger.warning("多次尝试后窗口仍未获得焦点")
            
            return True
        except Exception as e:
            print(f"[ERROR] 打开PPT失败: {e}")
            self.close()
            return False
            
    def close(self) -> bool:
        """关闭演示文稿并释放所有资源
        
        Returns:
            是否成功关闭并清理
        """
        logger.info("==== 开始关闭演示文稿并清理资源 ====")
        success = True
        
        try:
            # 1. 清理高亮记录
            if hasattr(self, 'highlightRecords'):
                logger.debug("清理高亮记录")
                self.highlightRecords.clear()
                delattr(self, 'highlightRecords')
                
            if hasattr(self, 'styleHighlights'):
                logger.debug("清理样式高亮记录")
                self.styleHighlights.clear()
                delattr(self, 'styleHighlights')
            
            # 2. 强制结束可能存在的幻灯片放映
            if self.presentation and hasattr(self.presentation, 'SlideShowWindow'):
                try:
                    logger.debug("关闭幻灯片放映")
                    self.presentation.SlideShowWindow.View.Exit()
                    time.sleep(0.5)  # 等待放映窗口关闭
                except Exception as e:
                    logger.warning(f"关闭放映窗口时出错: {str(e)}")
                    success = False
            
            # 3. 关闭演示文稿
            if self.presentation:
                try:
                    logger.debug("关闭演示文稿")
                    # 检查演示文稿是否仍然有效
                    if hasattr(self.presentation, 'Saved'):
                        self.presentation.Close()
                        logger.info("成功关闭演示文稿")
                    else:
                        logger.warning("演示文稿已经关闭")
                except Exception as e:
                    logger.warning(f"关闭演示文稿时出错: {str(e)}")
                    success = False
                finally:
                    self.presentation = None
                    
            # 4. 退出WPS应用
            if self.app:
                try:
                    logger.debug("退出WPS应用")
                    self.app.Quit()
                    logger.info("成功退出WPS应用")
                except Exception as e:
                    logger.warning(f"退出WPS应用时出错: {str(e)}")
                    success = False
                finally:
                    self.app = None
                    
            # 5. 强制结束WPS进程
            try:
                logger.debug("强制结束WPS进程")
                os.system('taskkill /f /im wpp.exe >nul 2>&1')
                time.sleep(0.5)  # 等待进程完全退出
            except Exception as e:
                logger.warning(f"强制结束WPS进程时出错: {str(e)}")
                success = False
                
            # 6. 检查并清理临时文件
            try:
                logger.debug("检查临时文件")
                temp_dir = os.environ.get('TEMP', '')
                if temp_dir:
                    # 查找并删除WPS相关的临时文件
                    for file in os.listdir(temp_dir):
                        if file.startswith('~$') and (file.endswith('.ppt') or 
                                                    file.endswith('.pptx') or 
                                                    file.endswith('.dps') or 
                                                    file.endswith('.dpsx')):
                            try:
                                os.remove(os.path.join(temp_dir, file))
                                logger.debug(f"删除临时文件: {file}")
                            except:
                                pass
            except Exception as e:
                logger.warning(f"清理临时文件时出错: {str(e)}")
                # 临时文件清理失败不影响整体结果
                
            # 7. 重置所有状态变量
            logger.debug("重置状态变量")
            self.current_slide = 0
            self.comInitialized = False
            
            # 8. 确保COM对象被释放
            try:
                logger.debug("释放COM对象")
                pythoncom.CoUninitialize()
            except Exception as e:
                logger.warning(f"释放COM对象时出错: {str(e)}")
                success = False
                
            # 9. 最终检查WPS进程是否真的关闭了
            try:
                import psutil
                wps_running = False
                for proc in psutil.process_iter(['name']):
                    if proc.info['name'] and proc.info['name'].lower() == 'wpp.exe':
                        wps_running = True
                        logger.warning("WPS进程仍在运行，尝试再次强制关闭")
                        os.system('taskkill /f /im wpp.exe >nul 2>&1')
                        time.sleep(0.5)
                        break
                        
                if not wps_running:
                    logger.info("确认WPS已完全关闭")
            except Exception as e:
                logger.warning(f"检查WPS进程状态时出错: {str(e)}")
                success = False
                
            logger.info("==== 资源清理完成 ====")
            return success
            
        except Exception as e:
            logger.error(f"关闭过程中发生异常: {str(e)}")
            logger.debug("详细错误信息", exc_info=True)
            
            # 发生异常时也要尝试清理资源
            try:
                self.presentation = None
                self.current_slide = 0
                self.comInitialized = False
                if self.app:
                    self.app.Quit()
                os.system('taskkill /f /im wpp.exe >nul 2>&1')
                pythoncom.CoUninitialize()
            except:
                pass
                
            return False
            
    def slideCount(self) -> Optional[int]:
        """获取总页数"""
        if self.presentation:
            return self.presentation.Slides.Count
        return 0
        
    def gotoSlide(self, slide_number: int) -> bool:
        """跳转到指定幻灯片"""
        if not self.presentation or slide_number < 1 or slide_number > self.slideCount():
            return False
            
        try:
            self.presentation.SlideShowWindow.View.GotoSlide(slide_number)
            self.current_slide = slide_number
            return True
        except Exception as e:
            print(f"跳转幻灯片失败: {e}")
            return False
            
    def nextSlide(self) -> bool:
        """下一页"""
        return self.gotoSlide(self.current_slide + 1)
        
    def prevSlide(self) -> bool:
        """上一页"""
        return self.gotoSlide(self.current_slide - 1)
        
    def startSlideshow(self) -> bool:
        """开始放映幻灯片"""
        if not self.presentation:
            return False
            
        for attempt in range(3):
            try:
                # 启动放映
                self.presentation.SlideShowSettings.Run()
                
                # 确认放映状态
                if hasattr(self.presentation, 'SlideShowWindow'):
                    # 等待幻灯片窗口初始化
                    time.sleep(0.5)
                    
                    # 检查窗口是否有效
                    if self.presentation.SlideShowWindow.View:
                        print(f"[INFO] 成功进入放映模式 (尝试 {attempt+1}/3)")
                        return True
                
                print(f"[WARN] 放映状态未确认 (尝试 {attempt+1}/3)")
                
            except Exception as e:
                print(f"[WARN] 开始放映失败 (尝试 {attempt+1}/3): {e}")
                
            if attempt < 2:
                time.sleep(0.5)
                
        print("[ERROR] 无法确认放映状态")
        return False
            
    def closeSlideshow(self) -> bool:
        """结束放映"""
        print("[DEBUG] 开始关闭放映流程")
        maxAttempts = 3
        for attempt in range(1, maxAttempts + 1):
            try:
                print(f"[DEBUG] 关闭尝试 {attempt}/{maxAttempts}")
                
                # 检查是否在放映状态
                if not self.presentation or not hasattr(self.presentation, 'SlideShowWindow'):
                    print("[DEBUG] 无放映窗口，无需关闭")
                    return True
                
                # 获取放映窗口引用
                ssWindow = self.presentation.SlideShowWindow
                if not ssWindow:
                    print("[DEBUG] 放映窗口已关闭")
                    return True
                
                # 关闭放映
                try:
                    ssWindow.View.Exit()
                    print("[DEBUG] 放映窗口退出成功")
                    time.sleep(0.5)
                    return True
                except Exception as e:
                    print(f"[WARN] 放映窗口退出异常: {e}")
                
                # 如果上述方法失败，尝试强制关闭
                if attempt == maxAttempts - 1:
                    try:
                        self.app.Quit()
                        print("[WARN] 已强制退出WPS应用")
                        return True
                    except:
                        pass
            
            except Exception as e:
                print(f"[WARN] 关闭放映尝试{attempt}失败: {e}")
            
            # 在重试前等待
            if attempt < maxAttempts:
                time.sleep(1)
        
        print("[ERROR] 关闭放映失败，已尝试最大次数")
        return False
    
    def isReady(self) -> bool:
        """检查是否准备就绪"""
        if not self.presentation:
            return False
            
        try:
            # 检查幻灯片属性是否可访问
            _ = self.presentation.Slides.Count
            return True
        except:
            return False
    
    def rgbToInt(self, rgb: Tuple[int, int, int]) -> int:
        """将RGB颜色转换为整数值
        
        Args:
            rgb: RGB颜色元组(r,g,b)
            
        Returns:
            整数表示的颜色值
        """
        r, g, b = rgb
        return r + (g << 8) + (b << 16)
        
    def clearHighlights(self, slide_number: Optional[int] = None) -> bool:
        """清除高亮标注
        
        Args:
            slide_number: 要清除的幻灯片编号，None表示当前幻灯片
            
        Returns:
            是否成功清除
        """
        logger.info(f"==== 开始清除高亮: slide_number={slide_number} ====")
        
        if not hasattr(self, 'highlightRecords'):
            logger.info("没有高亮记录需要清除")
            self.highlightRecords = {}
            return True
        
        try:
            # 确定目标幻灯片
            currentSlideIndex = None
            if hasattr(self.presentation, 'SlideShowWindow'):
                currentSlideIndex = self.presentation.SlideShowWindow.View.CurrentShowPosition
                logger.debug(f"当前幻灯片索引: {currentSlideIndex}")
            
            targetSlide = slide_number if slide_number is not None else currentSlideIndex
            logger.info(f"目标清除幻灯片: {targetSlide}")
            
            if targetSlide is None:
                logger.warning("无法确定目标幻灯片，可能未在放映状态")
                return False
            
            if targetSlide not in self.highlightRecords:
                logger.info(f"幻灯片 {targetSlide} 没有高亮记录需要清除")
                return True
            
            # 获取目标幻灯片
            try:
                slide = self.presentation.Slides(targetSlide)
                logger.debug(f"成功获取幻灯片对象: #{targetSlide}")
            except Exception as e:
                logger.error(f"获取幻灯片对象失败: {str(e)}")
                return False
            
            # 记录高亮数量
            highlightCount = len(self.highlightRecords[targetSlide])
            logger.info(f"幻灯片 {targetSlide} 上有 {highlightCount} 个高亮需要清除")
            
            # 清除该幻灯片上的所有高亮
            for index, record in enumerate(self.highlightRecords[targetSlide]):
                logger.debug(f"处理高亮记录 {index+1}/{highlightCount}: {record}")
                try:
                    if record['type'] == 'shape':
                        logger.debug(f"尝试清除形状高亮: shape_id={record['shape_id']}")
                        # 删除通过形状创建的高亮
                        shapeFound = False
                        for shapeIndex in range(1, slide.Shapes.Count + 1):
                            try:
                                shape = slide.Shapes(shapeIndex)
                                if shape.ID == record['shape_id']:
                                    logger.debug(f"找到匹配形状: #{shapeIndex}, ID={shape.ID}")
                                    shape.Delete()
                                    logger.info(f"成功删除形状高亮: ID={record['shape_id']}")
                                    shapeFound = True
                                    break
                            except Exception as shapeError:
                                logger.warning(f"处理形状 #{shapeIndex} 时出错: {str(shapeError)}")
                        
                        if not shapeFound:
                            logger.warning(f"未找到要清除的形状: ID={record['shape_id']}")
                    
                    elif record['type'] == 'text':
                        logger.debug(f"尝试清除文本高亮: shape_id={record['shape_id']}, "
                                    f"start={record['start']}, length={record['length']}")
                        
                        # 恢复被修改的文本格式
                        textFound = False
                        for shapeIndex in range(1, slide.Shapes.Count + 1):
                            try:
                                shape = slide.Shapes(shapeIndex)
                                if shape.ID == record['shape_id'] and hasattr(shape, "TextFrame"):
                                    logger.debug(f"找到匹配文本形状: #{shapeIndex}, ID={shape.ID}")
                                    
                                    textRange = shape.TextFrame.TextRange
                                    highlightRange = textRange.Characters(
                                        record['start']+1, 
                                        record['length']
                                    )
                                    
                                    # 记录当前样式用于调试
                                    currentBold = highlightRange.Font.Bold
                                    currentSize = highlightRange.Font.Size
                                    currentColor = highlightRange.Font.Color.RGB
                                    logger.debug(f"当前文本样式: Bold={currentBold}, "
                                                f"Size={currentSize}, Color={currentColor}")
                                    
                                    # 恢复默认格式
                                    logger.debug("恢复默认字体粗细")
                                    highlightRange.Font.Bold = False
                                    
                                    newSize = highlightRange.Font.Size / 1.1
                                    logger.debug(f"恢复字体大小: {highlightRange.Font.Size} -> {newSize}")
                                    highlightRange.Font.Size = newSize
                                    
                                    # 恢复默认颜色(通常是黑色)
                                    logger.debug("恢复默认字体颜色")
                                    highlightRange.Font.Color.RGB = self.rgbToInt((0, 0, 0))
                                    
                                    # 验证恢复是否成功
                                    restoredBold = highlightRange.Font.Bold
                                    restoredSize = highlightRange.Font.Size
                                    restoredColor = highlightRange.Font.Color.RGB
                                    logger.debug(f"恢复后样式: Bold={restoredBold}, "
                                                f"Size={restoredSize}, Color={restoredColor}")
                                    
                                    logger.info(f"成功恢复文本高亮: ID={record['shape_id']}")
                                    textFound = True
                                    break
                            except Exception as textError:
                                logger.warning(f"处理文本形状 #{shapeIndex} 时出错: {str(textError)}")
                        
                        if not textFound:
                            logger.warning(f"未找到要恢复的文本: ID={record['shape_id']}")
                except Exception as e:
                    logger.warning(f"清除单个高亮时出错: {str(e)}")
            
            # 清除记录
            self.highlightRecords[targetSlide] = []
            logger.info(f"==== 高亮清除完成: 幻灯片 {targetSlide} ====")
            return True
            
        except Exception as e:
            logger.error(f"清除高亮过程中发生异常: {str(e)}")
            logger.debug("详细错误信息", exc_info=True)
            return False

    def clearAllHighlights(self) -> bool:
        """清除所有幻灯片的高亮"""
        if not hasattr(self, 'highlightRecords'):
            self.highlightRecords = {}
            return True
        
        try:
            for slideNum in list(self.highlightRecords.keys()):
                self.clearHighlights(slideNum)
            return True
        except Exception as e:
            logger.error(f"清除所有高亮失败: {str(e)}")
            return False
    
    def refreshView(self) -> bool:
        """刷新演示视图，确保更改立即显示"""
        if not hasattr(self.presentation, 'SlideShowWindow'):
            return False
        
        view = self.presentation.SlideShowWindow.View
        current = view.CurrentShowPosition
        
        # 尝试多种刷新方法
        try:
            # 如果有多页，尝试临时切换页面
            total = self.presentation.Slides.Count
            if total > 1:
                tempPage = current + 1 if current < total else current - 1
                view.GotoSlide(tempPage)
                time.sleep(0.05)
                view.GotoSlide(current)
                return True
        except:
            pass
        
        # 如果只有一页或上面方法失败，尝试使用缩放
        try:
            if hasattr(view, "Zoom"):
                originalZoom = view.Zoom
                view.Zoom = not originalZoom
                time.sleep(0.05)
                view.Zoom = originalZoom
                return True
        except:
            pass
        
        return False

    def styleHighlight(self, text: str, color: Tuple[int, int, int] = None) -> bool:
        """通过直接修改文本样式实现持久高亮
        
        Args:
            text: 要高亮的文本
            color: RGB颜色元组，默认使用配置中的颜色
            
        Returns:
            是否成功高亮
        """
        logger.info(f"==== 开始文本样式高亮: '{text}' ====")
        
        if not self.presentation:
            logger.error("高亮失败: 未打开演示文稿")
            return False
        
        try:
            # 首先清除当前页的所有高亮，避免重叠
            currentSlideIndex = None
            if hasattr(self.presentation, 'SlideShowWindow'):
                currentSlideIndex = self.presentation.SlideShowWindow.View.CurrentShowPosition
                self.clearHighlights(currentSlideIndex)
            else:
                logger.error("未处于放映状态，无法执行高亮")
                return False
            
            # 获取当前幻灯片
            slide = self.presentation.Slides(currentSlideIndex)
            logger.debug(f"当前幻灯片: {currentSlideIndex}, 形状数量: {slide.Shapes.Count}")
            
            # 使用配置的颜色或传入的颜色
            highlight_color = color or self.config['default_highlight_color']
            
            # 查找并高亮文本
            found = False
            highlightId = f"style_highlight_{int(time.time() * 1000)}"
            
            for shapeIndex in range(1, slide.Shapes.Count + 1):
                try:
                    shape = slide.Shapes(shapeIndex)
                    
                    if not hasattr(shape, "TextFrame") or not shape.TextFrame.HasText:
                        continue
                    
                    textContent = shape.TextFrame.TextRange.Text
                    startPos = textContent.lower().find(text.lower())
                    
                    if startPos >= 0:
                        logger.info(f"在形状 #{shapeIndex} 中找到匹配文本 '{text}', 位置: {startPos}")
                        
                        try:
                            # 获取文本范围并修改样式
                            textRange = shape.TextFrame.TextRange
                            highlightRange = textRange.Characters(startPos+1, len(text))
                            
                            # 保存原始样式
                            originalColor = highlightRange.Font.Color.RGB
                            originalBold = highlightRange.Font.Bold
                            originalUnderline = getattr(highlightRange.Font, "Underline", False)
                            originalSize = highlightRange.Font.Size
                            
                            logger.debug(f"原始样式: Color={originalColor}, "
                                       f"Bold={originalBold}, Underline={originalUnderline}, "
                                       f"Size={originalSize}")
                            
                            # 修改样式 - 设置颜色
                            highlightRange.Font.Color.RGB = self.rgbToInt(highlight_color)
                            
                            # 设置加粗
                            highlightRange.Font.Bold = True
                            
                            # 设置下划线 (如果支持)
                            if hasattr(highlightRange.Font, "Underline"):
                                highlightRange.Font.Underline = True
                            
                            # 增大字体
                            newSize = originalSize * self.config['font_size_scale']
                            highlightRange.Font.Size = newSize
                            
                            # 记录高亮区域以便后续清除
                            if not hasattr(self, 'styleHighlights'):
                                self.styleHighlights = {}
                            
                            if currentSlideIndex not in self.styleHighlights:
                                self.styleHighlights[currentSlideIndex] = []
                            
                            # 记录原始样式和修改位置
                            self.styleHighlights[currentSlideIndex].append({
                                'id': highlightId,
                                'shape_id': shape.ID,
                                'start': startPos,
                                'length': len(text),
                                'original_style': {
                                    'color': originalColor,
                                    'bold': originalBold,
                                    'underline': originalUnderline,
                                    'size': originalSize
                                }
                            })
                            
                            found = True
                            logger.info(f"文本样式高亮成功: '{text}'")
                            break
                        except Exception as styleError:
                            logger.error(f"设置文本样式失败: {str(styleError)}")
                            logger.debug("详细错误信息", exc_info=True)
                except Exception as shapeError:
                    logger.warning(f"处理形状 #{shapeIndex} 时出错: {str(shapeError)}")
            
            # 如果找到并高亮了文本，强制刷新视图
            if found:
                try:
                    logger.debug("强制刷新视图以显示高亮效果")
                    self.refreshView()
                except Exception as e:
                    logger.warning(f"刷新视图失败: {str(e)}")
            
            logger.info(f"==== 文本样式高亮完成: 结果={found} ====")
            return found
            
        except Exception as e:
            logger.error(f"文本样式高亮过程中发生异常: {str(e)}")
            logger.debug("详细错误信息", exc_info=True)
            return False
    
    def clearStyleHighlights(self, slide_number: Optional[int] = None) -> bool:
        """清除文本样式高亮
        
        Args:
            slide_number: 要清除的幻灯片编号，None表示当前幻灯片
            
        Returns:
            是否成功清除
        """
        logger.info(f"==== 开始清除文本样式高亮: slide_number={slide_number} ====")
        
        if not hasattr(self, 'styleHighlights'):
            logger.info("没有文本样式高亮需要清除")
            self.styleHighlights = {}
            return True
        
        try:
            # 确定目标幻灯片
            currentSlideIndex = None
            if hasattr(self.presentation, 'SlideShowWindow'):
                currentSlideIndex = self.presentation.SlideShowWindow.View.CurrentShowPosition
            
            targetSlide = slide_number if slide_number is not None else currentSlideIndex
            logger.info(f"目标清除幻灯片: {targetSlide}")
            
            if targetSlide is None:
                logger.warning("无法确定目标幻灯片，可能未在放映状态")
                return False
            
            if targetSlide not in self.styleHighlights:
                logger.info(f"幻灯片 {targetSlide} 没有文本样式高亮需要清除")
                return True
            
            # 获取幻灯片
            slide = self.presentation.Slides(targetSlide)
            
            # 清除高亮
            for record in self.styleHighlights[targetSlide]:
                try:
                    # 查找对应形状
                    for shapeIndex in range(1, slide.Shapes.Count + 1):
                        shape = slide.Shapes(shapeIndex)
                        if shape.ID == record['shape_id']:
                            # 恢复原始样式
                            textRange = shape.TextFrame.TextRange
                            highlightRange = textRange.Characters(record['start']+1, record['length'])
                            
                            # 恢复颜色
                            highlightRange.Font.Color.RGB = record['original_style']['color']
                            
                            # 恢复加粗
                            highlightRange.Font.Bold = record['original_style']['bold']
                            
                            # 恢复下划线
                            if hasattr(highlightRange.Font, "Underline"):
                                highlightRange.Font.Underline = record['original_style']['underline']
                            
                            # 恢复字体大小
                            highlightRange.Font.Size = record['original_style']['size']
                            
                            logger.info(f"成功清除高亮: ID={record['id']}")
                            break
                except Exception as e:
                    logger.error(f"清除单个高亮失败: {str(e)}")
            
            # 清除记录
            self.styleHighlights[targetSlide] = []
            
            logger.info(f"==== 文本样式高亮清除完成 ====")
            return True
            
        except Exception as e:
            logger.error(f"清除文本样式高亮过程中发生异常: {str(e)}")
            logger.debug("详细错误信息", exc_info=True)
            return False

    def closePresentation(self) -> bool:
        """关闭当前打开的PPT，不保存修改
        
        Returns:
            是否成功关闭
        """
        try:
            if not self.presentation:
                logger.info("没有打开的PPT需要关闭")
                return True
                
            # 强制结束可能存在的幻灯片放映
            if hasattr(self.presentation, 'SlideShowWindow'):
                try:
                    self.presentation.SlideShowWindow.View.Exit()
                    time.sleep(0.5)  # 等待放映窗口关闭
                except Exception as e:
                    logger.warning(f"关闭放映窗口时出错: {str(e)}")
            
            # 关闭演示文稿，不保存修改
            try:
                # 检查演示文稿是否仍然有效
                if hasattr(self.presentation, 'Saved'):
                    # 禁用保存提示
                    if self.app:
                        self.app.DisplayAlerts = False
                    # 设置不保存修改
                    self.presentation.Saved = True
                    # 强制关闭，不保存
                    self.presentation.Close()
                    logger.info("成功关闭PPT")
                else:
                    logger.warning("演示文稿已经关闭")
            except Exception as e:
                logger.warning(f"关闭PPT时出错: {str(e)}")
                # 尝试强制关闭
                try:
                    if self.app:
                        # 确保禁用保存提示
                        self.app.DisplayAlerts = False
                        self.app.Quit()
                        logger.info("已强制退出WPS应用")
                except Exception as e2:
                    logger.error(f"强制退出WPS应用失败: {str(e2)}")
                
            # 重置状态
            self.presentation = None
            self.current_slide = 0
            
            # 确保WPS进程被关闭
            try:
                os.system('taskkill /f /im wpp.exe >nul 2>&1')
                time.sleep(0.5)  # 等待进程完全退出
            except:
                pass
                
            # 检查WPS进程是否真的关闭了
            try:
                import psutil
                for proc in psutil.process_iter(['name']):
                    if proc.info['name'] and proc.info['name'].lower() == 'wpp.exe':
                        logger.warning("WPS进程仍在运行，尝试再次强制关闭")
                        os.system('taskkill /f /im wpp.exe >nul 2>&1')
                        time.sleep(0.5)
            except:
                pass
                
            # 如果WPS已经关闭，就认为操作成功
            try:
                import psutil
                wps_running = False
                for proc in psutil.process_iter(['name']):
                    if proc.info['name'] and proc.info['name'].lower() == 'wpp.exe':
                        wps_running = True
                        break
                if not wps_running:
                    logger.info("确认WPS已完全关闭")
                    return True
            except:
                pass
                
            return True
            
        except Exception as e:
            logger.error(f"关闭PPT过程中发生异常: {str(e)}")
            # 即使发生异常，也尝试清理资源
            try:
                self.presentation = None
                self.current_slide = 0
                if self.app:
                    # 确保禁用保存提示
                    self.app.DisplayAlerts = False
                    self.app.Quit()
                os.system('taskkill /f /im wpp.exe >nul 2>&1')
                
                # 检查WPS是否真的关闭了
                try:
                    import psutil
                    wps_running = False
                    for proc in psutil.process_iter(['name']):
                        if proc.info['name'] and proc.info['name'].lower() == 'wpp.exe':
                            wps_running = True
                            break
                    if not wps_running:
                        logger.info("确认WPS已完全关闭")
                        return True
                except:
                    pass
                    
            except:
                pass
            return False