"""已登录用户的短语音输入接口。"""

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.routing import APIRoute

from server.utils.auth_middleware import get_required_user
from yuxi.services import health_voice_service as service
from yuxi.storage.postgres.models_business import User


async def private_response(response: Response):
    """语音及转写结果禁止公共缓存。"""
    response.headers["Cache-Control"] = "no-store"


class VoiceRoute(APIRoute):
    """在multipart解析前限制请求大小，避免无限制临时文件写入。"""

    def get_route_handler(self):
        """录音上传仅接受有长度上限的普通multipart请求。"""
        handler = super().get_route_handler()

        async def bounded(request: Request):
            """先验证传输边界，再交给认证和业务处理。"""
            if request.method == "POST":
                length = request.headers.get("content-length", "")
                if not length.isdecimal() or request.headers.get("transfer-encoding"):
                    raise HTTPException(
                        411, detail={"code": "VOICE_LENGTH_REQUIRED", "message": "录音上传须声明文件长度"}
                    )
                if int(length) > service.MAX_AUDIO_BYTES + 16384:
                    raise HTTPException(
                        413, detail={"code": "VOICE_SIZE_INVALID", "message": "录音文件过大，请重新录音"}
                    )
            return await handler(request)

        return bounded


health_voice = APIRouter(
    prefix="/health/v1/voice",
    tags=["health-voice"],
    route_class=VoiceRoute,
    dependencies=[Depends(private_response)],
)


@health_voice.get("/configuration")
async def configuration(user: User = Depends(get_required_user)):
    """返回当前转写能力，不公开供应商密钥。"""
    return service.configuration()


@health_voice.post("/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    client_request_id: str = Form(..., min_length=8, max_length=100),
    format: str = Form(...),
    sample_rate: int = Form(...),
    channels: int = Form(...),
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_required_user),
):
    """有限额地读取音频并将认证身份交给转写服务。"""
    try:
        if request_key != client_request_id:
            raise service.VoiceError("VOICE_REQUEST_INVALID", "语音请求标识不一致")
        data = await file.read(service.MAX_AUDIO_BYTES + 1)
        return await service.transcribe(user.uid, client_request_id, data, format, sample_rate, channels)
    except service.VoiceError as error:
        raise HTTPException(
            error.status, detail={"code": error.code, "message": error.message}, headers={"Cache-Control": "no-store"}
        ) from error
    finally:
        await file.close()
