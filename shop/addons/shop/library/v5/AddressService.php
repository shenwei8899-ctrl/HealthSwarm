<?php

namespace addons\shop\library\v5;

use think\Db;

class AddressService
{
    public function listRows($uid)
    {
        $rows = Db::name('shop_address')->where('user_id', $uid)->where('status', 'normal')->whereNull('deletetime')
            ->order('isdefault desc,id desc')->select();
        return ['items' => array_map([$this, 'format'], $rows)];
    }

    public function areas($pid = 0, $all = false)
    {
        $query = Db::name('shop_area')->where('status', 'normal');
        if (!$all) $query->where('pid', (int)$pid);
        return ['items' => $query->field('id,pid,name,level,adcode')->order('id')->select()];
    }

    public function save($uid, array $p, $id = null)
    {
        foreach (['name', 'phone', 'region', 'detail'] as $field) {
            if (!isset($p[$field]) || !is_string($p[$field]) || !trim($p[$field])) throw new DomainException('请完整填写收件信息', 40001, 400);
        }
        if (!preg_match('/^1\d{10}$/', $p['phone']) || mb_strlen($p['name']) > 50 || mb_strlen($p['detail']) > 200) {
            throw new DomainException('手机号或地址长度无效', 40001, 400);
        }
        $area = $this->resolveArea($p);
        $city = Db::name('shop_area')->where('id', $area['pid'])->find();
        $province = $city ? Db::name('shop_area')->where('id', $city['pid'])->find() : null;
        if (!$city || !$province) throw new DomainException('地区层级无效', 40001, 400);
        Db::startTrans();
        try {
            Db::name('user')->where('id', $uid)->lock(true)->find();
            $row = $id ? $this->owned($uid, $id) : null;
            if ($row && (!isset($p['version']) || (int)$p['version'] !== (int)$row['row_version'])) {
                throw new DomainException('地址已更新，请重新读取', 40906, 409);
            }
            $data = ['user_id' => $uid, 'receiver' => trim($p['name']), 'mobile' => $p['phone'],
                'province_id' => $province['id'], 'city_id' => $city['id'], 'area_id' => $area['id'],
                'address' => trim($p['detail']), 'zipcode' => $area['zipcode'], 'isdefault' => 1,
                'status' => 'normal', 'row_version' => $row ? (int)$row['row_version'] + 1 : 1, 'updatetime' => time()];
            Db::name('shop_address')->where('user_id', $uid)->where('isdefault', 1)->update(['isdefault' => 0]);
            if ($id) Db::name('shop_address')->where('id', $id)->update($data);
            else $id = Db::name('shop_address')->insertGetId($data + ['createtime' => time()]);
            Db::commit();
        } catch (\Exception $e) { Db::rollback(); throw $e; }
        return $this->format($this->owned($uid, $id));
    }

    public function selectDefault($uid, $id)
    {
        Db::startTrans();
        try {
            Db::name('user')->where('id', $uid)->lock(true)->find();
            $this->owned($uid, $id);
            Db::name('shop_address')->where('user_id', $uid)->where('isdefault', 1)->update(['isdefault' => 0]);
            Db::name('shop_address')->where('id', $id)->update(['isdefault' => 1]);
            Db::commit();
        } catch (\Exception $e) { Db::rollback(); throw $e; }
        return $this->format($this->owned($uid, $id));
    }

    public function remove($uid, $id)
    {
        Db::startTrans();
        try {
            Db::name('user')->where('id', $uid)->lock(true)->find();
            $row = $this->owned($uid, $id);
            Db::name('shop_address')->where('id', $id)->where('user_id', $uid)->update(['status' => 'deleted', 'deletetime' => time(), 'isdefault' => 0]);
            if ($row['isdefault']) {
                $next = Db::name('shop_address')->where('user_id', $uid)->where('status', 'normal')->whereNull('deletetime')->order('id', 'desc')->find();
                if ($next) Db::name('shop_address')->where('id', $next['id'])->update(['isdefault' => 1]);
            }
            Db::commit();
        } catch (\Throwable $e) { Db::rollback(); throw $e; }
        return $this->listRows($uid);
    }

    private function owned($uid, $id)
    {
        $row = Db::name('shop_address')->where('id', $id)->where('user_id', $uid)->where('status', 'normal')->whereNull('deletetime')->find();
        if (!$row) throw new DomainException('收货地址不存在', 40407, 404);
        return $row;
    }

    private function resolveArea(array $p)
    {
        $parts = preg_split('/[\s\/]+/u', trim($p['region']), -1, PREG_SPLIT_NO_EMPTY);
        if (count($parts) < 2 || count($parts) > 3) throw new DomainException('请按“省 市 区”填写地区，直辖市可填“市 区”', 40001, 400);
        $query = Db::name('shop_area')->alias('a')->join('shop_area c', 'c.id=a.pid')->join('shop_area p', 'p.id=c.pid')
            ->where('a.level', 3)->where('a.status', 'normal')->where('p.name', $parts[0])->where('a.name', end($parts));
        if (count($parts) === 3) $query->where('c.name', $parts[1]);
        if (!empty($p['area_id'])) $query->where('a.id', (int)$p['area_id']);
        $rows = $query->field('a.*')->limit(2)->select();
        if (count($rows) !== 1) throw new DomainException('地区无法唯一识别，请填写完整省、市、区名称', 40001, 400);
        return $rows[0];
    }

    public function format($row)
    {
        $names = [];
        foreach (['province_id', 'city_id', 'area_id'] as $key) $names[] = (string)Db::name('shop_area')->where('id', $row[$key])->value('name');
        $prefix = implode('', $names);
        $detail = $row['address'];
        if ($prefix !== '' && strpos($detail, $prefix) === 0) $detail = substr($detail, strlen($prefix));
        return ['id' => (string)$row['id'], 'name' => $row['receiver'], 'phone' => $row['mobile'], 'region' => implode(' ', $names),
            'detail' => $detail, 'area_id' => (string)$row['area_id'], 'isDefault' => (bool)$row['isdefault'], 'version' => (int)$row['row_version']];
    }
}
