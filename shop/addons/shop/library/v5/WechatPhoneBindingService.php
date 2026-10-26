<?php
namespace addons\shop\library\v5;

use think\Db;

/** Adds verified contact data to an existing identity. Never registers or merges users. */
class WechatPhoneBindingService
{
    private $gateway;
    public function __construct($gateway = null) { $this->gateway = $gateway ?: new WechatPhoneGateway(); }

    private function user($uid, $lock = false)
    {
        $query = Db::name('user')->where('id', (int)$uid);
        if ($lock) $query = $query->lock(true);
        $user = $query->find();
        if (!$user || $user['status'] !== 'normal') throw new DomainException('当前账号不可用，请重新登录', 40301, 403);
        return $user;
    }

    private function linked($uid)
    {
        $client = trim((string)getenv('SHOP_AGENT_CLIENT_ID'));
        if ($client === '' || !Db::name('shop_external_identity')->where(['client_id'=>$client,'user_id'=>(int)$uid,'status'=>'normal'])->find()) {
            throw new DomainException('请先完成小程序与商城账号同步', 40967, 409);
        }
    }

    private function result($uid, $binding)
    {
        return ['user_id'=>(int)$uid, 'phone_bound'=>(bool)$binding,
            'phone_masked'=>$binding ? substr($binding['national_number'],0,3) . '****' . substr($binding['national_number'],-4) : null,
            'country_code'=>$binding ? $binding['country_code'] : null,
            'verification_source'=>$binding ? $binding['verification_source'] : null,
            'verified_at'=>$binding ? (int)$binding['verified_at'] : null];
    }

    public function detail($uid)
    {
        $user = $this->user($uid);
        $binding = Db::name('shop_phone_binding')->where('user_id',(int)$uid)->find();
        // A later manual account edit is not proof of a new verified number.
        if ($binding && (string)$user['mobile'] !== $this->mobile($binding)) $binding = null;
        return $this->result($uid, $binding);
    }

    private function mobile(array $phone)
    {
        return $phone['country_code'] === '86' ? $phone['national_number'] : '+' . $phone['country_code'] . $phone['national_number'];
    }

    private function advisory($value)
    {
        Db::query('SELECT pg_advisory_xact_lock(hashtext(:phone_lock))', ['phone_lock'=>$value]);
    }

    public function bind($uid, array $payload, $key)
    {
        if (array_keys($payload) !== ['phone_code'] || !is_string($payload['phone_code']) ||
            !preg_match('/^[A-Za-z0-9._~-]{1,512}$/D', $payload['phone_code'])) {
            throw new DomainException('仅接受有效的微信手机号授权 code', 40001, 400);
        }
        if (!is_string($key) || !preg_match('/^[A-Za-z0-9_-]{16,64}$/D', $key)) {
            throw new DomainException('请提供16至64位的独立绑定请求编号', 40003, 400);
        }
        if (config('database.type') !== 'pgsql') throw new DomainException('手机号绑定存储尚未配置', 50311, 503);
        $this->user($uid); $this->linked($uid);
        $settings = $this->gateway->config();
        if (!$settings['available']) throw new DomainException('微信手机号授权尚未配置', 50311, 503);
        $app = $settings['appid'];
        $codeHash = hash('sha256',$app . ':' . $payload['phone_code']);
        $keyHash = hash('sha256',$key);
        $now = time();
        Db::startTrans();
        try {
            $this->advisory('phone-user:' . (int)$uid);
            $this->user($uid, true);
            $record = Db::name('shop_phone_binding_request')->where(['user_id'=>(int)$uid,'key_hash'=>$keyHash])->lock(true)->find();
            if ($record) {
                if (!hash_equals($record['code_hash'],$codeHash)) throw new DomainException('同一请求编号不能用于不同授权',40964,409);
                if ($record['status'] === 'succeeded') {
                    $result = $this->detail($uid);
                    Db::commit(); return $result;
                }
                if ($record['status'] === 'processing' && (int)$record['updated_at'] > time()-45) {
                    throw new DomainException('手机号绑定正在处理，请稍后查询绑定状态',40966,409);
                }
                throw new DomainException('上次授权结果未完成，请查询绑定状态后重新授权并使用新的请求编号',40963,409);
            }
            if (Db::name('shop_phone_binding_request')->where('code_hash',$codeHash)->find()) {
                throw new DomainException('此授权已提交，请查询绑定状态或重新授权',40963,409);
            }
            if (Db::name('shop_phone_binding_request')->where('user_id',(int)$uid)->where('created_at','>',time()-60)->count() >= 5) {
                throw new DomainException('手机号授权请求过于频繁，请稍后重试',42900,429);
            }
            $requestId = Db::name('shop_phone_binding_request')->insertGetId(['user_id'=>(int)$uid,'key_hash'=>$keyHash,
                'code_hash'=>$codeHash,'app_id'=>$app,'status'=>'processing','created_at'=>$now,'updated_at'=>$now]);
            Db::commit();
        } catch (\Throwable $e) {
            Db::rollback();
            if ($e instanceof DomainException) throw $e;
            // Concurrent reuse of a single-use grant is rejected by the unique constraint.
            throw new DomainException('绑定请求未受理，请查询状态后重新授权',40963,409);
        }

        try {
            $phone = $this->gateway->exchange($payload['phone_code']);
            Db::startTrans();
            try {
                $this->advisory('phone-user:' . (int)$uid);
                $this->advisory('phone-number:' . $phone['country_code'] . ':' . $phone['national_number']);
                $user = $this->user($uid, true); $this->linked($uid);
                $binding = Db::name('shop_phone_binding')->where('user_id',(int)$uid)->lock(true)->find();
                $mobile = $this->mobile($phone);
                if (($binding && ($binding['country_code'] !== $phone['country_code'] || $binding['national_number'] !== $phone['national_number'])) ||
                    ((string)$user['mobile'] !== '' && (string)$user['mobile'] !== $mobile)) {
                    throw new DomainException('当前账号已有其他手机号，请通过独立换绑流程处理',40965,409);
                }
                $other = Db::name('shop_phone_binding')->where(['country_code'=>$phone['country_code'],'national_number'=>$phone['national_number']])->where('user_id','<>',(int)$uid)->find();
                $legacy = Db::name('user')->where('mobile',$mobile)->where('id','<>',(int)$uid)->find();
                if ($other || $legacy) throw new DomainException('此手机号已关联其他账号，不能自动合并，请联系管理员核对',40962,409);
                $row = ['user_id'=>(int)$uid,'country_code'=>$phone['country_code'],'national_number'=>$phone['national_number'],
                    'app_id'=>$app,'verification_source'=>'wechat_phone','verified_at'=>time()];
                if ($binding) Db::name('shop_phone_binding')->where('user_id',(int)$uid)->update($row);
                else Db::name('shop_phone_binding')->insert($row);
                Db::name('user')->where('id',(int)$uid)->update(['mobile'=>$mobile]);
                $result = $this->result($uid,$row);
                Db::name('shop_phone_binding_request')->where('id',$requestId)->update(['status'=>'succeeded',
                    'result_json'=>json_encode($result),'updated_at'=>time()]);
                Db::commit(); return $result;
            } catch (\Throwable $e) { Db::rollback(); throw $e; }
        } catch (\Throwable $e) {
            $known = $e instanceof DomainException;
            $status = $known && $e->getHttpStatus() < 500 ? 'failed' : 'uncertain';
            Db::name('shop_phone_binding_request')->where('id',$requestId)->where('status','processing')->update([
                'status'=>$status,'error_code'=>$known ? $e->getCode() : 50313,'updated_at'=>time()]);
            if ($known) throw $e;
            throw new DomainException('绑定结果暂不能确认，请先查询手机号状态',50313,503);
        }
    }
}
