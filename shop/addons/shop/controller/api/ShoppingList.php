<?php

namespace addons\shop\controller\api;

use addons\shop\library\service\ShoppingListService;

class ShoppingList extends Base
{
    public function collection()
    {
        if ($this->request->isGet()) {
            try {
                $result = ShoppingListService::listForUser(
                    $this->auth->id,
                    $this->request->get('page/d', 1),
                    $this->request->get('page_size/d', 20)
                );
            } catch (\Throwable $e) {
                $this->fail($e, 'SHOP_LIST_QUERY_FAILED');
            }
            $this->success('获取成功', $result);
        }
        return $this->create();
    }

    public function create()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误', ['error_code' => 'SHOP_METHOD_NOT_ALLOWED'], 405);
        }
        try {
            $result = ShoppingListService::create(
                $this->auth->id,
                $this->request->post('menu_version_id', ''),
                $this->request->post('shopping_list_version/d', 1),
                $this->request->post('items/a', [])
            );
        } catch (\Throwable $e) {
            $this->fail($e, 'SHOP_LIST_CREATE_FAILED');
        }
        $this->success('购物清单创建成功', $result);
    }

    public function detail()
    {
        try {
            $result = ShoppingListService::detail(
                $this->request->param('id/d'),
                $this->auth->id
            );
        } catch (\Throwable $e) {
            $this->fail($e, 'SHOP_LIST_NOT_FOUND');
        }
        $this->success('获取成功', $result);
    }

    public function updateItem()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误', ['error_code' => 'SHOP_METHOD_NOT_ALLOWED'], 405);
        }
        try {
            $result = ShoppingListService::updateItem(
                $this->request->param('id/d'),
                $this->request->param('item_id/d'),
                $this->auth->id,
                $this->request->param('changes/a', [])
            );
        } catch (\Throwable $e) {
            $this->fail($e, 'SHOP_LIST_UPDATE_FAILED');
        }
        $this->success('购物清单更新成功', $result);
    }

    public function confirm()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误', ['error_code' => 'SHOP_METHOD_NOT_ALLOWED'], 405);
        }
        try {
            $result = ShoppingListService::confirm(
                $this->request->param('id/d'),
                $this->auth->id
            );
        } catch (\Throwable $e) {
            $this->fail($e, 'SHOP_LIST_CONFIRM_FAILED');
        }
        $this->success('购物清单确认成功', $result);
    }

    private function fail(\Throwable $e, $errorCode)
    {
        $code = in_array((int)$e->getCode(), [404, 409, 422], true) ? (int)$e->getCode() : 422;
        $this->error($e->getMessage(), ['error_code' => $errorCode], $code);
    }
}
