<?php

namespace addons\shop\library\v5;

use think\Db;

class DeliveryService
{
    public function validateAddress($userId, $addressId, $slotId = 0)
    {
        $address = Db::name('shop_address')->where('id', (int)$addressId)->where('user_id', (int)$userId)->find();
        if (!$address) {
            throw new DomainException('收货地址不存在', 40407, 404);
        }
        $districtCode = (string)Db::name('shop_area')->where('id', $address['area_id'])->value('adcode');
        $cityCode = (string)Db::name('shop_area')->where('id', $address['city_id'])->value('adcode');
        $provinceCode = (string)Db::name('shop_area')->where('id', $address['province_id'])->value('adcode');
        $area = Db::name('shop_delivery_area')->where('status', 'normal')->where(function ($query) use ($districtCode, $cityCode, $provinceCode) {
            $query->where('district_code', $districtCode)
                ->whereOr(function ($query) use ($cityCode) {
                    $query->where('district_code', '')->where('city_code', $cityCode);
                })->whereOr(function ($query) use ($provinceCode) {
                    $query->where('district_code', '')->where('city_code', '')->where('province_code', $provinceCode);
                });
        })->order('supplier_id', 'asc')->find();
        if (!$area) {
            throw new DomainException('当前地址不在配送范围', 40914, 409, ['area_id' => (string)$address['area_id']]);
        }
        $slot = null;
        if ($slotId) {
            $slot = Db::name('shop_delivery_slot')->where('id', (int)$slotId)->where('area_id', $area['id'])->where('status', 'normal')->find();
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
                'detail' => $address['address'], 'zipcode' => $address['zipcode'],
            ],
        ];
    }
}
