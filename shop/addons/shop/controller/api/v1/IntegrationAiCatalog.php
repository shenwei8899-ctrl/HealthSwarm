<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\CatalogService;

class IntegrationAiCatalog extends IntegrationBase
{
    protected $expectedClientType = 'agent';

    public function products()
    {
        return $this->execute(function () {
            return (new CatalogService())->listProducts($this->request->get());
        }, $this->integrationLog('ai_catalog_products', 'catalog'));
    }

    public function sku($sku_id = null)
    {
        return $this->execute(function () use ($sku_id) {
            return (new CatalogService())->getSku($sku_id, true);
        }, $this->integrationLog('ai_catalog_sku', 'sku', $sku_id));
    }

    public function alternatives($sku_id = null)
    {
        return $this->execute(function () use ($sku_id) {
            return (new CatalogService())->alternatives($sku_id, $this->request->get());
        }, $this->integrationLog('ai_catalog_alternatives', 'sku', $sku_id));
    }
}
