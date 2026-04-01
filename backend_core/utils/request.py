"""异步HTTP请求封装 - 支持超时/重试/指数退避"""
import asyncio
import logging
from typing import Any, Optional, Dict
import aiohttp
from config.settings import settings

logger = logging.getLogger(__name__)


class AsyncHttpClient:
    """异步HTTP客户端 - 带重试和超时机制"""

    def __init__(
        self,
        timeout: int = settings.REQUEST_TIMEOUT,
        max_retries: int = settings.REQUEST_RETRY,
        base_delay: float = settings.RETRY_BASE_DELAY
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_delay = base_delay

    async def post(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        异步POST请求（带重试和指数退避）
        :param url: 请求URL
        :param headers: 请求头
        :param json_data: JSON数据
        :return: 响应JSON数据
        """
        attempt = 0
        last_exception = None

        while attempt < self.max_retries:
            try:
                timeout_config = aiohttp.ClientTimeout(total=self.timeout)

                async with aiohttp.ClientSession(timeout=timeout_config) as session:
                    async with session.post(
                        url,
                        headers=headers,
                        json=json_data,
                        **kwargs
                    ) as response:
                        # 记录请求日志
                        logger.info(
                            f"HTTP POST {url} | Status: {response.status} | Attempt: {attempt + 1}"
                        )

                        # 检查HTTP状态码
                        if response.status >= 500:
                            # 服务器错误，需要重试
                            error_text = await response.text()
                            raise aiohttp.ClientError(
                                f"Server error {response.status}: {error_text}"
                            )

                        # 返回JSON响应
                        response.raise_for_status()
                        return await response.json()

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exception = e
                attempt += 1

                if attempt < self.max_retries:
                    # 指数退避延迟
                    delay = self.base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        f"Request failed (attempt {attempt}/{self.max_retries}): {str(e)}, "
                        f"retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Request failed after {self.max_retries} attempts: {str(e)}"
                    )

        # 所有重试失败，抛出异常
        raise last_exception or Exception("Request failed with unknown error")


# 创建全局客户端实例
http_client = AsyncHttpClient()
