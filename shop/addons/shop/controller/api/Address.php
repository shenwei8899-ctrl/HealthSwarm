<?php

namespace addons\shop\controller\api;

use addons\shop\model\Address as AddressModel;
use addons\shop\model\Area;

/**
 * 地址
 */
class Address extends Base
{
    protected $noNeedLogin = [];

    //地址列表
    public function index()
    {
        $list = AddressModel::getAddressList($this->auth->id);
        $this->success('', $list);
    }

    //地址详情
    public function detail()
    {
        $id = $this->request->param('id');
        if (!$id) {
            $this->error('参数错误');
        }
        $row = AddressModel::where('user_id', $this->auth->id)->where('id', $id)->find();
        if (!$row) {
            $this->error('未找到记录');
        }
        $this->success('获取成功', $row);
    }

    /**
     * @ 默认地址
     */
    public function def_address()
    {
        $row = AddressModel::where('user_id', $this->auth->id)->where('isdefault', 1)
            ->field('id,address,mobile,receiver')->find();
        if (!$row) {
            $this->error('未找到记录');
        }
        $this->success('获取成功', $row);
    }

    //添加(编辑)地址
    public function addedit()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $id = $this->request->post('id');
        $address = $this->request->post('address');
        $area_id = $this->request->post('area_id');
        $isdefault = $this->request->post('isdefault');
        $mobile = $this->request->post('mobile');
        $receiver = $this->request->post('receiver');
        $area = Area::field('a.id,a.zipcode,c.id as city_id,p.id as province_id')
            ->alias('a')
            ->join('shop_area c', 'a.pid=c.id')
            ->join('shop_area p', 'c.pid=p.id')
            ->where('a.id', $area_id)
            ->where('a.level', 3)
            ->find();
        if (!$area) {
            $this->error('未找到地区记录');
        }
        if (!$area['city_id'] || !$area['province_id']) {
            $this->error('地址错误');
        }

        $data = [
            'address'     => $address,
            'isdefault'   => $isdefault,
            'mobile'      => $mobile,
            'receiver'    => $receiver,
            'area_id'     => $area_id,
            'user_id'     => $this->auth->id,
            'city_id'     => $area['city_id'],
            'province_id' => $area['province_id'],
            'zipcode'     => $area['zipcode'],
            'status'      => 'normal'
        ];
        if ($id) { //编辑
            $row = AddressModel::where('id', $id)->where('user_id', $this->auth->id)->find();
            if (!$row) {
                $this->error('未找到记录');
            }
            $row->save($data);
        } else { //添加
            (new AddressModel)->save($data);
        }
        $this->success('操作成功');
    }

    //删除地址
    public function del()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $id = $this->request->post('id');
        if (!$id) {
            $this->error('参数错误');
        }
        $row = AddressModel::where('user_id', $this->auth->id)->where('id', $id)->find();
        if (!$row) {
            $this->error('未找到记录');
        }
        $row->delete();
        $this->success('删除成功');
    }
}
