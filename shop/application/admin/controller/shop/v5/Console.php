<?php
namespace app\admin\controller\shop\v5;

use think\Db;
use think\Response;

/** New commerce presentation layer. Reuses Workspace/domain services and existing RBAC. */
class Console extends Workspace
{
    protected $layout = false;
    protected $noNeedRight = ['index','bootstrap','listing','record','persist','overview','operate','account','publication','publicationFilters','publicationSummary','bulkPublicationPreview','bulkPublicationConfirm','importTemplate','importPreview','importConfirm','importHistory','importRecord','skuTemplates'];
    protected function requireImport($write=false, $confirm=false)
    {
        $this->requireResource('goods',$write);
        if ($write) {
            $this->requireResource('suppliers',true);
            $permission=$confirm?'confirmimport':'previewimport';
            if (!$this->auth->check('shop/v5/workspace/'.$permission)) $this->error('没有商品导入操作权限');
        }
    }
    public function importTemplate()
    {
        $this->requireImport();
        return parent::downloadImportTemplate();
    }
    public function importHistory()
    {
        $this->requireImport();
        $search=trim((string)$this->request->get('q',''));
        $build=function()use($search){$query=Db::name('shop_master_data_import');if($search!=='')$query->where('batch_sn|original_name','like','%'.$search.'%');return $query;};
        $total=$build()->count();
        $query=$build();
        $rows=$query->field('id,batch_sn,original_name,status,total_rows,valid_rows,invalid_rows,inserted_count,updated_count,createtime,imported_at')->order('id','desc')->limit(max(0,(int)$this->request->get('offset',0)),20)->select();
        $this->ok(['total'=>$total,'rows'=>$rows]);
    }
    public function importRecord()
    {
        $this->requireImport();
        try {$result=(new \addons\shop\library\v5\MasterDataImportService())->detail((int)$this->request->get('id',0));}
        catch (\Exception $e) {$this->error($e->getMessage());}
        $batchId=(int)$this->request->get('id',0);
        $batch=Db::name('shop_master_data_import')->where('id',$batchId)->find();
        $result['original_name']=$batch['original_name'];
        $result['rows_total']=Db::name('shop_master_data_import_row')->where('batch_id',$batchId)->count();
        $result['rows']=Db::name('shop_master_data_import_row')->where('batch_id',$batchId)->field('sheet_name,row_no,business_key,status,action,error_message,data_json')->order('id')->limit(max(0,(int)$this->request->get('offset',0)),100)->select();
        $this->ok($result);
    }
    public function importPreview()
    {
        $this->requireImport(true);
        if (!$this->request->isPost()) $this->error('请求方式错误');
        $this->token();
        try {
            $file=$this->request->file('file');
            if (!$file) throw new \RuntimeException('请选择 .xlsx 文件；文件不能超过 12 MB');
            $name=(string)$file->getInfo('name');
            if (strtolower(pathinfo($name,PATHINFO_EXTENSION))!=='xlsx' || $file->getSize()<=0 || $file->getSize()>12*1024*1024) throw new \RuntimeException('仅支持不超过 12 MB 的 .xlsx 文件');
            $result=(new \addons\shop\library\v5\SupplierCatalogImportService())->preview($file->getRealPath(),$name,(int)$this->auth->id);
        } catch (\Exception $e) {$this->error($e->getMessage(),null,['__token__'=>$this->request->token()]);}
        $this->ok($result,$result['duplicate']?'文件已预检，返回原批次':'预检完成，尚未写入商品');
    }
    public function importConfirm()
    {
        $this->requireImport(true,true);
        if (!$this->request->isPost()) $this->error('请求方式错误');
        $this->token();
        try {$result=(new \addons\shop\library\v5\SupplierCatalogImportService())->confirm((int)$this->request->post('batch_id'),(int)$this->auth->id);}
        catch (\Exception $e) {$this->error($e->getMessage(),null,['__token__'=>$this->request->token()]);}
        $this->ok($result,'导入完成，新商品已保存为草稿；已有商品保留原上架状态');
    }
    protected function rights($resource)
    {
        $map=['goods'=>'product','skus'=>'product','categories'=>'product','specs'=>'product','spec_values'=>'product','inventory_logs'=>'product',
            'orders_all'=>'orders','orders_unpaid'=>'orders','orders_pending'=>'orders','orders_shipping'=>'orders','orders_completed'=>'orders','orders_closed'=>'orders',
            'aftersales'=>'aftersales','aftersales_pending'=>'aftersales','refunds'=>'aftersales','members'=>'members','addresses'=>'members',
            'suppliers'=>'suppliers','supplier_skus'=>'suppliers','supplier_orders'=>'supplier_collaboration','supplier_order_items'=>'supplier_collaboration',
            'fulfillment_events'=>'fulfillment','exceptions_supplier'=>'supplier_collaboration','admin_logs'=>'audit'];
        if ($resource==='admins') return 'auth/admin/index';
        if ($resource==='roles') return 'auth/group/index';
        if (!isset($map[$resource])) $this->error('该资源不属于商城管理范围');
        return 'shop/v5/workspace/'.$map[$resource];
    }
    protected function requireResource($resource,$write=false)
    {
        if (!$this->auth->check($this->rights($resource))) $this->error('没有该管理页面的访问权限');
        if ($write && !$this->auth->check('shop/v5/workspace/save')) $this->error('没有保存权限');
    }
    protected function ok($data=[],$message='读取成功')
    {
        header('Cache-Control: no-store');
        $data['__token__']=$this->request->token();
        $this->success($message,null,$data);
    }
    protected function permissionLabels()
    {
        return ['shop/v5/workspace/dashboard'=>'首页 · 查看经营工作台','shop/v5/workspace/product'=>'商品 · 查看商品、分类与规格',
            'shop/v5/workspace/save'=>'商品 / 供应商 · 保存基础资料','shop/v5/workspace/adjuststock'=>'商品 · 调整库存',
            'shop/v5/workspace/previewimport'=>'商品 · Excel 导入预检','shop/v5/workspace/confirmimport'=>'商品 · 确认 Excel 导入',
            'shop/v5/workspace/orders'=>'订单 · 查看订单与发货','shop/v5/workspace/shiporder'=>'订单 · 提交发货',
            'shop/v5/workspace/aftersales'=>'订单 · 查看售后','shop/v5/workspace/reviewaftersale'=>'订单 · 审核售后',
            'shop/v5/workspace/members'=>'用户 · 查看用户与购买记录','user/user/edit'=>'用户 · 编辑账号',
            'shop/v5/workspace/suppliers'=>'供应商 · 查看资料与关联商品','shop/v5/workspace/supplier_collaboration'=>'供应商 · 查看履约与异常',
            'shop/v5/workspace/resolveexception'=>'供应商 · 处理异常','auth/admin/index'=>'权限 · 查看管理员',
            'auth/admin/add'=>'权限 · 添加管理员','auth/admin/edit'=>'权限 · 编辑管理员','auth/group/index'=>'权限 · 查看角色',
            'auth/group/add'=>'权限 · 添加角色','auth/group/edit'=>'权限 · 编辑角色权限','shop/v5/workspace/audit'=>'权限 · 查看操作日志'];
    }
    public function index()
    {
        $root=rtrim($this->request->root(),'/');
        $assets=substr($root,-4)==='.php'?dirname($root):$root;
        $assets=rtrim($assets,'/');
        $config=['base'=>$root.'/shop/v5/console/','adminBase'=>$root.'/','assetBase'=>$assets,
            'csrf'=>$this->request->token(),'username'=>$this->auth->nickname?:$this->auth->username,'isolated'=>getenv('COMMERCE_ADMIN_ISOLATED')==='1'];
        $this->assign('consoleConfig',json_encode($config,JSON_UNESCAPED_UNICODE|JSON_HEX_TAG|JSON_HEX_AMP|JSON_HEX_APOS|JSON_HEX_QUOT));
        $this->assign('assetBase',$assets);
        $this->assign('assetVersion',substr(hash('sha256',file_get_contents(ROOT_PATH.'public/assets/js/backend/shop/console.js').file_get_contents(ROOT_PATH.'public/assets/css/backend/shop/console.css')),0,12));
        return $this->view->fetch('shop/v5/console');
    }
    protected function resources()
    {
        $r=parent::resources();
        // Keep original integration flags, but remove them from daily merchandising forms.
        unset($r['goods']['fields']['agent_visible'],$r['categories']['fields']['agent_visible']);
        $r['goods']['columns']['catalog_status']='发布状态';
        $r['goods']['columns']['agent_visible']='商品接口可见';
        $r['goods']['fields']['status']['required']=false;
        $r['goods']['fields']['content']=$this->f('商品详情','textarea');
        $r['goods']['fields']['images']=$this->f('商品轮播图','images');
        $r['categories']['fields']['status']['options']=['normal'=>'启用','hidden'=>'停用'];
        $r['suppliers']['fields']['status']['options']=['normal'=>'合作中','hidden'=>'停用'];
        $r['supplier_skus']['fields']['supplier_id']=$this->f('供应商','select',true,Db::name('shop_supplier')->order('name')->column('name','id'));
        $skuOptions=[];
        foreach(Db::name('shop_goods_sku')->alias('s')->join('shop_goods g','g.id=s.goods_id')->field('s.id,g.title,s.sku_id')->order('s.id','desc')->select() as $row) $skuOptions[$row['id']]=$row['title'].' / '.$row['sku_id'];
        $r['supplier_skus']['fields']['sku_id']=$this->f('商城商品规格','select',true,$skuOptions);
        $r['supplier_skus']['fields']['supplier_sku_name']['title']='供货名称备注';
        $r['supplier_skus']['fields']['source_note']=$this->f('供货备注','textarea');
        $r['supplier_skus']['fields']['stock_quantity']['title']='供应商可供数量';
        $r['supplier_skus']['fields']['status']['options']=['normal'=>'可供货','hidden'=>'停用'];
        return $r;
    }
    public function bootstrap()
    {
        $resources=[];
        foreach(['goods','skus','categories','specs','spec_values','inventory_logs','orders_all','orders_unpaid','orders_pending','orders_shipping','orders_completed','orders_closed','aftersales','aftersales_pending','refunds','members','addresses','suppliers','supplier_skus','supplier_orders','supplier_order_items','fulfillment_events','exceptions_supplier','admin_logs'] as $key){
            if (!$this->auth->check($this->rights($key))) continue;
            $r=$this->resource($key);
            $resources[$key]=['columns'=>$r['columns'],'fields'=>$r['fields'],'editable'=>$r['editable']&&$this->auth->check('shop/v5/workspace/save')];
        }
        $roles=[];$rules=[];
        if($this->auth->check('auth/admin/index')||$this->auth->check('auth/group/index')){
            $groups=$this->auth->getChildrenGroupIds($this->auth->isSuperAdmin());
            $roles=$groups?Db::name('auth_group')->where('id','in',$groups)->field('id,pid,name,rules,status')->select():[];
        }
        if($this->auth->check('auth/group/index')){
            $ruleIds=$this->auth->getRuleIds();
            $query=Db::name('auth_rule')->where('status','normal');
            if(!in_array('*',$ruleIds)) $query->where('id','in',$ruleIds?:[0]);
            $labels=$this->permissionLabels();
            $rules=$query->where('name','in',array_keys($labels))->field('id,pid,name,title,ismenu')->order('id')->select();
            foreach($rules as &$rule)$rule['title']=$labels[$rule['name']];unset($rule);
        }
        $permissions=[];
        foreach(['auth/admin/index','auth/admin/add','auth/admin/edit','auth/group/index','auth/group/add','auth/group/edit','user/user/edit','shop/v5/workspace/shiporder','shop/v5/workspace/adjuststock','shop/v5/workspace/reviewaftersale','shop/v5/workspace/resolveexception','shop/v5/workspace/dashboard'] as $name) $permissions[$name]=$this->auth->check($name);
        foreach (['previewimport','confirmimport'] as $action) $permissions['shop/v5/workspace/'.$action]=$this->auth->check('shop/v5/workspace/'.$action)&&$this->auth->check('shop/v5/workspace/product')&&$this->auth->check('shop/v5/workspace/suppliers')&&$this->auth->check('shop/v5/workspace/save');
        $this->ok(['resources'=>$resources,'roles'=>$roles,'rules'=>$rules,'permissions'=>$permissions]);
    }
    public function listing()
    {
        $resource=$this->request->get('resource','');$this->requireResource($resource);
        if($resource==='admins'){
            $ids=$this->auth->getChildrenAdminIds($this->auth->isSuperAdmin());
            $q=Db::name('admin')->where('id','in',$ids?:[0]);$search=trim((string)$this->request->get('q',''));
            if($search!=='')$q->where('username|nickname','like','%'.$search.'%');
            $rows=$q->field('id,username,nickname,email,mobile,status,logintime')->order('id')->select();
            foreach($rows as &$row){$row['groups']=Db::name('auth_group_access')->where('uid',$row['id'])->column('group_id');$row['groups_text']=implode('、',Db::name('auth_group')->where('id','in',$row['groups']?:[0])->column('name'));}unset($row);
            return json(['total'=>count($rows),'rows'=>array_slice($rows,max(0,(int)$this->request->get('offset',0)),20)]);
        }
        if($resource==='roles'){
            $ids=$this->auth->getChildrenGroupIds($this->auth->isSuperAdmin());$query=Db::name('auth_group')->where('id','in',$ids?:[0]);
            $search=trim((string)$this->request->get('q',''));if($search!=='')$query->where('name','like','%'.$search.'%');
            $rows=$query->field('id,pid,name,rules,status')->order('id')->select();
            return json(['total'=>count($rows),'rows'=>array_slice($rows,max(0,(int)$this->request->get('offset',0)),20)]);
        }
        return parent::data();
    }
    /** Templates are copied into new SKU labels; editing a template never rewrites existing SKUs. */
    public function skuTemplates()
    {
        $this->requireResource('skus');
        $specs=Db::name('shop_spec')->order('id')->field('id,name')->select();
        $values=Db::name('shop_spec_value')->order('spec_id')->order('id')->field('id,spec_id,value')->select();
        $this->ok(['specs'=>$specs,'values'=>$values]);
    }

    public function persist()
    {
        if(!$this->request->isPost())$this->error('请求方式错误');
        $resource=$this->request->post('resource','');$this->requireResource($resource,true);
        if(!in_array($resource,['goods','skus','categories','specs','spec_values','suppliers','supplier_skus'],true))$this->error('该资源不支持此保存方式');
        $row=$this->request->post('row/a',[]);
        foreach($row as $value)if(!is_scalar($value)&&$value!==null)$this->error('表单字段格式无效');
        $templateId=$this->request->post('template_value_id','');
        if ($templateId !== '') {
            if ($resource !== 'skus' || (int)$this->request->post('id',0)!==0) $this->error('规格模板仅用于新增商品规格，已有规格请直接编辑');
            if (!is_scalar($templateId) || !preg_match('/^[1-9][0-9]*$/D',(string)$templateId)) $this->error('请选择有效的规格模板值');
            $template=Db::name('shop_spec_value')->alias('v')->join('shop_spec s','s.id=v.spec_id')->where('v.id',(int)$templateId)->field('v.value')->find();
            if (!$template || trim((string)$template['value'])==='') $this->error('规格模板已不存在，请刷新后重新选择');
            if (trim((string)($row['sku_id']??''))!==trim((string)$template['value'])) $this->error('规格模板已变化，请重新打开新增规格并选择');
            $row['sku_id']=trim((string)$template['value']);
        }
        // Basic editing never changes publication. New products must first be saved as drafts.
        if($resource==='goods')unset($row['status']);
        $optionalNumbers=['skus'=>['marketprice'],'categories'=>['weigh'],'suppliers'=>['priority'],'supplier_skus'=>['stock_quantity','priority']];
        foreach($optionalNumbers[$resource]??[] as $field)if(array_key_exists($field,$row)&&$row[$field]==='')$row[$field]=0;
        if($resource==='skus')foreach(['price','marketprice']as $field)if(isset($row[$field])&&(!is_scalar($row[$field])||!preg_match('/^\d{1,8}(?:\.\d{1,2})?$/D',(string)$row[$field])))$this->error('价格须为非负金额，最多两位小数');
        $this->request->post(['row'=>$row]);
        if($resource==='supplier_skus'){
            if(!$this->auth->check('shop/v5/workspace/product'))$this->error('关联商品还需要商品管理权限');
            $row=$this->request->post('row/a',[]);$id=(int)$this->request->post('id',0);
            $dup=Db::name('shop_supplier_sku')->where('supplier_id',(int)($row['supplier_id']??0))->where('sku_id',(int)($row['sku_id']??0))->where('id','<>',$id)->find();
            if($dup)$this->error('此供应商已关联该规格，请编辑已有供货关系');
        }
        if($resource==='skus'){
            $id=(int)$this->request->post('id',0);$row=$this->request->post('row/a',[]);
            if($id){$old=Db::name('shop_goods_sku')->where('id',$id)->find();if($old&&((int)($row['stocks']??-1)!==(int)$old['stocks']))$this->error('库存变动请使用库存调整并填写原因');if($old&&(int)($row['goods_id']??0)!==(int)$old['goods_id'])$this->error('已有规格不能移动到其他商品');}
        }
        return parent::save();
    }
    protected function decorateScalarDisplayRows($resource, &$rows, array $definition)
    {
        parent::decorateScalarDisplayRows($resource, $rows, $definition);
        if ($resource === 'members') (new \addons\shop\library\v5\MiniappUserAccessService())->decorateUsers($rows);
    }
    protected function buildResourceQuery(array $definition,array $filter,$q,array $queryColumns)
    {
        if($definition['table']==='shop_goods')return (new \addons\shop\library\v5\BulkPublicationService())->query($filter,$q);
        $exact=[];
        foreach(['status','supplier_id','sku_id','goods_id','spec_id','category_id','user_id','paystate','orderstate','shippingstate'] as $key){
            if(array_key_exists($key,$filter)&&in_array($key,$queryColumns,true)&&is_scalar($filter[$key])&&$filter[$key]!==''){$exact[$key]=$filter[$key];unset($filter[$key]);}
        }
        $userSearch = $definition['table'] === 'user' && $q !== '';
        $query=parent::buildResourceQuery($definition,$filter,$userSearch?'':$q,$queryColumns);
        if ($userSearch) {
            $pattern = '%' . strtr($q, ['!' => '!!', '%' => '!%', '_' => '!_']) . '%';
            $linked = Db::name('shop_external_identity')->whereRaw("(external_user_ref LIKE :ref_q ESCAPE '!' OR external_account_name LIKE :name_q ESCAPE '!' OR external_account_id LIKE :id_q ESCAPE '!')", ['ref_q'=>$pattern,'name_q'=>$pattern,'id_q'=>$pattern])->column('user_id');
            $match = "(username LIKE :username_q ESCAPE '!' OR nickname LIKE :nickname_q ESCAPE '!' OR mobile LIKE :mobile_q ESCAPE '!'";
            if ($linked) $match .= ' OR id IN (' . implode(',',array_map('intval',$linked)) . ')';
            if (ctype_digit($q)) $match .= ' OR id = ' . (int)$q;
            $query->whereRaw($match.')',['username_q'=>$pattern,'nickname_q'=>$pattern,'mobile_q'=>$pattern]);
        }
        foreach($exact as $key=>$value)$query->where($key,$value);
        return $query;
    }
    public function record()
    {
        $resource=$this->request->get('resource','');$this->requireResource($resource);$id=(int)$this->request->get('id',0);
        $tables=['goods'=>'shop_goods','suppliers'=>'shop_supplier','supplier_orders'=>'shop_supplier_order','orders_all'=>'shop_order','members'=>'user','aftersales'=>'shop_order_aftersales'];
        if(!isset($tables[$resource]))$this->error('不支持此详情类型');
        if($id<=0||!Db::name($tables[$resource])->where('id',$id)->find())$this->error('记录不存在，请刷新列表');
        if($resource==='goods'){
            $goods=Db::name('shop_goods')->where('id',$id)->find();if(!$goods)$this->error('商品不存在');
            $skus=Db::name('shop_goods_sku')->where('goods_id',$id)->order('id')->select();
            $relations=$skus?$this->relations(['sku_id'=>['in',array_column($skus,'id')]]):[];
            $this->ok(['goods'=>array_intersect_key($goods,array_flip(['id','title','image','images','content','sale_type','category_id','status','goods_sn','agent_visible','catalog_status'])),'skus'=>$skus,'relations'=>$relations,'publication'=>(new \addons\shop\library\v5\ProductPublicationService())->describe($goods,$skus)]);
        }
        if($resource==='suppliers'){
            $row=Db::name('shop_supplier')->where('id',$id)->field('id,supplier_code,name,company_name,credit_code,contact_name,priority,status,interface_type')->find();if(!$row)$this->error('供应商不存在');
            $orders=$this->auth->check($this->rights('supplier_orders'))?Db::name('shop_supplier_order')->where('supplier_id',$id)->field('id,supplier_order_sn,platform_order_sn,status,push_status,push_attempts')->order('id','desc')->limit(50)->select():[];
            $this->ok(['supplier'=>$row,'relations'=>$this->relations(['supplier_id'=>$id]),'orders'=>$orders]);
        }
        if($resource==='supplier_orders'){
            $row=Db::name('shop_supplier_order')->where('id',$id)->find();if(!$row)$this->error('供应商订单不存在');
            $safe=array_intersect_key($row,array_flip(['id','supplier_order_sn','supplier_id','platform_order_sn','external_order_no','status','push_status','push_attempts','reject_code','updatetime']));
            $items=Db::name('shop_supplier_order_item')->where('supplier_order_id',$id)->field('id,supplier_sku_id,quantity,purchase_price_cent,unavailable_quantity,status,reason_code')->select();
            $relations=$items?$this->relations(['id'=>['in',array_column($items,'supplier_sku_id')]]):[];$byId=[];foreach($relations as$r)$byId[$r['id']]=$r;
            foreach($items as &$item){$r=$byId[$item['supplier_sku_id']]??[];$item['goods_title']=$r['goods_title']??'关联商品已不存在';$item['specification']=$r['specification']??'';$item['supplier_sku_code']=$r['supplier_sku_code']??'';}unset($item);
            $this->ok(['order'=>$safe,'items'=>$items,'exceptions'=>Db::name('shop_exception_order')->where('supplier_order_id',$id)->field('id,summary,status,resolution')->select()]);
        }
        if($resource==='orders_all'){
            $d=(new \addons\shop\library\v5\CommerceAdminService())->order($id);unset($d['sources']);
            $d['order']=array_merge($d['order'],Db::name('shop_order')->where('id',$id)->field('order_type,expressname,expressno,paytime,shippingtime,receivetime')->find()?:[]);
            $sn=$d['order']['order_sn'];
            $d['items']=Db::name('shop_order_goods')->where('order_sn',$sn)->field('id,title,goods_sku_id,nums,price,realprice,salestate')->select();
            $d['payments']=Db::name('shop_payment_record')->where('order_sn',$sn)->field('payment_sn,channel,amount_cent,status,paid_at')->select();
            $d['refunds']=Db::name('shop_refund_record')->where('order_sn',$sn)->field('refund_sn,refund_amount_cent,reason,status,failure_message,success_at')->select();
            $d['logistics']=Db::name('shop_fulfillment_event')->where('platform_order_sn',$sn)->field('carrier_code,tracking_no,normalized_status,description,occurred_at')->order('id')->select();
            $d['supplier_orders']=Db::name('shop_supplier_order')->where('platform_order_sn',$sn)->field('id,supplier_order_sn,status,push_status')->select();
            $this->ok($d);
        }
        if($resource==='members'){
            $users=[Db::name('user')->where('id',$id)->field('id,username,nickname,mobile,jointime,status')->find()];
            (new \addons\shop\library\v5\MiniappUserAccessService())->decorateUsers($users);
            $this->ok(['user'=>$users[0],
                'addresses'=>(new \addons\shop\library\v5\AddressService())->listRows($id)['items'],
                'orders'=>$this->auth->check($this->rights('orders_all'))?Db::name('shop_order')->where('user_id',$id)->field('id,order_sn,saleamount,paystate,orderstate,createtime')->order('id','desc')->limit(50)->select():[]]);
        }
        if($resource==='aftersales'){
            $r=Db::name('shop_order_aftersales')->where('id',$id)->find();if(!$r)$this->error('售后申请不存在');
            $this->ok(['aftersale'=>array_intersect_key($r,array_flip(['id','order_id','user_id','reason','refund','status','images','content','createtime']))]);
        }
        $this->error('不支持此详情类型');
    }
    protected function relations($where)
    {
        $rows=Db::name('shop_supplier_sku')->where($where)->order('id')->select();
        foreach($rows as &$r){$sku=Db::name('shop_goods_sku')->where('id',$r['sku_id'])->field('goods_id,sku_id')->find();$r['goods_id']=$sku['goods_id']??0;$r['goods_title']=Db::name('shop_goods')->where('id',$r['goods_id'])->value('title');$r['specification']=$sku['sku_id']??'';$r['supplier_name']=Db::name('shop_supplier')->where('id',$r['supplier_id'])->value('name');}unset($r);
        return $rows;
    }
    public function overview()
    {
        if(!$this->auth->check('shop/v5/workspace/dashboard'))$this->error('没有工作台权限');
        $days=(int)$this->request->get('days',1);if(!in_array($days,[1,7,30],true))$days=1;
        $start=strtotime(date('Y-m-d'))-($days-1)*86400;$end=strtotime(date('Y-m-d'))+86400;
        $payments=Db::name('shop_payment_record')->where('paid_at','>=',$start)->where('paid_at','<',$end)->where('status','paid')->where('channel','<>','local_test')->sum('amount_cent');
        $test=Db::name('shop_payment_record')->where('channel','local_test')->count();
        $trend=[];for($i=6;$i>=0;$i--){$s=strtotime(date('Y-m-d'))-$i*86400;$trend[]=['date'=>date('m-d',$s),'amount_cent'=>(int)Db::name('shop_payment_record')->where('paid_at','>=',$s)->where('paid_at','<',$s+86400)->where('status','paid')->where('channel','<>','local_test')->sum('amount_cent')];}
        $this->ok(['paid_cent'=>(int)$payments,'orders'=>Db::name('shop_order')->where('createtime','>=',$start)->where('createtime','<',$end)->count(),
            'pending'=>Db::name('shop_order')->where('order_type','normal')->where('paystate',1)->where('orderstate',0)->where('shippingstate',0)->count(),
            'aftersales'=>Db::name('shop_order_aftersales')->where('status',1)->count(),'test_payments_excluded'=>$test,'trend'=>$trend]);
    }
    public function publicationSummary()
    {
        $this->requireResource('goods');
        // One aggregate snapshot, using the same publication states as the product list.
        $counts=Db::name('shop_goods')->field("COUNT(*) AS total, COALESCE(SUM(CASE WHEN status='normal' AND catalog_status='published' AND agent_visible=1 THEN 1 ELSE 0 END),0) AS published, COALESCE(SUM(CASE WHEN catalog_status='draft' THEN 1 ELSE 0 END),0) AS draft")->find();
        $total=(int)$counts['total'];$published=(int)$counts['published'];$draft=(int)$counts['draft'];
        $this->ok(['total'=>$total,'published'=>$published,'hidden'=>$total-$published-$draft,'draft'=>$draft]);
    }
    public function publicationFilters()
    {
        $this->requireResource('goods');
        $this->ok([
            'suppliers'=>Db::name('shop_supplier')->field('id,name,status')->order('id')->select(),
            'categories'=>Db::name('shop_category')->field('id,name')->order('id')->select(),
            'batches'=>Db::name('shop_master_data_import')->where('status','imported')->field('id,batch_sn,original_name')->order('id','desc')->select()
        ]);
    }
    public function bulkPublicationPreview()
    {
        if(!$this->request->isPost())$this->error('请求方式错误');
        $this->requireResource('goods',true);$this->token();
        try{
            $filter=json_decode($this->request->post('filter','{}'),true);
            if(!is_array($filter))throw new \addons\shop\library\v5\DomainException('筛选条件无效');
            $service=new \addons\shop\library\v5\BulkPublicationService();
            $ids=$service->selectIds($this->request->post('mode','selected'),$this->request->post('ids/a',[]),$filter,$this->request->post('q',''));
            $preview=$service->preview($ids,$this->request->post('state',''));
            $ticket=bin2hex(random_bytes(24));
            \think\Session::set('commerce_bulk_publication',['ticket'=>$ticket,'admin_id'=>(int)$this->auth->id,'expires'=>time()+600,'preview'=>$preview]);
            unset($preview['eligible']);$preview['ticket']=$ticket;$preview['expires_in']=600;
        }catch(\addons\shop\library\v5\DomainException $e){$this->error($e->getMessage(),null,['__token__'=>$this->request->token()]);}
        $this->ok($preview,'预检完成，尚未改动商品');
    }
    public function bulkPublicationConfirm()
    {
        if(!$this->request->isPost())$this->error('请求方式错误');
        $this->requireResource('goods',true);$this->token();
        $saved=\think\Session::get('commerce_bulk_publication');$ticket=$this->request->post('ticket','');
        if(!$saved||$saved['admin_id']!==(int)$this->auth->id||$saved['expires']<time()||!is_string($ticket)||!hash_equals($saved['ticket'],$ticket))$this->error('预检已失效或已执行，请重新预检',null,['__token__'=>$this->request->token()]);
        if($this->request->post('ack','')!=='1')$this->error('请先确认本次商品和操作范围',null,['__token__'=>$this->request->token()]);
        if($saved['preview']['state']==='normal'&&$saved['preview']['has_sample']&&$this->request->post('sample_ack','')!=='1')$this->error('包含示例标记商品，请先核实真实资料',null,['__token__'=>$this->request->token()]);
        // Consume before execution. A repeated click cannot repeat a confirmed batch.
        \think\Session::delete('commerce_bulk_publication');
        $result=(new \addons\shop\library\v5\BulkPublicationService())->execute($saved['preview']);
        \app\admin\model\AdminLog::setTitle($saved['preview']['state']==='normal'?'商品批量上架':'商品批量下架');
        \app\admin\model\AdminLog::setContent(['state'=>$saved['preview']['state'],'result'=>$result]);
        $this->ok($result,'批量处理完成，请查看逐项结果');
    }

    public function publication()
    {
        if(!$this->request->isPost())$this->error('请求方式错误');
        $this->requireResource('goods',true);$this->token();
        $id=(int)$this->request->post('id',0);$state=$this->request->post('state','');
        try{$result=(new \addons\shop\library\v5\ProductPublicationService())->change($id,$state,$this->request->post('revision',''));}
        catch(\addons\shop\library\v5\DomainException $e){$this->error($e->getMessage(),null,['__token__'=>$this->request->token(),'issues'=>$e->getDetails()['issues']??[]]);}
        catch(\Throwable $e){$this->error('发布未完成，请刷新商品后重试',null,['__token__'=>$this->request->token()]);}
        \app\admin\model\AdminLog::setTitle($state==='normal'?'商品上架发布':'商品下架');
        \app\admin\model\AdminLog::setContent(['goods_id'=>$id,'state'=>$state,'changed'=>$result['changed']]);
        $this->ok($result,$state==='normal'?'商品已上架，可通过小程序商品接口查询':'商品已下架，小程序商品接口不再展示');
    }
    public function operate()
    {
        if(!$this->request->isPost())$this->error('请求方式错误');
        $action=$this->request->post('operation','');
        $map=['stock'=>'adjustStock','ship'=>'shipOrder','review'=>'reviewAftersale','resolve'=>'resolveException'];
        if(!isset($map[$action])||!$this->auth->check('shop/v5/workspace/'.strtolower($map[$action])))$this->error('没有该操作权限');
        // Keep isolated review sessions read-only for order/stock side effects.
        if(getenv('COMMERCE_ADMIN_ISOLATED')==='1')$this->error('隔离验证环境禁止发货、退款、库存变更和异常关闭；请先完成只读检查');
        switch($action){case 'stock':return parent::adjustStock();case 'ship':return parent::shipOrder();case 'review':return parent::reviewAftersale();case 'resolve':return parent::resolveException();}
    }
    public function account()
    {
        if(!$this->request->isPost())$this->error('请求方式错误');
        $this->requireResource('members');if(!$this->auth->check('user/user/edit'))$this->error('没有用户编辑权限');$this->token();
        $id=(int)$this->request->post('id');$row=$this->request->post('row/a',[]);$safe=array_intersect_key($row,array_flip(['nickname','mobile','status','password']));
        foreach($safe as $key=>$value){if(!is_scalar($value)&&$value!==null)$this->error('账号资料格式无效');$safe[$key]=trim((string)$value);}
        if(isset($safe['nickname'])&&mb_strlen($safe['nickname'])>50)$this->error('昵称不能超过50个字符');
        \app\admin\model\AdminLog::setContent(['user_id'=>$id,'action'=>'商城用户维护','fields'=>array_keys($safe)]);
        if(isset($safe['status'])&&!in_array($safe['status'],['normal','hidden'],true))$this->error('账号状态无效');
        if(!empty($safe['mobile'])&&!preg_match('/^1[3-9]\d{9}$/D',$safe['mobile']))$this->error('手机号格式不正确');
        if(!empty($safe['mobile'])&&Db::name('user')->where('mobile',$safe['mobile'])->where('id','<>',$id)->find())$this->error('手机号已被使用');
        if(!empty($safe['password'])&&(strlen($safe['password'])<8||strlen($safe['password'])>64))$this->error('密码长度须为8至64个字符');
        if(!empty($safe['password']) && Db::name('shop_external_identity')->where('user_id',$id)->count()) $this->error('小程序关联账号使用原登录身份，不能在商城设置微信登录密码');
        if(empty($safe['password']))unset($safe['password']);
        $model=\app\admin\model\User::get($id);if(!$model)$this->error('用户不存在');
        Db::startTrans();try{$model->save($safe);Db::commit();}catch(\Throwable $e){Db::rollback();$this->error('保存失败，请检查内容后重试',null,['__token__'=>$this->request->token()]);}
        $this->ok([],'用户资料已保存');
    }
}
