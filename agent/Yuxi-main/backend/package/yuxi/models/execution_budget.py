"""为当前模型执行作用域限制新SDK实例，不修改共享模型。"""

import time
from contextvars import ContextVar, Token

_MODEL_EXECUTION_DEADLINE: ContextVar[float | None] = ContextVar("model_execution_deadline", default=None)


class ModelExecutionBudgetExceeded(Exception):
    """模型加载时当前执行作用域已经耗尽。"""


def bind_model_execution_deadline(deadline: float) -> Token[float | None]:
    """绑定当前执行的monotonic截止点，供新模型实例读取。"""
    return _MODEL_EXECUTION_DEADLINE.set(deadline)


def reset_model_execution_deadline(token: Token[float | None]) -> None:
    """恢复调用前的模型执行作用域。"""
    _MODEL_EXECUTION_DEADLINE.reset(token)


def model_execution_budget_options() -> dict[str, float | int]:
    """剩余时间限制新SDK实例，未绑定的调用维持原参数。"""
    deadline = _MODEL_EXECUTION_DEADLINE.get()
    if deadline is None:
        return {}
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ModelExecutionBudgetExceeded("健康Agent执行预算已耗尽")
    return {"timeout": remaining, "max_retries": 0}
