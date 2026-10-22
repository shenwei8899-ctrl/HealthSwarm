<?php
namespace addons\shop\library\v5;

use think\Db;

/** Configuration maintenance only; never calls a transport or fulfillment service. */
class SupplierApiConfigService
{
    public function detail($id)
    {
        $supplier=Db::name('shop_supplier')->where('id',(int)$id)->find();
        if (!$supplier) throw new DomainException('供应商不存在',40411,404);
        $client=Db::name('shop_integration_client')->where('client_id',$supplier['supplier_code'])->find();
        $conflict=$client && $client['client_type']!=='supplier';
        $ips=$client&&!$conflict?Json::decode($client['allowed_ip_json'],[]):[];
        if (!is_array($ips)) $ips=[];
        $path='/api/v1/integration/suppliers/'.rawurlencode($supplier['supplier_code']).'/order-events';
        $missing=[];
        if (trim((string)$supplier['endpoint_url'])==='') $missing[]='供应商真实下单接口地址';
        if (empty($supplier['secret_ciphertext'])) $missing[]='商城向供应商推单的共享签名密钥';
        if (!$client || $conflict || empty($client['secret_ciphertext'])) $missing[]='供应商回调商城的共享签名密钥';
        if (!$ips) $missing[]='供应商回调服务器的真实出口 IP';
        return [
            'supplier'=>['id'=>(int)$supplier['id'],'supplier_code'=>$supplier['supplier_code'],'name'=>$supplier['name'],'version'=>(int)$supplier['version'],'interface_type'=>$supplier['interface_type'],'status'=>$supplier['status']],
            'outbound'=>['endpoint_url'=>(string)$supplier['endpoint_url'],'secret_configured'=>!empty($supplier['secret_ciphertext'])],
            'callback'=>['client_id'=>$supplier['supplier_code'],'exists'=>(bool)$client,'conflict'=>(bool)$conflict,'version'=>$client?(int)$client['version']:0,'status'=>$client?$client['status']:'not_configured','secret_configured'=>$client&&!$conflict&&!empty($client['secret_ciphertext']),'allowed_ips'=>array_values($ips),'clock_skew_seconds'=>$client&&!$conflict?(int)$client['clock_skew_seconds']:300,'path'=>$path],
            'missing_configuration'=>$missing,
            'materials'=>['正式及沙箱接口地址、接口文档与对接联系人','真实推单凭据、签名算法及商户/客户编号约定','成功与拒单响应示例、幂等和重试约定','接单、缺货、发货、完成回调字段及状态说明','回调共享密钥、出口 IP、双方网络白名单与正式 HTTPS 回调域名','供应商 SKU、规格单位、采购价、起订量、库存与配送范围确认表'],
            'protocol'=>['method'=>'POST','content_type'=>'application/json','algorithm'=>'HMAC-SHA256','canonical'=>'METHOD + 换行 + 实际请求路径 + 换行 + 秒级时间戳 + 换行 + nonce + 换行 + SHA256(原始请求体)','outbound_client_id'=>'shop','callback_client_id'=>$supplier['supplier_code'],'headers'=>['X-Client-Id','X-Timestamp','X-Nonce','X-Signature','Idempotency-Key'],'callback_required_fields'=>['supplier_order_sn','event_id','status'],'callback_statuses'=>['accepted','preparing','shipped','completed','rejected','exception','partially_unavailable'],'nonce'=>'32至64字符，每次请求不同；重试沿用幂等键并使用新 nonce','notice'=>'下单地址由供应商提供；回调路径需与商城部署前缀组合并由双方确认。资料已填写不代表协议兼容或联调通过。'],
            'notice'=>'保存配置不会切换供应商对接方式，不会启用新建回调调用方，不会推单或改变历史订单。密钥留空保留原值，不回显明文。',
        ];
    }

    public function save($id,array $input)
    {
        $allowed=['endpoint_url','outbound_password','callback_password','allowed_ips','clock_skew_seconds','supplier_version','callback_version'];
        if (array_diff(array_keys($input),$allowed)) throw new DomainException('包含不支持的配置项；此处不能启用自动推单或回调',40001,400);
        foreach ($input as $value) if (!is_string($value)&&!is_int($value)) throw new DomainException('配置格式无效',40001,400);
        foreach (['endpoint_url','allowed_ips'] as $key) if (!array_key_exists($key,$input)) throw new DomainException('配置内容不完整，请刷新后重试',40001,400);
        foreach (['supplier_version','callback_version','clock_skew_seconds'] as $key) if (!isset($input[$key]) || !preg_match('/^\d+$/D',(string)$input[$key])) throw new DomainException('配置版本或时间偏差无效，请刷新后重试',40001,400);
        $skew=(int)$input['clock_skew_seconds'];
        if ($skew<30 || $skew>900) throw new DomainException('允许时间偏差应为30至900秒',40001,400);
        $url=trim($input['endpoint_url']??'');$parts=$url!==''?parse_url($url):[];
        if ($url!=='' && (strlen($url)>500 || !filter_var($url,FILTER_VALIDATE_URL) || !$parts || !in_array(strtolower($parts['scheme']??''),['http','https'],true) || isset($parts['user']) || isset($parts['pass']) || isset($parts['fragment']))) throw new DomainException('请填写有效HTTP/HTTPS接口地址，地址中不能包含账号密码或片段',40001,400);
        $secrets=[];
        foreach (['outbound_password','callback_password'] as $key) {
            $value=$input[$key]??'';
            if ($value!=='' && (strlen($value)<16 || strlen($value)>256 || preg_match('/[\x00-\x1F\x7F]/',$value))) throw new DomainException('新签名密钥应为16至256字符且不含控制字符',40001,400);
            if ($value!=='') $secrets[$key]=SecretCipher::encrypt($value);
        }
        $text=trim($input['allowed_ips']??'');$ips=$text===''?[]:preg_split('/[\s,]+/',$text);
        if (count($ips)>100) throw new DomainException('回调来源IP最多填写100个',40001,400);
        foreach ($ips as $ip) if (!filter_var($ip,FILTER_VALIDATE_IP)) throw new DomainException('回调来源IP格式无效；每行一个IPv4或IPv6，不支持网段',40001,400);
        $ips=array_values(array_unique($ips));
        Db::startTrans();
        try {
            $supplier=Db::name('shop_supplier')->where('id',(int)$id)->lock(true)->find();
            if (!$supplier) throw new DomainException('供应商不存在',40411,404);
            $client=Db::name('shop_integration_client')->where('client_id',$supplier['supplier_code'])->lock(true)->find();
            if ($client && $client['client_type']!=='supplier') throw new DomainException('该供应商编码已被其他类型调用方占用，请先核查系统配置',40933,409);
            if ((int)$supplier['version']!==(int)$input['supplier_version'] || ($client?(int)$client['version']:0)!==(int)$input['callback_version']) throw new DomainException('配置已被其他人修改，请重新打开后保存',40933,409);
            $now=time();
            $data=['endpoint_url'=>$url,'version'=>(int)$supplier['version']+1,'updatetime'=>$now];
            if (isset($secrets['outbound_password'])) $data['secret_ciphertext']=$secrets['outbound_password'];
            Db::name('shop_supplier')->where('id',$supplier['id'])->update($data);
            $callback=['allowed_ip_json'=>Json::encode($ips),'clock_skew_seconds'=>$skew,'version'=>$client?(int)$client['version']+1:1,'updatetime'=>$now];
            if (isset($secrets['callback_password'])) $callback['secret_ciphertext']=$secrets['callback_password'];
            if ($client) Db::name('shop_integration_client')->where('id',$client['id'])->update($callback);
            else Db::name('shop_integration_client')->insert($callback+['client_id'=>$supplier['supplier_code'],'client_type'=>'supplier','name'=>$supplier['name'].'回调','secret_ciphertext'=>'','callback_whitelist_json'=>'[]','status'=>'hidden','createtime'=>$now]);
            Db::commit();
        } catch (\Throwable $e) { Db::rollback(); throw $e; }
        return $this->detail($id);
    }
}
