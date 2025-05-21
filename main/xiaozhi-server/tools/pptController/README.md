# PPT演示控制服务

## 部署步骤

1. **环境要求**
   - Windows操作系统
   - Python 3.9+
   - WPS Office
   - 管理员权限

2. **安装依赖**
```bash
pip install fastapi uvicorn websockets pywin32 psutil
```

3. **启动服务**
```bash
# 启动所有服务（HTTP + WebSocket）
python server/server.py

# 仅启动HTTP服务
python server/server.py --mode http

# 仅启动WebSocket服务
python server/server.py --mode ws

# 自定义端口
python server/server.py --http-port 8080 --ws-port 8765
```

## 接口说明

### HTTP接口

#### 1. 打开PPT
```http
POST /api/ppt/open
Content-Type: application/json

{
    "filepath": "C:/path/to/your/presentation.pptx"
}
```
- 功能：打开指定的PPT文件
- 实现：通过WPS COM接口打开文件，自动设置窗口焦点
- 返回：成功时返回幻灯片数量

#### 2. 开始放映
```http
POST /api/ppt/start
```
- 功能：开始PPT放映
- 实现：调用WPS的SlideShowSettings.Run()方法
- 返回：放映状态

#### 3. 下一页
```http
POST /api/ppt/next
```
- 功能：切换到下一页
- 实现：通过SlideShowWindow.View.GotoSlide()方法
- 返回：操作状态

#### 4. 上一页
```http
POST /api/ppt/prev
```
- 功能：切换到上一页
- 实现：通过SlideShowWindow.View.GotoSlide()方法
- 返回：操作状态

#### 5. 跳转到指定页
```http
POST /api/ppt/goto
Content-Type: application/json

{
    "slide": 3
}
```
- 功能：跳转到指定页码
- 实现：通过SlideShowWindow.View.GotoSlide()方法
- 返回：操作状态

#### 6. 结束放映
```http
POST /api/ppt/stop
```
- 功能：结束PPT放映
- 实现：调用SlideShowWindow.View.Exit()方法
- 返回：操作状态

#### 7. 获取状态
```http
GET /api/ppt/status
```
- 功能：获取当前PPT状态
- 实现：检查WPS进程状态和幻灯片信息
- 返回：
```json
{
    "is_ready": true,
    "current_slide": 1,
    "slide_count": 10
}
```

#### 8. 文本高亮
```http
POST /api/ppt/styleHighlight
Content-Type: application/json

{
    "text": "要高亮的文本",
    "color": [255, 0, 0]  // RGB颜色，可选
}
```
- 功能：高亮指定文本
- 实现：修改文本样式（颜色、加粗、大小）
- 返回：操作状态

#### 9. 清除高亮
```http
POST /api/ppt/clearStyleHighlights?slide=3  // slide参数可选
```
- 功能：清除文本高亮
- 实现：恢复原始文本样式
- 返回：操作状态

#### 10. 关闭PPT
```http
POST /api/ppt/close
```
- 功能：关闭当前PPT
- 实现：关闭WPS进程，清理资源
- 返回：操作状态

### WebSocket接口

WebSocket服务器支持以下命令格式：
```json
{
    "action": "命令类型",
    "data": {
        // 命令参数
    }
}
```

#### 1. 打开PPT
```json
{
    "action": "open",
    "data": {
        "filepath": "C:/path/to/your/presentation.pptx"
    }
}
```

#### 2. 控制命令
```json
{
    "action": "control",
    "data": {
        "command": "start|next|prev"
    }
}
```

#### 3. 跳转页面
```json
{
    "action": "goto",
    "data": {
        "slide": 3
    }
}
```

#### 4. 获取状态
```json
{
    "action": "status"
}
```

#### 5. 结束放映
```json
{
    "action": "endShow"
}
```

#### 6. 刷新视图
```json
{
    "action": "refresh"
}
```

#### 7. 文本高亮
```json
{
    "action": "styleHighlight",
    "data": {
        "text": "要高亮的文本",
        "color": [255, 0, 0]  // 可选
    }
}
```

#### 8. 清除高亮
```json
{
    "action": "clearStyleHighlights",
    "data": {
        "slide": 3  // 可选
    }
}
```

## 错误码说明

- 0: 成功
- 1001: 连接失败
- 1002: 无效命令
- 1003: 文件未找到
- 1004: 幻灯片超出范围
- 9999: 未知错误

## 注意事项

1. 确保WPS Office已正确安装
2. 服务需要管理员权限才能控制WPS
3. 关闭PPT时会自动保存更改
4. 建议使用HTTP接口`/api/server/shutdown`来优雅地关闭服务
5. 注意检查临时文件清理是否成功
6. 监控WPS进程状态
7. 定期检查日志文件大小
