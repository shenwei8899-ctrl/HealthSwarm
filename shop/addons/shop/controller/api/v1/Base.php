<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\DomainException;
use addons\shop\library\v5\Identifiers;
use addons\shop\library\v5\IntegrationLogger;
use addons\shop\library\v5\Json;

class Base extends \addons\shop\controller\api\Base
{
    protected $requestId;

    public function _initialize()
    {
        parent::_initialize();
        $this->requestId = trim((string)$this->request->header('x-request-id')) ?: Identifiers::requestId();
    }

    protected function input()
    {
        $body = (string)$this->request->getContent();
        $json = Json::decode($body, null);
        return is_array($json) ? $json : $this->request->param();
    }

    protected function execute(callable $callback, array $logContext = [])
    {
        $started = microtime(true);
        try {
            $data = call_user_func($callback);
            $response = ['code' => 0, 'message' => 'success', 'request_id' => $this->requestId, 'data' => $data];
            if ($logContext) {
                IntegrationLogger::write(array_merge($logContext, [
                    'request_id' => $this->requestId, 'request_body_masked' => $this->input(),
                    'response_code' => '0', 'response_body_masked' => $response,
                    'http_status' => 200, 'duration_ms' => (int)round((microtime(true) - $started) * 1000), 'success' => 1,
                ]));
            }
            return json($response, 200);
        } catch (DomainException $e) {
            $response = ['code' => $e->getCode(), 'message' => $e->getMessage(), 'request_id' => $this->requestId, 'data' => $e->getDetails()];
            if ($logContext) {
                IntegrationLogger::write(array_merge($logContext, [
                    'request_id' => $this->requestId, 'request_body_masked' => $this->input(),
                    'response_code' => (string)$e->getCode(), 'response_body_masked' => $response,
                    'http_status' => $e->getHttpStatus(), 'duration_ms' => (int)round((microtime(true) - $started) * 1000),
                    'success' => 0, 'error_code' => (string)$e->getCode(),
                ]));
            }
            return json($response, $e->getHttpStatus());
        } catch (\Exception $e) {
            $response = ['code' => 50000, 'message' => config('app_debug') ? $e->getMessage() : '系统内部错误', 'request_id' => $this->requestId, 'data' => ['retryable' => true]];
            if ($logContext) {
                IntegrationLogger::write(array_merge($logContext, [
                    'request_id' => $this->requestId, 'request_body_masked' => $this->input(),
                    'response_code' => '50000', 'response_body_masked' => $response,
                    'http_status' => 500, 'duration_ms' => (int)round((microtime(true) - $started) * 1000),
                    'success' => 0, 'error_code' => '50000',
                ]));
            }
            return json($response, 500);
        }
    }

    protected function userId()
    {
        if (!$this->auth || !$this->auth->id) {
            throw new DomainException('请先登录', 40100, 401);
        }
        return (int)$this->auth->id;
    }

    protected function requireMethod($method)
    {
        if (strtoupper($this->request->method()) !== strtoupper($method)) {
            throw new DomainException('请求方式错误', 40500, 405);
        }
    }
}
