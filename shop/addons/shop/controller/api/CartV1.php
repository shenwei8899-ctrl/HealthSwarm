<?php

namespace addons\shop\controller\api;

use addons\shop\library\service\CartService;

class CartV1 extends Base
{
    public function collection()
    {
        if ($this->request->isGet()) {
            try {
                $result = CartService::listing(
                    $this->auth->id,
                    $this->request->get('ids/a', []),
                    $this->request->get('sceneval/d', 1)
                );
            } catch (\Throwable $e) {
                $this->fail($e, 'SHOP_CART_QUERY_FAILED');
            }
            $this->success('获取成功', ['items' => $result]);
        }
        if (!$this->request->isPost()) {
            $this->error('请求方式错误', ['error_code' => 'SHOP_METHOD_NOT_ALLOWED'], 405);
        }
        try {
            $shoppingListId = $this->request->post('shopping_list_id/d', 0);
            if ($shoppingListId) {
                $result = CartService::addConfirmedShoppingList(
                    $this->auth->id,
                    $shoppingListId,
                    $this->request->post('shopping_list_version/d', 0)
                );
            } else {
                $cartId = CartService::addItem(
                    $this->auth->id,
                    $this->request->post('goods_id/d'),
                    $this->request->post('goods_sku_id/d', 0),
                    $this->request->post('quantity/d', $this->request->post('nums/d', 1)),
                    $this->request->post('sceneval/d', 1)
                );
                $result = [CartService::detail($this->auth->id, $cartId)];
            }
        } catch (\Throwable $e) {
            $this->fail($e, 'SHOP_CART_ADD_FAILED');
        }
        $this->success('加入购物车成功', ['items' => $result]);
    }

    public function item()
    {
        $cartId = $this->request->param('id/d');
        try {
            if ($this->request->isDelete()) {
                CartService::remove($this->auth->id, [$cartId]);
                $this->success('删除成功');
            }
            if (!$this->request->isPatch() && !$this->request->isPut() && !$this->request->isPost()) {
                $this->error('请求方式错误', ['error_code' => 'SHOP_METHOD_NOT_ALLOWED'], 405);
            }
            $result = CartService::updateQuantity(
                $this->auth->id,
                $cartId,
                $this->request->param('quantity/d', $this->request->param('nums/d'))
            );
        } catch (\Throwable $e) {
            $this->fail($e, 'SHOP_CART_UPDATE_FAILED');
        }
        $this->success('更新成功', $result);
    }

    private function fail(\Throwable $e, $errorCode)
    {
        $code = in_array((int)$e->getCode(), [404, 409, 422], true) ? (int)$e->getCode() : 422;
        $this->error($e->getMessage(), ['error_code' => $errorCode], $code);
    }
}
