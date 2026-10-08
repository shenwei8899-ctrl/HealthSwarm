<?php

namespace addons\shop\model;

use think\Model;
use traits\model\SoftDelete;

/**
 * 模型
 */
class Address extends Model
{

    use SoftDelete;

    // 表名
    protected $name = 'shop_address';
    // 开启自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';
    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    protected $deleteTime = 'deletetime';

    // 追加属性
    protected $append = [];

    public static function init()
    {
        parent::init();
        self::beforeWrite(function ($row) {
            $changed = $row->getChangedData();
            if (isset($changed['isdefault']) && $changed['isdefault']) {
                $info = \addons\shop\model\Address::where('isdefault', 1)->where('user_id', $row['user_id'])->find();
                if ($info && (!isset($row['id']) || $info['id'] != $row['id'])) {
                    $info->isdefault = 0;
                    $info->save();
                }
            }
            $row['address'] = $row->address_full;
        });
    }

    public function getAddressBaseAttr($value, $data)
    {
        $areainfo = $this->getAreainfoAttr($value, $data);
        $province = $areainfo['province'] ? $areainfo['province']['name'] : '';
        $city = $areainfo['city'] ? $areainfo['city']['name'] : '';
        $area = $areainfo['area'] ? $areainfo['area']['name'] : '';
        $value = $data['address'];
        $value = preg_replace("/^{$province}{$city}{$area}/", "", $value);
        return $value;
    }

    public function getAddressFullAttr($value, $data)
    {
        $areainfo = $this->getAreainfoAttr($value, $data);
        $province = $areainfo['province'] ? $areainfo['province']['name'] : '';
        $city = $areainfo['city'] ? $areainfo['city']['name'] : '';
        $area = $areainfo['area'] ? $areainfo['area']['name'] : '';
        $value = $data['address'];
        $value = preg_replace("/^{$province}{$city}{$area}/", "", $value);
        $value = $province . $city . $area . $value;
        return $value;
    }

    /**
     * 获取城市和地区信息
     * @param $value
     * @param $data
     * @return array
     */
    public function getAreainfoAttr($value, $data)
    {
        $result = [
            'province' => null,
            'city'     => null,
            'area'     => null,
        ];
        $areaList = Area::where('id', 'in', [$data['province_id'], $data['city_id'], $data['area_id']])->select();
        foreach ($areaList as $index => $item) {
            $levelName = ($item['level'] == 1 ? 'province' : ($item['level'] == 2 ? 'city' : 'area'));
            $result[$levelName] = $item;
        }
        return $result;
    }

    public function getMobileAttr($value, $data)
    {
        return substr_replace($value, '****', 3, 4);
    }

    /**
     * 获取会员地址列表
     * @param $user_id
     * @return false|\PDOStatement|string|\think\Collection
     */
    public static function getAddressList($user_id)
    {
        $addressList = self::where('user_id', $user_id)->where('status', 'normal')
            ->field('id,address,mobile,receiver,isdefault')
            ->order('usednums desc,id desc')->select();
        return $addressList;
    }
}
