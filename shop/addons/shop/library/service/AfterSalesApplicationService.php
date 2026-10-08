<?php

namespace addons\shop\library\service;

use addons\shop\model\OrderGoods;
use RuntimeException;
use think\Db;

class AfterSalesApplicationService
{
    public static function create($orderGoodsId, $userId, $type, $quantity, $reason = '', $images = '')
    {
        $orderGoodsId = (int)$orderGoodsId;
        $userId = (int)$userId;
        $type = (int)$type;
        $quantity = filter_var($quantity, FILTER_VALIDATE_INT);
        $reason = trim((string)$reason);

        if ($orderGoodsId <= 0 || $userId <= 0) {
            throw new RuntimeException('售后申请参数缺失');
        }
        if (!in_array($type, [1, 2], true)) {
            throw new RuntimeException('不存在的售后类型');
        }
        if ($quantity === false || $quantity <= 0) {
            throw new RuntimeException('售后数量必须是正整数');
        }
        if ($type !== 1 && $reason === '') {
            throw new RuntimeException('请输入售后原因');
        }
        if ($reason === '') {
            $reason = '仅退款';
        }

        Db::startTrans();
        try {
            $goods = Db::name('shop_order_goods')->where('id', $orderGoodsId)->lock(true)->find();
            if (!$goods) {
                throw new RuntimeException('订单商品不存在', 404);
            }
            $order = Db::name('shop_order')->where('order_sn', $goods['order_sn'])->lock(true)->find();
            if (!$order) {
                throw new RuntimeException('订单不存在', 404);
            }
            if ((int)$order['user_id'] !== $userId) {
                throw new RuntimeException('不可越权操作', 403);
            }
            if (!in_array((int)$order['orderstate'], [0, 3, 4], true) || (int)$order['paystate'] !== 1) {
                throw new RuntimeException('当前订单状态不允许申请售后', 409);
            }
            if ($type === 2 && (int)$order['shippingstate'] === 0) {
                throw new RuntimeException('未发货订单不能申请退货退款', 409);
            }
            if (!in_array((int)$goods['salestate'], [0, 6], true)) {
                throw new RuntimeException('存在尚未完成的售后申请', 409);
            }
            $pending = Db::name('shop_order_aftersales')
                ->where('order_goods_id', $orderGoodsId)
                ->where('status', 1)
                ->lock(true)
                ->find();
            if ($pending) {
                throw new RuntimeException('存在尚未审核的售后申请', 409);
            }

            $goodsExtension = Db::name('shop_order_goods_ext')
                ->where('order_goods_id', $orderGoodsId)
                ->lock(true)
                ->find();
            $availableQuantity = (int)$goods['nums'];
            if ($goodsExtension) {
                $availableQuantity -= (int)$goodsExtension['refunded_quantity'];
            }
            if ($quantity > $availableQuantity) {
                throw new RuntimeException('售后数量超过剩余可退数量', 409);
            }
            if (!$goodsExtension && $quantity !== (int)$goods['nums']) {
                throw new RuntimeException('历史订单仅支持整行商品售后', 409);
            }

            $goodsModel = OrderGoods::get($orderGoodsId, ['Order']);
            $realPrice = $goodsModel->getAvailableRefundRealprice($quantity);
            $shippingFee = $goodsModel->getAvailableRefundShippingfee($quantity);
            $refundAmount = bcadd($realPrice, $shippingFee, 2);
            $now = time();
            Db::name('shop_order_goods')->where('id', $orderGoodsId)->update([
                'salestate' => $type === 1 ? 2 : 1,
            ]);
            Db::name('shop_order')->where('id', (int)$order['id'])->update([
                'orderstate' => 4,
                'updatetime' => $now,
            ]);
            $aftersalesId = Db::name('shop_order_aftersales')->insertGetId([
                'user_id' => $userId,
                'order_id' => (int)$order['id'],
                'order_goods_id' => $orderGoodsId,
                'type' => $type,
                'nums' => (int)$quantity,
                'reason' => $reason,
                'realprice' => $realPrice,
                'shippingfee' => $shippingFee,
                'refund' => $refundAmount,
                'images' => trim((string)$images),
                'status' => 1,
                'createtime' => $now,
                'updatetime' => $now,
            ]);
            Db::commit();

            return [
                'aftersales_id' => (int)$aftersalesId,
                'order_id' => (int)$order['id'],
                'order_sn' => $order['order_sn'],
                'quantity' => (int)$quantity,
                'realprice' => $realPrice,
                'shippingfee' => $shippingFee,
                'refund' => $refundAmount,
            ];
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }
}
