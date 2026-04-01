"""统一响应格式封装 - 适配美团NoCode前端"""
from typing import Any, Optional


def success_response(data: Any, msg: str = "success") -> dict:
    """
    成功响应格式
    :param data: 响应数据
    :param msg: 提示信息
    :return: 标准响应字典
    """
    return {
        "code": 200,
        "msg": msg,
        "data": data
    }


def error_response(
    code: int,
    msg: str,
    data: Optional[Any] = None
) -> dict:
    """
    错误响应格式
    :param code: 错误码（400参数错误/500服务异常/503第三方API故障）
    :param msg: 错误提示
    :param data: 附加数据（可选）
    :return: 标准错误响应字典
    """
    response = {
        "code": code,
        "msg": msg
    }
    if data is not None:
        response["data"] = data
    return response
