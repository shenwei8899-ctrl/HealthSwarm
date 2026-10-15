<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\CatalogService;
use addons\shop\library\v5\DomainException;
use think\Db;

class CommerceProduct extends Base
{
    protected $noNeedLogin = ['*'];
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
        $product_id = $product_id ?? $this->request->route('product_id');
        return $this->execute(function () use ($product_id) {
            $this->publicProduct($product_id);
            $skuIds = Db::name('shop_goods_sku')->where('goods_id', (int)$product_id)->column('id');
            if (!$skuIds) {
                throw new DomainException('商品不存在', 40412, 404);
            }
            $items = [];
            foreach ($skuIds as $skuId) {
                $items[] = (new CatalogService())->getSku($skuId, true);
            }
            $goods = Db::name('shop_goods')->where('id', (int)$product_id)->field('title,content')->find();
            return ['product_id' => (string)$product_id, 'product_name' => $goods['title'], 'description' => strip_tags((string)($goods['content'] ?? '')), 'skus' => $items];
        });
    }

    public function availability($sku_id = null)
    {
        $sku_id = $sku_id ?? $this->request->route('sku_id');
        return $this->execute(function () use ($sku_id) {
            $productId = Db::name('shop_goods_sku')->where('id', (int)$sku_id)->value('goods_id');
            $this->publicProduct($productId);
            return (new CatalogService())->getSku($sku_id, true);
        });
    }

    public function alternatives($product_id = null)
    {
        $product_id = $product_id ?? $this->request->route('product_id');
        return $this->execute(function () use ($product_id) {
            $this->publicProduct($product_id);
            $skuId = (int)\think\Db::name('shop_goods_sku')->where('goods_id', (int)$product_id)->order('id', 'asc')->value('id');
            if (!$skuId) throw new \addons\shop\library\v5\DomainException('商品不存在', 40401, 404);
            return (new CatalogService())->alternatives($skuId, $this->request->get());
        });
    }

    private function publicProduct($id)
    {
        if (!Db::name('shop_goods')->where('id', (int)$id)->where('status', 'normal')
            ->where('catalog_status', 'published')->where('agent_visible', 1)->find()) {
            throw new DomainException('商品不存在或已下架', 40412, 404);
        }
    }
}
