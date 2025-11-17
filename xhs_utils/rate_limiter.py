# encoding: utf-8
import time
import random
from loguru import logger


class RateLimiter:
    """
    请求频率控制器
    用于控制API请求频率，避免触发反爬机制
    """
    
    def __init__(self, min_delay=1.0, max_delay=3.0, failure_backoff=5.0):
        """
        初始化频率控制器
        
        :param min_delay: 最小延时秒数
        :param max_delay: 最大延时秒数
        :param failure_backoff: 失败后的退避延时秒数
        """
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.failure_backoff = failure_backoff
        self.last_request_time = 0
        self.consecutive_failures = 0
        
    def wait(self):
        """
        执行延时等待
        """
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        
        # 计算需要等待的时间
        if self.consecutive_failures > 0:
            # 如果有连续失败，使用退避延时
            delay = self.failure_backoff * (2 ** min(self.consecutive_failures - 1, 3))
            logger.warning(f"连续失败 {self.consecutive_failures} 次，延时 {delay:.1f} 秒")
        else:
            # 正常情况下使用随机延时
            delay = random.uniform(self.min_delay, self.max_delay)
            
        # 如果距离上次请求时间不够，需要额外等待
        if elapsed < delay:
            wait_time = delay - elapsed
            logger.info(f"频率控制：等待 {wait_time:.1f} 秒")
            time.sleep(wait_time)
            
        self.last_request_time = time.time()
        
    def on_success(self):
        """
        请求成功时调用，重置失败计数
        """
        self.consecutive_failures = 0
        
    def on_failure(self):
        """
        请求失败时调用，增加失败计数
        """
        self.consecutive_failures += 1
        logger.warning(f"请求失败，连续失败次数: {self.consecutive_failures}")


def with_rate_limit(rate_limiter):
    """
    装饰器：为函数添加频率控制
    
    :param rate_limiter: RateLimiter 实例
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            rate_limiter.wait()
            try:
                result = func(*args, **kwargs)
                # 检查结果是否成功
                if isinstance(result, tuple) and len(result) >= 2:
                    success = result[0]
                    if success:
                        rate_limiter.on_success()
                    else:
                        rate_limiter.on_failure()
                else:
                    rate_limiter.on_success()
                return result
            except Exception as e:
                rate_limiter.on_failure()
                raise e
        return wrapper
    return decorator


# 全局频率控制器实例
DEFAULT_RATE_LIMITER = RateLimiter(min_delay=1.0, max_delay=3.0)