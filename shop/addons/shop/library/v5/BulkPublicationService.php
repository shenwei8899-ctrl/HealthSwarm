<?php
namespace addons\shop\library\v5;

use think\Db;

/** Batch selection and preview. Publication still uses the existing locked single-product service. */
class BulkPublicationService
{
    const LIMIT = 1000;

    public function query(array $filter = [], $keyword = '')
    {
        $query=Db::name('shop_goods');
        $keyword=trim((string)$keyword);
        if($keyword!==''){
            $pattern='%'.strtr($keyword,['!'=>'!!','%'=>'!%','_'=>'!_']).'%';
            $query->whereRaw("(title LIKE :bulk_title ESCAPE '!' OR goods_sn LIKE :bulk_sn ESCAPE '!')",['bulk_title'=>$pattern,'bulk_sn'=>$pattern]);
        }
        foreach(['category_id','supplier_id','batch_id'] as $key){
            if(isset($filter[$key])&&$filter[$key]!==''){
                if(!is_scalar($filter[$key])||!ctype_digit((string)$filter[$key])||(int)$filter[$key]<1)throw new DomainException('筛选条件无效');
                $value=(int)$filter[$key];
                if($key==='category_id')$query->where('category_id',$value);
                elseif($key==='supplier_id'){
                    $ids=Db::name('shop_supplier_sku')->alias('ss')->join('shop_goods_sku k','k.id=ss.sku_id')->where('ss.supplier_id',$value)->column('k.goods_id');
                    $query->where('id','in',$ids?:[0]);
                }else $query->where('id','in',$this->batchGoods($value)?:[0]);
            }
        }
        $state=$filter['publication_state']??'';
        if(!in_array($state,['','draft','published','hidden'],true))throw new DomainException('发布状态无效');
        if($state==='draft')$query->where('catalog_status','draft');
        elseif($state==='published')$query->where('status','normal')->where('catalog_status','published')->where('agent_visible',1);
        elseif($state==='hidden')$query->whereRaw("COALESCE(catalog_status,'') <> 'draft' AND NOT (COALESCE(status,'')='normal' AND COALESCE(catalog_status,'')='published' AND COALESCE(agent_visible,0)=1)");
        // Retain older links that use the underlying status filter.
        if(!empty($filter['status'])){
            if(!in_array($filter['status'],['normal','hidden'],true))throw new DomainException('商品状态无效');
            $query->where('status',$filter['status']);
        }
        return $query;
    }

    public function batchGoods($batchId)
    {
        if(!Db::name('shop_master_data_import')->where('id',$batchId)->where('status','imported')->find())throw new DomainException('该导入批次尚未完成或不存在');
        $keys=[];
        foreach(Db::name('shop_master_data_import_row')->where('batch_id',$batchId)->column('data_json') as $json){
            $row=json_decode($json,true)?:[];
            if(isset($row['supplier_code'],$row['supplier_sku_code']))$keys[$row['supplier_code'].'|'.$row['supplier_sku_code']]=true;
        }
        // Old import records do not store goods IDs. Resolve their stable supplier/SKU keys to current goods.
        $relations=Db::name('shop_supplier_sku')->alias('ss')->join('shop_supplier s','s.id=ss.supplier_id')->join('shop_goods_sku k','k.id=ss.sku_id')->field('s.supplier_code,ss.supplier_sku_code,k.goods_id')->select();
        $ids=[];foreach($relations as $row)if(isset($keys[$row['supplier_code'].'|'.$row['supplier_sku_code']]))$ids[]=(int)$row['goods_id'];
        return array_values(array_unique($ids));
    }

    public function selectIds($mode, array $ids, array $filter, $keyword)
    {
        if($mode==='all')$ids=$this->query($filter,$keyword)->order('id')->limit(self::LIMIT+1)->column('id');
        elseif($mode!=='selected')throw new DomainException('请选择商品或全部筛选结果');
        foreach($ids as $id)if(!is_scalar($id)||!ctype_digit((string)$id)||(int)$id<1)throw new DomainException('商品编号无效');
        $ids=array_values(array_unique(array_map('intval',$ids)));sort($ids);
        if(!$ids)throw new DomainException('请先选择商品');
        if(count($ids)>self::LIMIT)throw new DomainException('单批最多处理1000件商品，请缩小筛选范围');
        return $ids;
    }

    protected function publisher(){return new ProductPublicationService();}

    public function preview(array $ids, $state)
    {
        if(!in_array($state,['normal','hidden'],true))throw new DomainException('批量操作类型无效');
        $ids=$this->selectIds('selected',$ids,[],'');$rows=[];$eligible=[];$sample=false;
        foreach($ids as $id){
            $goods=Db::name('shop_goods')->where('id',$id)->find();
            if(!$goods){$rows[]=['id'=>$id,'title'=>'商品已不存在','eligible'=>false,'issues'=>['商品已删除'],'skus'=>[],'suppliers'=>[]];continue;}
            $skus=Db::name('shop_goods_sku')->where('goods_id',$id)->order('id')->select();
            $description=$this->publisher()->describe($goods,$skus);
            $issues=$state==='normal'?$description['issues']:[];
            if($state==='normal'&&$description['published'])$issues=['已经上架，无需重复操作'];
            if($state==='hidden'&&!$description['published'])$issues=['当前未上架，无需下架'];
            $suppliers=Db::name('shop_supplier_sku')->alias('ss')->join('shop_supplier s','s.id=ss.supplier_id')->join('shop_goods_sku k','k.id=ss.sku_id')->where('k.goods_id',$id)->field('s.name,s.supplier_code,s.status as supplier_status,ss.status as relation_status')->select();
            $isSample=strpos($goods['title'],'示例')!==false;
            foreach($suppliers as $supplier)if(stripos($supplier['supplier_code'],'DEMO-')===0)$isSample=true;
            $ok=!$issues;
            if($ok){$eligible[]=['id'=>$id,'title'=>$goods['title'],'revision'=>$description['revision']];if($isSample)$sample=true;}
            $rows[]=['id'=>$id,'title'=>$goods['title'],'eligible'=>$ok,'issues'=>$issues,'sample'=>$isSample,'suppliers'=>$suppliers,'skus'=>array_map(function($sku){return ['label'=>$sku['sku_id'],'price'=>$sku['price'],'available'=>max(0,(int)$sku['stocks']-(int)$sku['reserved_stock']-(int)$sku['safety_stock'])];},$skus)];
        }
        return ['state'=>$state,'total'=>count($rows),'eligible_count'=>count($eligible),'blocked_count'=>count($rows)-count($eligible),'has_sample'=>$sample,'rows'=>$rows,'eligible'=>$eligible];
    }

    public function execute(array $preview)
    {
        if(!isset($preview['state'],$preview['eligible'])||!in_array($preview['state'],['normal','hidden'],true))throw new DomainException('预检无效，请重新检查');
        $results=[];
        foreach($preview['eligible'] as $row){
            try{
                $result=$this->publisher()->change($row['id'],$preview['state'],$row['revision']);
                $results[]=['id'=>$row['id'],'title'=>$row['title'],'status'=>$result['changed']?'changed':'unchanged','message'=>$result['changed']?'已完成':'状态已一致'];
            }catch(DomainException $e){$results[]=['id'=>$row['id'],'title'=>$row['title'],'status'=>'failed','message'=>$e->getMessage()];}
            catch(\Throwable $e){$results[]=['id'=>$row['id'],'title'=>$row['title'],'status'=>'failed','message'=>'未完成，请刷新后重新预检'];}
        }
        return ['rows'=>$results,'changed'=>count(array_filter($results,function($r){return $r['status']==='changed';})),'failed'=>count(array_filter($results,function($r){return $r['status']==='failed';})),'skipped'=>$preview['blocked_count']??0];
    }
}
