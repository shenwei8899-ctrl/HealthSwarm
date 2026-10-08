<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\CatalogService;
use addons\shop\library\v5\DomainException;
use think\Db;

class CommerceProduct extends Base
{
    public function categories()
    {
        return $this->execute(function () {
            $rows = \think\Db::name('shop_category')->where('status', 'normal')->where('agent_visible', 1)
                ->field('id,pid,name,nickname,image,business_category_code,weigh')->order('weigh', 'desc')->select();
            return ['items' => $rows];
        });
    }

    public function products()
    {
        return $this->execute(function () {
            $filters = $this->request->get();
            $filters['available_only'] = true;
            return (new CatalogService())->listProducts($filters);
        });
    }

    public function detail($product_id = null)
    {
        return $this->execute(function () use ($product_id) {
            $skuIds = Db::name('shop_goods_sku')->where('goods_id', (int)$product_id)->column('id');
            if (!$skuIds) {
                throw new DomainException('商品不存在', 40412, 404);
            }
            $items = [];
            foreach ($skuIds as $skuId) {
                $items[] = (new CatalogService())->getSku($skuId, true);
            }
            return ['product_id' => (string)$product_id, 'skus' => $items];
        });
    }

    public function availability($sku_id = null)
    {
        return $this->execute(function () use ($sku_id) {
            return (new CatalogService())->getSku($sku_id, true);
        });
    }

    public function alternatives($product_id = null)
    {
        return $this->execute(function () use ($product_id) {
            $skuId = (int)\think\Db::name('shop_goods_sku')->where('goods_id', (int)$product_id)->order('id', 'asc')->value('id');
            if (!$skuId) throw new \addons\shop\library\v5\DomainException('商品不存在', 40401, 404);
            return (new CatalogService())->alternatives($skuId, $this->request->get());
        });
    }
}
