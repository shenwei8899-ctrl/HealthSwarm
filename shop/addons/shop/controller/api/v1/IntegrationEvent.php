<?php

namespace addons\shop\controller\api\v1;

use think\Db;

class IntegrationEvent extends IntegrationBase
{
    protected $expectedClientType='agent';

    public function index()
    {
        return $this->execute(function(){
            $config=get_addon_config('shop');
            if(!empty($config['v5_agent_client_id'])&&$config['v5_agent_client_id']!==$this->clientId())throw new \addons\shop\library\v5\DomainException('调用方无权读取事件',40301,403);
            $limit=min(100,max(1,(int)$this->request->get('limit',50)));$after=(int)$this->request->get('after_id',0);
            $query=Db::name('shop_outbox_event')->where('destination','agent')->where('id','>',$after);
            if($this->request->get('resource_type'))$query->where('aggregate_type',$this->request->get('resource_type'));
            if($this->request->get('resource_ref'))$query->where('aggregate_ref',$this->request->get('resource_ref'));
            $rows=$query->order('id','asc')->limit($limit+1)->select();$more=count($rows)>$limit;if($more)array_pop($rows);
            foreach($rows as &$row){$row['data']=\addons\shop\library\v5\Json::decode($row['payload_json'],[]);unset($row['payload_json'],$row['last_error'],$row['locked_by']);}
            return ['items'=>$rows,'next_after_id'=>$rows?(int)end($rows)['id']:$after,'has_more'=>$more];
        },$this->integrationLog('agent_event_compensation','outbox'));
    }
}
