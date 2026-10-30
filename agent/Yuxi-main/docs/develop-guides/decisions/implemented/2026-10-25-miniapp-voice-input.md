# 小程序短语音转写与请求重放

状态：implemented
类型：feature
Owner：backend/package/yuxi/services/health_voice_service.py

## 问题

聊天输入需要把用户主动录制的短音频转成文字，再进入既有健康聊天流程。设备录音授权不代表语音识别服务已配置，模型对话接口也不拥有音频解码能力。

## 决策

### 实现方案

微信端录制16kHz、单声道、16位PCM，松手上传，成功后把文字交给原聊天发送入口；上移取消不上传。小程序原生布局容器拥有语音区域的剩余宽度，避免自定义组件宿主不参与flex拉伸。

后端独立语音路由复用业务JWT认证，以当前用户为音频访问边界。服务校验实际字节长度、格式元数据及请求键，调用腾讯云一句话识别。原始音频不写业务数据库或对象存储；multipart临时文件在请求结束时关闭。结果以用户、请求键和音频摘要绑定，在Redis保留五分钟用于响应丢失后的重放，并使用短租约阻止并发重复调用。原请求键更换音频返回冲突。

此能力默认关闭。API进程读取`HEALTH_ASR_ENABLED`、`HEALTH_ASR_SECRET_ID`、`HEALTH_ASR_SECRET_KEY`和`HEALTH_ASR_REGION`，不读取客户端传入的密钥或供应商URL。启用值为`1`，地区默认`ap-shanghai`，凭据通过部署环境注入。健康档案的授权和聊天同意仍由原健康任务链路执行。

## 替代方案

微信插件可以减少后端接入工作，但会更换当前录音控制和事件来源。实时WebSocket转写适合边说边显示，对松手发送的短输入增加连接维护成本。同步短音频接口符合当前交互且沿用现有录音控制。

## 后果

录音在客户端失败时短期保留以供手动重试；成功、放弃、离开页面或五分钟到期后清理已保存文件。取消会中止客户端上传并忽略迟到结果；供应商已经接收的处理不能保证被取消。Redis不可用时不启动转写，服务未配置时明确返回未就绪。

五分钟缓存不是永久幂等账本。供应商成功但缓存写入失败、进程崩溃或缓存过期后再提交可能再次计费；系统不承诺供应商调用恰好一次。限流按用户每分钟最多十次新识别。日志不记录音频、完整转写或密钥。

部署需要腾讯云ASR服务和可调用`SentenceRecognition`的凭据、微信录音隐私声明及HTTPS上传合法域名。提供方会收到音频，隐私说明需覆盖处理方和用途。此决定的代码实现不等于已部署、已开通服务或已完成真机验收。

## 验证

服务单测覆盖格式、声道、时长、供应商编码和错误映射。HTTP集成使用真实TCP、生产JWT验证、隔离PostgreSQL及Redis，覆盖身份失效、账号隔离、结果重放、并发、限流和文件上限；付费ASR用合成响应替换。真实转写质量、微信录音格式和授权行为需要在服务开通后做iOS、Android真机验证。

源码入口：[语音服务](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/package/yuxi/services/health_voice_service.py)、[HTTP路由](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/server/routers/health_voice_router.py)、[HTTP集成测试](https://github.com/shenwei8899-ctrl/HealthSwarm/blob/main/agent/Yuxi-main/backend/test/integration/api/test_health_voice_http.py)。
