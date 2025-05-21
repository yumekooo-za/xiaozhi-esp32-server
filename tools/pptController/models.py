"""
PPT控制服务数据模型
包含错误码和API响应结构
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

class PPTErrorCode(Enum):
    """PPT控制错误码"""
    SUCCESS = 0
    CONNECTION_FAILED = 1001
    INVALID_COMMAND = 1002
    FILE_NOT_FOUND = 1003
    SLIDE_OUT_OF_RANGE = 1004
    UNKNOWN_ERROR = 9999

@dataclass
class APIResponse:
    """API响应数据结构"""
    status: bool
    code: PPTErrorCode
    message: str
    data: Optional[Dict] = None 