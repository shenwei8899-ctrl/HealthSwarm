<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\DeliveryService;
use think\Db;

class CommerceDelivery extends Base
{
    public function slots()
    {
        return $this->execute(function () {
            $addressId=(int)$this->request->get('address_id');
            $delivery=(new DeliveryService())->validateAddress($this->userId(),$addressId);
            $rows=Db::name('shop_delivery_slot')->where('area_id',$delivery['area']['id'])->where('status','normal')->order('start_time','asc')->select();
            foreach($rows as &$row){$row['available']=(int)$row['capacity']===0||(int)$row['used_capacity']<(int)$row['capacity'];$row['remaining_capacity']=(int)$row['capacity']===0?null:max(0,(int)$row['capacity']-(int)$row['used_capacity']);}
            return ['area'=>$delivery['area'],'date'=>$this->request->get('date'),'items'=>$rows];
        });
    }

    public function validateDelivery()
    {
        return $this->execute(function () {$p=$this->input();$delivery=(new DeliveryService())->validateAddress($this->userId(),$p['address_id'],isset($p['delivery_slot_id'])?$p['delivery_slot_id']:0);return ['supported'=>true,'area'=>$delivery['area'],'slot'=>$delivery['slot'],'address'=>$delivery['snapshot'],'failed_items'=>[]];});
    }
}
