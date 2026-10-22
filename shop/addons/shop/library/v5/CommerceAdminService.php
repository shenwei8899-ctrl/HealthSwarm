<?php
namespace addons\shop\library\v5;
use think\Db;

/** 管理端仅返回交易所需字段，不输出密码、令牌或餐单来源签名。 */
class CommerceAdminService
{
    public function decorateUsers(array &$rows)
    {
        foreach ($rows as &$row) {
            $ids = Db::name('shop_external_identity')->where('user_id',$row['id'])->field('client_id,external_user_ref,status')->select();
            $active = array_values(array_filter($ids, function($i){return $i['status']==='normal';}));
            $row['account_source'] = $active ? '小程序 / Agent' : '商城本地账号';
            $row['linked_account'] = implode('、', array_map(function($i){return preg_replace('/^uid:/','',$i['external_user_ref']);}, $active));
            $row['binding_status'] = $active ? '已关联' : ($ids ? '关联已停用' : '未关联');
            $row['wechat_status'] = Db::name('shop_miniapp_identity')->where('user_id',$row['id'])->count() ? '已绑定' : '未绑定';
        }
    }

    public function user($id)
    {
        $row = Db::name('user')->where('id',(int)$id)->field('id,username,nickname,mobile,jointime,status')->find();
        if (!$row) throw new DomainException('用户不存在',40401,404);
        $rows=[$row];$this->decorateUsers($rows);
        return ['user'=>$rows[0], 'addresses'=>(new AddressService())->listRows($id)['items'],
            'cart'=>(new CartService())->listItems($id)['items'],
            'purchases'=>Db::name('shop_purchase_list')->where('user_id',$id)->field('purchase_list_sn,source_ref,source_version,status,createtime')->order('id','desc')->limit(50)->select(),
            'orders'=>Db::name('shop_order')->where('user_id',$id)->field('order_sn,saleamount,paystate,orderstate,createtime')->order('id','desc')->limit(50)->select(),
            'credential_note'=>'关联账号的密码由原登录系统管理，商城不显示密码。清单和订单各显示最近50条。'];
    }

    public function readiness($q='', $offset=0, $limit=20)
    {
        $build=function()use($q){$db=Db::name('shop_goods_sku')->alias('s')->join('shop_goods g','g.id=s.goods_id');if($q!=='')$db->where('g.title|s.sku_code','like','%'.$q.'%');return $db;};
        $count=$build()->count('s.id');
        $rows=$build()->field('s.id,s.sku_code,s.sku_id as specification,g.title')->order('s.id','asc')->limit($offset,$limit)->select();
        foreach($rows as &$r){
            $sku=(new CatalogService())->getSku($r['id']);
            $r['mapping_status']=$sku['purchase_ready']?'可用于采购':'待补充或审核';
            $r['nutrition_status']=$sku['nutrition_facts']?'有有效审核资料':'缺少有效审核资料';
            $r['allergen_status']=$sku['allergen_information_status']==='not_recorded'?'未录入，不能视为无过敏原':'已录入来源资料，需核实完整性';
            $r['missing_data']=implode('；',array_column($sku['data_issues'],'message'));
        }
        return ['total'=>$count,'rows'=>$rows];
    }

    public function purchase($type,$id)
    {
        $list=null;
        if($type==='purchase_lists'){
            $list=Db::name('shop_purchase_list')->where('id',(int)$id)->find();
            if(!$list)throw new DomainException('采购清单不存在',40403,404);
            $package=Db::name('shop_recommendation_package')->where('package_sn',$list['source_ref'])->find();
        }else $package=Db::name('shop_recommendation_package')->where('id',(int)$id)->find();
        if(!$package)throw new DomainException('餐单采购来源不存在',40402,404);
        $version=Db::name('shop_recommendation_package_version')->where('package_id',$package['id'])->where('version_no',$package['current_version'])->find();
        $lists=Db::name('shop_purchase_list')->where('source_type','recommendation_package')->where('source_ref',$package['package_sn'])->order('id','desc')->select();
        $allowed=['package_sn','user_id','user_ref','menu_version_ref','meal_date','current_version','nutrition_status','trade_status','confirm_status','status','expires_at','last_issue_code'];
        $summary=array_intersect_key($package,array_flip($allowed));
        $summary['source_evidence']=empty(Json::decode($package['agent_source_proof_json']??'[]',[]))?'未保存 Agent 来源凭据':'已保存，交易时仍须回源校验';
        $summary['expired']=(int)$package['expires_at']<=time();
        $summary['generation_notice']='商城记录不证明真实 AI 生成，生成、审核与采用以 Agent 来源为准。';
        $items=[];foreach($lists as $l){
            foreach(Db::name('shop_purchase_item')->where('purchase_list_id',$l['id'])->where('list_version_no',$l['current_version'])->select() as $item){$item['purchase_list_sn']=$l['purchase_list_sn'];$item['ingredient_code']=Db::name('shop_ingredient')->where('id',$item['ingredient_id'])->value('ingredient_code');$items[]=array_intersect_key($item,array_flip(['purchase_list_sn','ingredient_code','required_value','required_unit','pantry_value','pantry_unit','net_required_value','net_required_unit','match_status','selected_match_id']));}
        }
        $orders=[];
        foreach(Db::name('shop_order_ext')->alias('e')->join('shop_order o','o.id=e.order_id')->where('o.user_id',$package['user_id'])->field('e.order_sn,e.source_type,e.source_ref,e.source_version,e.pricing_snapshot_json,e.business_status,e.payment_status')->select() as $o){
            $sources=$this->sources($o);
            foreach($sources as $s){if(($s['source_type']==='recommendation_package' && $s['source_ref']===$package['package_sn']) || ($s['source_type']==='purchase_list' && in_array($s['source_ref'],array_column($lists,'purchase_list_sn'),true))){unset($o['pricing_snapshot_json']);$orders[]=$o;break;}}
        }
        return ['package'=>$summary,'requirements'=>Json::decode($version['requirements_snapshot_json']??'[]',[]),'issues'=>Json::decode($version['issues_json']??'[]',[]),'purchase_lists'=>array_map(function($l){return array_intersect_key($l,array_flip(['purchase_list_sn','source_ref','source_version','current_version','status','match_status','expires_at']));},$lists),'purchase_items'=>$items,'orders'=>$orders];
    }

    public function order($id)
    {
        $o=Db::name('shop_order')->where('id',(int)$id)->field('id,order_sn,user_id,saleamount,payamount,goodsprice,shippingfee,discount,paystate,orderstate,shippingstate,receiver,mobile,address,createtime')->find();
        if(!$o)throw new DomainException('订单不存在',40409,404);
        $e=Db::name('shop_order_ext')->where('order_id',$o['id'])->find();
        $sources=$e?$this->sources($e):[];
        foreach($sources as &$s){
            if($s['source_type']==='purchase_list'){$l=Db::name('shop_purchase_list')->where('purchase_list_sn',$s['source_ref'])->find();if($l){$s['package_sn']=$l['source_ref'];$s['package_version']=$l['source_version'];}}
            elseif($s['source_type']==='recommendation_package')$s['package_sn']=$s['source_ref'];
            if(isset($s['package_sn'])){$p=Db::name('shop_recommendation_package')->where('package_sn',$s['package_sn'])->find();if($p)$s['menu_version_ref']=$p['menu_version_ref'];}
        }
        return ['order'=>$o,'sources'=>$sources,'state'=>$e?array_intersect_key($e,array_flip(['business_status','payment_status','fulfillment_status','exception_status','request_id'])):[],
            'items'=>Db::name('shop_order_goods')->where('order_sn',$o['order_sn'])->field('goods_id,goods_sku_id,nums')->select(),
            'inventory'=>Db::name('shop_inventory_reservation')->where('source_type','checkout')->where('source_ref',$e['checkout_token_hash']??'')->field('sku_id,quantity,status')->select()];
    }

    public function sources(array $ext)
    {
        $pricing=Json::decode($ext['pricing_snapshot_json']??'{}',[]);
        $rows=($ext['source_type']??'')==='cart'?($pricing['cart_items']??[]):[$ext];$result=[];
        foreach($rows as $row){$type=$row['source_type']??'manual';$ref=$row['source_ref']??'';$v=(int)($row['source_version']??0);$result[$type.':'.$ref.':'.$v]=['source_type'=>$type,'source_ref'=>$ref,'source_version'=>$v];}
        return array_values($result);
    }

    public function status()
    {
        $missing=[];foreach(['SHOP_WECHAT_APP_ID','SHOP_WECHAT_APP_SECRET','SHOP_WECHAT_MCH_ID','SHOP_WECHAT_API_V2_KEY','SHOP_WECHAT_NOTIFY_URL'] as $k)if(!trim((string)getenv($k)))$missing[]=$k;
        return ['identity_configured'=>!!getenv('SHOP_AGENT_SESSION_URL')&&!!getenv('SHOP_AGENT_CLIENT_ID'),
            'pending_maps'=>Db::name('shop_ingredient_sku_map')->where('review_status','<>','approved')->count(),
            'nutrition_records'=>Db::name('shop_sku_nutrition_fact')->count(),
            'missing_wechat_configuration'=>$missing,
            'agent_notice'=>'真实餐单、健康资料、模型用途同意和专业审核请在 Agent 平台核实。商城不代为确认。'];
    }
}
