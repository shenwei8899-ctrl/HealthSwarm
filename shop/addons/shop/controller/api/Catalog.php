<?php

namespace addons\shop\controller\api;

use addons\shop\library\service\CatalogQueryService;
use think\Db;

class Catalog extends Base
{
    protected $noNeedLogin = ['index', 'detail', 'availability', 'substitutes'];

    public function index()
    {
        try {
            $result = CatalogQueryService::listGoods([
                'page' => $this->request->get('page/d', 1),
                'page_size' => $this->request->get('page_size/d', 20),
                'keyword' => $this->request->get('keyword', ''),
                'category_id' => $this->request->get('category_id/d', 0),
            ]);
        } catch (\Throwable $e) {
            $this->fail($e, 'SHOP_GOODS_QUERY_FAILED');
        }
        $this->success('获取成功', $result);
    }

    public function detail()
    {
        try {
            $result = CatalogQueryService::detail(
                $this->request->param('id/d'),
                $this->request->get('region/a', [])
            );
        } catch (\Throwable $e) {
            $this->fail($e, 'SHOP_GOODS_NOT_FOUND');
        }
        $this->success('获取成功', $result);
    }

    public function availability()
    {
        $skuId = $this->request->param('id/d', 0);
        $goodsId = $this->request->get('goods_id/d', 0);
        if (!$goodsId && $skuId) {
            $goodsId = (int)Db::name('shop_goods_sku')->where('id', $skuId)->value('goods_id');
        }
        if (!$goodsId) {
            $this->error('商品 ID 缺失', ['error_code' => 'SHOP_GOODS_ID_REQUIRED'], 422);
        }
        try {
            $result = CatalogQueryService::availability(
                $goodsId,
                $skuId,
                $this->request->get('quantity/d', 1),
                $this->request->get('region/a', [])
            );
        } catch (\Throwable $e) {
            $this->fail($e, 'SHOP_AVAILABILITY_QUERY_FAILED');
        }
        $this->success('获取成功', $result);
    }

    public function substitutes()
    {
        $skuId = $this->request->param('id/d', 0);
        $goodsId = $this->request->get('goods_id/d', 0);
        if (!$goodsId && $skuId) {
            $goodsId = (int)Db::name('shop_goods_sku')->where('id', $skuId)->value('goods_id');
        }
        if (!$goodsId) {
            $this->error('商品 ID 缺失', ['error_code' => 'SHOP_GOODS_ID_REQUIRED'], 422);
        }
        try {
            $result = CatalogQueryService::substitutes(
                $goodsId,
                $skuId,
                $this->request->get('region/a', [])
            );
        } catch (\Throwable $e) {
            $this->fail($e, 'SHOP_SUBSTITUTE_QUERY_FAILED');
        }
        $this->success('获取成功', ['items' => $result]);
    }

    private function fail(\Throwable $e, $errorCode)
    {
        $code = in_array((int)$e->getCode(), [403, 404, 409, 422], true) ? (int)$e->getCode() : 422;
        $this->error($e->getMessage(), ['error_code' => $errorCode], $code);
    }
}
