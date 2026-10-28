"""专用最终模型生成期间，校验完整句段后公开咨询正文。"""

from yuxi.services.health_vision_types import HealthVisionError

MAX_PREFIX_CHARS = 32000


class TrustedHealthFinalAnswerStream:
    """只接受当前请求专用无工具最终调用，逐完整句段校验后公开。"""

    def __init__(self, validate, *, request_id, run_id, thread_id):
        self.validate = validate
        self.route = {"request_id": request_id, "run_id": run_id, "thread_id": thread_id}
        self.message_id = ""
        self.prefix = ""
        self.published = 0
        self.checked = 0
        self.finished = False

    async def consume(self, event: dict) -> dict | None:
        """忽略普通custom和其他执行的事件，禁止偏移缺口与中途换消息。"""
        if not isinstance(event, dict) or any(event.get(key) != value for key, value in self.route.items()):
            return None
        kind = event.get("type")
        if kind not in {"health_final_answer_start", "health_final_answer_delta", "health_final_answer_end"}:
            return None
        message_id = event.get("message_id")
        if not isinstance(message_id, str) or not message_id:
            return None
        if kind == "health_final_answer_start":
            if self.message_id and self.message_id != message_id:
                raise HealthVisionError("answer_stream_conflict", "答复流发生变化，请重新提交咨询", 409)
            self.message_id = message_id
            return None
        if not self.message_id or message_id != self.message_id or self.finished:
            return None
        offset = event.get("offset")
        if type(offset) is not int or offset < 0:
            raise HealthVisionError("answer_stream_offset", "答复流不完整，请重新提交咨询", 409)
        if kind == "health_final_answer_delta":
            text = event.get("content")
            if not isinstance(text, str) or not text:
                return None
            if offset < len(self.prefix) and self.prefix[offset : offset + len(text)] == text:
                return None
            if offset != len(self.prefix):
                raise HealthVisionError("answer_stream_offset", "答复流不完整，请重新提交咨询", 409)
            if len(self.prefix) + len(text) > MAX_PREFIX_CHARS:
                raise HealthVisionError("answer_stream_limit", "本次咨询答复过长，已停止答复预览", 422)
            self.prefix += text
            boundary = self._complete_boundary()
            if boundary - self.checked < 32:
                return None
        else:
            if offset != len(self.prefix):
                raise HealthVisionError("answer_stream_offset", "答复流不完整，请重新提交咨询", 409)
            self.finished = True
            boundary = len(self.prefix)
        if boundary <= self.published or boundary <= self.checked:
            return None
        self.checked = boundary
        try:
            await self.validate(self.prefix[:boundary])
        except HealthVisionError as error:
            if error.code == "citation_invalid":
                return None  # 引用可能在后续句段，等待完整可校验前缀。
            raise
        delta = {"content": self.prefix[self.published : boundary], "offset": self.published, "message_id": message_id}
        self.published = boundary
        return delta

    def _complete_boundary(self):
        """引用及文件名括号完整闭合后，才在句号、换行或段落末公开。"""
        stack, boundary = [], 0
        closing = {"]": "[", ")": "(", "）": "（"}
        for index, char in enumerate(self.prefix):
            if char in {"[", "(", "（"}:
                stack.append(char)
            elif char in closing and stack and stack[-1] == closing[char]:
                stack.pop()
            if not stack and char in "。！？!?\n":
                boundary = index + 1
        return boundary
