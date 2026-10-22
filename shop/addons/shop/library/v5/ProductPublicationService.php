<?php
namespace addons\shop\library\v5;

use think\Db;

/** Publish the existing commerce product to its existing catalog, without changing stock or orders. */
class ProductPublicationService
{
    public function describe(array $goods, array $skus)
    {
        $issues=[];$available=0;
        if(trim((string)($goods['title']??''))==='')$issues[]='请填写商品名称';
        $image=trim((string)($goods['image']??''));
        if($image===''||preg_match('~^[a-z][a-z0-9+.-]*:~i',$image)&&!preg_match('~^https?://~i',$image))$issues[]='请上传有效的商品主图';
        if(!Db::name('shop_category')->where('id',(int)($goods['category_id']??0))->find())$issues[]='请选择有效的商品分类';
        if(!$skus)$issues[]='请先添加商品规格、售价和库存';
        foreach($skus as $sku){
            $label=trim((string)($sku['sku_id']??''));$label=$label!==''?$label:'未命名规格';
            if(trim((string)($sku['sku_id']??''))===''||trim((string)($sku['sku_code']??''))==='')$issues[]=$label.'：规格名称或系统编号缺失';
            if(!preg_match('/^\d{1,8}(?:\.\d{1,2})?$/D',(string)$sku['price']))$issues[]=$label.'：售价须为非负金额，最多两位小数';
            if(!is_numeric($sku['net_content_value'])||!is_finite((float)$sku['net_content_value'])||(float)$sku['net_content_value']<=0||!in_array($sku['net_content_unit'],['g','kg','ml','piece','pack'],true))$issues[]=$label.'：请填写有效的净含量和单位';
            if((int)$sku['stocks']-(int)$sku['reserved_stock']-(int)$sku['safety_stock']>0)$available++;
        }
        if($skus&&!$available)$issues[]='至少一个商品规格需要有可销售库存（实物库存减去预占和安全库存）';
        $published=$goods['status']==='normal'&&$goods['catalog_status']==='published'&&(int)$goods['agent_visible']===1;
        // Include SKU content so a concurrent price/stock edit cannot be published from a stale page.
        $snapshot=[$goods,$skus];array_walk_recursive($snapshot,function(&$value){if($value!==null)$value=(string)$value;});
        $revision=hash('sha256',Json::encode($snapshot));
        return ['published'=>$published,'can_publish'=>!$issues,'issues'=>array_values(array_unique($issues)),'available_sku_count'=>$available,'revision'=>$revision];
    }

    public function change($goodsId,$state,$revision)
    {
        if(!in_array($state,['normal','hidden'],true)||!is_string($revision)||!preg_match('/^[a-f0-9]{64}$/D',$revision))throw new DomainException('发布参数无效，请刷新商品页面',40001,400);
        Db::startTrans();
        try{
            $goods=Db::name('shop_goods')->where('id',(int)$goodsId)->lock(true)->find();
            if(!$goods)throw new DomainException('商品不存在，请刷新列表',40401,404);
            $skus=Db::name('shop_goods_sku')->where('goods_id',(int)$goodsId)->order('id')->lock(true)->select();
            $before=$this->describe($goods,$skus);
            if(!hash_equals($before['revision'],$revision))throw new DomainException('商品资料或库存已变化，请刷新后重新确认',40906,409);
            if($state==='normal'&&!$before['can_publish'])throw new DomainException(implode('；',$before['issues']),40917,409,['issues'=>$before['issues']]);
            $target=$state==='normal'?['status'=>'normal','catalog_status'=>'published','agent_visible'=>1]:['status'=>'hidden','catalog_status'=>$goods['catalog_status']==='draft'?'draft':'suspended','agent_visible'=>0];
            $changed=false;foreach($target as $key=>$value)if((string)$goods[$key]!== (string)$value)$changed=true;
            if($changed){
                $target['updatetime']=time();$target['catalog_version']=(int)$goods['catalog_version']+1;
                (new CatalogService())->touchVersion($state==='normal'?'product_publish':'product_unpublish',(string)$goodsId,$state==='normal'?'商品上架发布':'商品下架');
                Db::name('shop_goods')->where('id',(int)$goodsId)->update($target);$goods=array_merge($goods,$target);
            }
            // Check the same eligibility calculation used by the unchanged public product API.
            if($state==='normal'){
                $visible=false;foreach($skus as $sku)if((new CatalogService())->getSku($sku['id'],true)['sale_status']==='available'){$visible=true;break;}
                if(!$visible)throw new DomainException('商品暂不可展示，请检查规格和库存',40917,409);
            }
            $result=['id'=>(int)$goodsId,'changed'=>$changed,'publication'=>$this->describe($goods,$skus)];
            Db::commit();return$result;
        }catch(\Throwable$e){Db::rollback();throw$e;}
    }
}
