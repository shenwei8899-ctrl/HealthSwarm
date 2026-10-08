<?php

namespace addons\shop\controller\api;

use addons\shop\library\service\ProductMatchService;

class Matching extends Base
{
    public function preview()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误', ['error_code' => 'SHOP_METHOD_NOT_ALLOWED'], 405);
        }
        $requirements = $this->request->post('requirements/a', []);
        $region = $this->request->post('region/a', []);
        try {
            $result = ProductMatchService::matchRequirements($requirements, $region);
        } catch (\Throwable $e) {
            $code = in_array((int)$e->getCode(), [404, 409, 422], true) ? (int)$e->getCode() : 422;
            $this->error($e->getMessage(), ['error_code' => 'SHOP_MATCH_FAILED'], $code);
        }
        $this->success('匹配成功', ['items' => $result, 'trace_id' => $this->traceId()]);
    }

    private function traceId()
    {
        $traceId = $this->request->server('HTTP_X_TRACE_ID');
        return $traceId ?: bin2hex(random_bytes(16));
    }
}

