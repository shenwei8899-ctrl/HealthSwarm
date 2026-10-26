<?php

namespace addons\shop\library\v5;

use think\Db;

class DeliveryService
{
    public function reserveSlot($orderSn, $slotId, $areaId = null)
    {
        if (!$slotId) return;
        $slot=Db::name('shop_delivery_slot')->where('id',$slotId)->lock(true)->find();
        if (!$slot || ($slot['service_scope'] ?? 'normal')!=='normal' || $slot['status'] !== 'normal' || ($areaId !== null && (int)$slot['area_id'] !== (int)$areaId)) {
            throw new DomainException('配送时段不可用，请重新结算',40915,409);
        }
        if ((int)$slot['capacity']>0 && (int)$slot['used_capacity']>=(int)$slot['capacity']) throw new DomainException('配送时段容量已满',40916,409);
        Db::name('shop_slot_reservation')->insert(['order_sn'=>$orderSn,'slot_id'=>$slotId,'status'=>'active']);
        Db::name('shop_delivery_slot')->where('id',$slotId)->setInc('used_capacity');
    }

    public function releaseSlot($orderSn)
    {
        Db::startTrans();
        try {
            $reservation=Db::name('shop_slot_reservation')->where('order_sn',$orderSn)->lock(true)->find();
            if ($reservation && $reservation['status']==='active') {
                Db::name('shop_delivery_slot')->where('id',$reservation['slot_id'])->where('used_capacity','>',0)->setDec('used_capacity');
                Db::name('shop_slot_reservation')->where('order_sn',$orderSn)->update(['status'=>'released']);
            }
            Db::commit();
        } catch (\Throwable $e) { Db::rollback(); throw $e; }
    }

    /** Called inside checkout's transaction; prevent rule inserts/updates until order commit. */
    public function lockRules()
    {
        if (strtolower((string)config('database.type')) === 'pgsql') {
            $table = str_replace('"', '""', config('database.prefix') . 'shop_delivery_area');
            Db::execute('LOCK TABLE "' . $table . '" IN SHARE MODE');
        }
    }

    public function validateAddress($userId, $addressId, $slotId = 0, $lock = false)
    {
        $address = Db::name('shop_address')->where('id', (int)$addressId)->where('user_id', (int)$userId)->where('status', 'normal')->whereNull('deletetime')->lock($lock)->find();
        if (!$address) {
            throw new DomainException('收货地址不存在', 40407, 404);
        }
        $districtCode = (string)Db::name('shop_area')->where('id', $address['area_id'])->value('adcode');
        $cityCode = (string)Db::name('shop_area')->where('id', $address['city_id'])->value('adcode');
        $provinceCode = (string)Db::name('shop_area')->where('id', $address['province_id'])->value('adcode');
        // A disabled specific rule must not fall back to broader nationwide coverage.
        $area = Db::name('shop_delivery_area')->where('status', 'in', ['normal', 'hidden'])->where(function ($query) use ($districtCode, $cityCode, $provinceCode) {
            $query->where('district_code', $districtCode)
                ->whereOr(function ($query) use ($cityCode) {
                    $query->where('district_code', '')->where('city_code', $cityCode);
                })->whereOr(function ($query) use ($provinceCode) {
                    $query->where('district_code', '')->where('city_code', '')->where('province_code', $provinceCode);
                });
        })->order('supplier_id asc,district_code desc,city_code desc,province_code desc,id desc')->find();
        if (!$area) {
            $configured = (int)Db::name('shop_delivery_area')->count() > 0;
            throw new DomainException($configured ? '当前地址不在配送范围，请更换收货地址' : '商城尚未配置配送区域，请联系商家', 40914, 409, [
                'area_id' => (string)$address['area_id'],
                'reason_code' => $configured ? 'address_out_of_range' : 'delivery_not_configured',
            ]);
        }
        if ($area['status'] !== 'normal') {
            throw new DomainException('当前地区已暂停配送，请更换收货地址', 40914, 409, [
                'area_id' => (string)$address['area_id'], 'reason_code' => 'area_disabled',
            ]);
        }
        $slot = null;
        if ($slotId) {
            $slot = Db::name('shop_delivery_slot')->where('id', (int)$slotId)->where('area_id', $area['id'])->where('status', 'normal')->lock($lock)->find();
            if (!$slot) {
                throw new DomainException('配送时段不可用', 40915, 409);
            }
            if ((int)$slot['capacity'] > 0 && (int)$slot['used_capacity'] >= (int)$slot['capacity']) {
                throw new DomainException('配送时段容量已满', 40916, 409);
            }
        }
        return [
            'address' => $address,
            'area' => $area,
            'slot' => $slot,
            'snapshot' => [
                'address_id' => (string)$address['id'], 'receiver' => $address['receiver'],
                'mobile' => $address['mobile'], 'province_id' => (string)$address['province_id'],
                'city_id' => (string)$address['city_id'], 'area_id' => (string)$address['area_id'],
                'province_code' => $provinceCode, 'city_code' => $cityCode, 'district_code' => $districtCode,
                'region' => (new AddressService())->format($address)['region'],
                'detail' => $address['address'], 'zipcode' => $address['zipcode'],
            ],
        ];
    }

    /** Read-only eligibility; checkout still uses validateAddress and rejects unsupported areas. */
    public function availability($userId, $addressId, $slotId = 0)
    {
        try {
            $delivery = $this->validateAddress($userId, $addressId, $slotId);
            return ['supported' => true, 'reason_code' => '', 'message' => '当前地址支持配送',
                'area' => $delivery['area'], 'slot' => $delivery['slot'], 'address' => $delivery['snapshot'], 'failed_items' => []];
        } catch (DomainException $e) {
            if ($e->getCode() !== 40914) throw $e;
            $details = $e->getDetails();
            return ['supported' => false, 'reason_code' => $details['reason_code'] ?? 'address_out_of_range',
                'message' => $e->getMessage(), 'area' => null, 'slot' => null, 'failed_items' => []];
        }
    }
}
