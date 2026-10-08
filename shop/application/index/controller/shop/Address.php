<?php

namespace app\index\controller\shop;

use addons\shop\model\Area;
use app\common\controller\Frontend;
use think\Db;

class Address extends Frontend
{

    protected $layout = 'default';
    protected $noNeedLogin = [];
    protected $noNeedRight = ['*'];

    /**
     * 我的地址
     */
    public function index()
    {
        $addressList = \addons\shop\model\Address::where('user_id', $this->auth->id)->where('status', 'normal')->order('id', 'desc')->paginate(10);
        $this->view->assign('addressList', $addressList);
        $this->view->assign('title', "我的收货地址");
        return $this->view->fetch();
    }

    /**
     * 添加地址
     */
    public function add()
    {
        $this->view->assign('title', '添加收货地址');
        $this->view->assign('areainfo', null);
        $this->view->assign('address', ['isdefault' => 1]);
        return $this->view->fetch('shop/address/addedit');
    }

    /**
     * 修改地址
     */
    public function edit($id = null)
    {
        $address = \addons\shop\model\Address::get($id);
        if (!$address || $address['status'] != 'normal') {
            $this->error('未找到相关信息');
        }
        if ($address['user_id'] != $this->auth->id) {
            $this->error('无法进行越权操作');
        }
        $this->view->assign('address', $address);
        $this->view->assign('areainfo', $address->areainfo);
        $this->view->assign('title', '编辑地址');

        return $this->view->fetch('shop/address/addedit');
    }

    /**
     * 保存地址
     */
    public function save()
    {
        if ($this->request->isPost()) {
            $id = $this->request->post('id/d', 0);
            $province_id = $this->request->post('province_id/d');
            $city_id = $this->request->post('city_id/d');
            $area_id = $this->request->post('area_id/d');
            $address = $this->request->post('address');
            $mobile = $this->request->post('mobile');
            $receiver = $this->request->post('receiver');
            $isdefault = $this->request->post('isdefault', 0);
            if (!$province_id || !$city_id || !$area_id) {
                $this->error('省市区不能为空');
            }
            if (!$address) {
                $this->error('详细地址不能为空');
            }
            if (!$receiver) {
                $this->error('收货人姓名不能为空');
            }
            if (!$mobile) {
                $this->error('手机号不能为空');
            }
            $areaInfo = \addons\shop\model\Area::get($area_id);
            $zipcode = $areaInfo ? $areaInfo['zipcode'] : '';
            $data = [
                'user_id'     => $this->auth->id,
                'province_id' => $province_id,
                'city_id'     => $city_id,
                'area_id'     => $area_id,
                'address'     => $address,
                'mobile'      => $mobile,
                'receiver'    => $receiver,
                'zipcode'     => $zipcode,
                'isdefault'   => $isdefault,
                'status'      => 'normal',
            ];
            if ($id) {
                $addressInfo = \addons\shop\model\Address::get($id);
                if (!$addressInfo) {
                    $this->error('未找到相关信息');
                }
                if ($addressInfo['user_id'] != $this->auth->id) {
                    $this->error('无法进行越权操作');
                }
                $addressInfo->save($data);
            } else {
                \addons\shop\model\Address::create($data, true);
            }

            $this->success("保存成功", url("shop.address/index"));
        }
        return;
    }

    /**
     * 删除地址
     */
    public function del()
    {
        $id = $this->request->post("id/d");
        $addressInfo = \addons\shop\model\Address::get($id);
        if (!$addressInfo) {
            $this->error('未找到相关信息');
        }
        if ($addressInfo['user_id'] != $this->auth->id) {
            $this->error('无法进行越权操作');
        }
        Db::startTrans();
        try {
            $addressInfo->delete();
            if ($addressInfo->isdefault) {
                $prev = \addons\shop\model\Address::where('user_id', $this->auth->id)->where('status', 'normal')->order('id', 'desc')->find();
                if ($prev) {
                    $prev->save(['isdefault' => 1]);
                }
            }
            Db::commit();
        } catch (\Exception $e) {
            Db::rollback();
            $this->error('删除失败');
        }
        $this->success();
    }

    /**
     * 设置默认地址
     */
    public function setdefault()
    {
        $id = $this->request->post("id/d");
        $addressInfo = \addons\shop\model\Address::get($id);
        if (!$addressInfo) {
            $this->error('未找到相关信息');
        }
        if ($addressInfo['user_id'] != $this->auth->id) {
            $this->error('无法进行越权操作');
        }
        Db::startTrans();
        try {
            \addons\shop\model\Address::where('user_id', $this->auth->id)->where('isdefault', 1)->update(['isdefault' => 0]);
            $addressInfo->save(['isdefault' => 1]);
            Db::commit();
        } catch (\Exception $e) {
            Db::rollback();
            $this->error('操作失败');
        }
        $this->success();
    }

    /**
     * 读取省市区数据,联动列表
     */
    public function area()
    {
        $province_id = $this->request->get('province_id');
        $city_id = $this->request->get('city_id');
        $where = ['pid' => 0, 'level' => 1];
        $provinceList = null;
        if ($province_id !== '') {
            if ($province_id) {
                $where['pid'] = $province_id;
                $where['level'] = 2;
            }
            if ($city_id !== '') {
                if ($city_id) {
                    $where['pid'] = $city_id;
                    $where['level'] = 3;
                }
                $provinceList = Area::where($where)->field('id as value,name')->where('status', 'normal')->select();
            }
        }
        $this->success('', null, $provinceList);
    }


}
