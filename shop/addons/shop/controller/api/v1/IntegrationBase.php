<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\SignatureService;

class IntegrationBase extends Base
{
    protected $noNeedLogin = ['*'];
    protected $integrationClient;
    protected $expectedClientType = '';

    public function _initialize()
    {
        parent::_initialize();
    }

    protected function clientId()
    {
        $this->authenticateIntegrationClient();
        return $this->integrationClient['client_id'];
    }

    protected function authenticateIntegrationClient()
    {
        if (!$this->integrationClient) {
            $this->integrationClient = (new SignatureService())->authenticate($this->request, $this->expectedClientType);
        }
        return $this->integrationClient;
    }

    protected function execute(callable $callback, array $logContext = [])
    {
        return parent::execute(function () use ($callback) {
            $this->authenticateIntegrationClient();
            return call_user_func($callback);
        }, $logContext);
    }

    protected function integrationLog($interface, $businessType = '', $businessRef = '')
    {
        return [
            'partner_type' => $this->expectedClientType ?: 'integration',
            'partner_code' => trim((string)$this->request->header('x-client-id')),
            'direction' => 'inbound', 'interface_name' => $interface,
            'method' => $this->request->method(), 'url_path' => SignatureService::normalizePath($this->request->url()),
            'business_type' => $businessType, 'business_ref' => $businessRef,
        ];
    }
}
