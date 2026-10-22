<?php
$_SERVER['REMOTE_ADDR']='127.0.0.1';
require dirname(__DIR__).'/bootstrap.php';
set_exception_handler(function($e){fwrite(STDERR,(string)$e."\n");exit(1);});
use think\Db;
use addons\shop\library\v5\{AgentMemberService,AgentSessionVerifier,DomainException,MiniappUserAccessService};
if(config('database.database')!=='healthflow_link_test'||getenv('HEALTHFLOW_RELEASE_TEST')!=='1')throw new RuntimeException('Dedicated fixture database required');
function accessCheck($ok,$message){if(!$ok)throw new RuntimeException($message);}
function accessReject($fn,$code){try{$fn();}catch(DomainException $e){accessCheck($e->getCode()===$code,'Unexpected rejection '.$e->getCode());return;}throw new RuntimeException('Expected rejection '.$code);}
class AccessClaimsFixture extends AgentSessionVerifier {
    public $claims;
    protected function request($authorization,$code=null){return $this->claims;}
}
$verifier=new AccessClaimsFixture();
$verifier->claims=['account'=>['id'=>71,'uid'=>'access_fixture','name'=>' Synthetic account '],'wechat_authenticated'=>false];
$identity=$verifier->verify('Bearer synthetic-never-persist');
accessCheck($identity['login_channel']==='other'&&$identity['ref']==='uid:access_fixture'&&$identity['name']==='Synthetic account','Business identity and display metadata must be verified');
accessReject(function()use($verifier){$verifier->verifyPaymentIdentity('Bearer synthetic-never-persist','code');},40100);
unset($verifier->claims['wechat_authenticated']);
accessCheck($verifier->verify('Bearer synthetic-never-persist')['login_channel']==='unknown','Missing history must remain unknown');
$verifier->claims['wechat_authenticated']='true';
accessReject(function()use($verifier){$verifier->verify('Bearer synthetic-never-persist');},50202);
$verifier->claims['wechat_authenticated']=true;
accessReject(function()use($verifier){$verifier->verifyPaymentIdentity('Bearer synthetic-never-persist','code');},50202);
$verifier->claims+=['appid'=>'wx1111111111111111','openid'=>'synthetic-openid'];
accessCheck($verifier->verifyPaymentIdentity('Bearer synthetic-never-persist','code')['openid']==='synthetic-openid','Payment requires verified WeChat and complete identity');
$verifier->claims['account']['id']='71';
accessReject(function()use($verifier){$verifier->verify('Bearer synthetic-never-persist');},50202);
$verifier->claims['account']['id']=71;
$verifier->claims['wechat_authenticated']=false;
putenv('SHOP_AGENT_CLIENT_ID=access-fixture');putenv('SHOP_WECHAT_APP_ID=wx1111111111111111');
// 基础安装夹具有固定ID样例；仅在上述专用测试库推进用户序列。
Db::query("SELECT setval(pg_get_serial_sequence('fa_user','id'), (SELECT COALESCE(MAX(id),0)+1 FROM fa_user), false)");
Db::startTrans();
try {
    $auth=new \app\common\library\Auth();$service=new AgentMemberService($verifier);
    try{$service->exchange('Bearer synthetic-never-persist',[],$auth);}
    catch(DomainException $error){throw new RuntimeException('Synthetic member registration: '.$auth->getError(),0,$error);}
    $uid=(int)$auth->id;
    accessCheck($uid>0,'Ordinary verified account must create an associated member');
    $before=Db::name('user')->where('id',$uid)->find();
    $service->exchange('Bearer synthetic-never-persist',[],$auth);
    accessCheck((int)$auth->id===$uid&&Db::name('shop_external_identity')->where('client_id','access-fixture')->count()===1,'Repeated exchange must reuse the same account');
    $after=Db::name('user')->where('id',$uid)->find();
    accessCheck($before['password']===$after['password']&&$before['salt']===$after['salt'],'Exchange must preserve existing credentials');
    $mapping=Db::name('shop_external_identity')->where('client_id','access-fixture')->find();
    accessCheck($mapping['external_account_id']==='71'&&$mapping['last_login_channel']==='other'&&(int)$mapping['last_seen_at']>0&&(int)$mapping['last_wechat_verified_at']===0,'Business login cannot manufacture WeChat proof');
    accessCheck(strpos(json_encode($mapping),'synthetic-never-persist')===false,'Bearer token must never enter identity metadata');
    $users=[['id'=>$uid]];(new MiniappUserAccessService())->decorateUsers($users);
    accessCheck($users[0]['account_source']==='小程序用户'&&$users[0]['login_method']==='其他登录'&&$users[0]['wechat_login_status']==='尚无微信登录验证记录','Admin projections must retain identity semantics');
    $verifier->claims['wechat_authenticated']=true;$service->exchange('Bearer synthetic-never-persist',[],$auth);
    $wechat=Db::name('shop_external_identity')->where('id',$mapping['id'])->find();
    accessCheck((int)$wechat['last_wechat_verified_at']>0,'Verified WeChat exchange must record its evidence');
    $verifier->claims['wechat_authenticated']=false;$service->exchange('Bearer synthetic-never-persist',[],$auth);
    $latest=Db::name('shop_external_identity')->where('id',$mapping['id'])->find();
    accessCheck($latest['last_login_channel']==='other'&&$latest['last_wechat_verified_at']===$wechat['last_wechat_verified_at'],'Latest business login must not erase earlier WeChat evidence');
    $verifier->claims['account']['id']=72;
    accessReject(function()use($service,$auth){$service->exchange('Bearer synthetic-never-persist',[],$auth);},40943);
    accessCheck(Db::name('shop_external_identity')->where('id',$mapping['id'])->value('external_account_id')==='71','Conflicting identity must not overwrite its binding');
    $paymentOnly=Db::name('user')->insertGetId(['username'=>'payment_identity_only','status'=>'normal']);
    Db::name('shop_miniapp_identity')->insert(['user_id'=>$paymentOnly,'app_id'=>'wx1111111111111111','openid'=>'synthetic-payment-only','createtime'=>time()]);
    $users=[['id'=>$paymentOnly]];(new MiniappUserAccessService())->decorateUsers($users);
    accessCheck($users[0]['payment_identity_bound']===true&&$users[0]['last_wechat_verified_at']===0,'Payment OpenID binding alone cannot invent a verified-login history');
} finally {Db::rollback();}
echo "Miniapp access passed: business/WeChat/payment identity, account reuse, credential preservation, metadata and conflicting-binding rejection.\n";
