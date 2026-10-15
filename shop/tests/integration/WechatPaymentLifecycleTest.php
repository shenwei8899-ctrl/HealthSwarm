<?php
$_SERVER['REMOTE_ADDR']='127.0.0.1';
require dirname(__DIR__).'/bootstrap.php';
set_exception_handler(function ($e) { fwrite(STDERR,(string)$e."\n"); exit(1); });
use think\Db;
use addons\shop\library\v5\{AddressService, CartService, CatalogService, CheckoutService, DomainException, IdempotencyService, PaymentService, WechatPaymentLifecycle};
use addons\shop\library\service\WechatPayService;

if (config('database.database')!=='healthflow_link_test' || getenv('HEALTHFLOW_RELEASE_TEST')!=='1') throw new RuntimeException('Run only in the explicitly isolated release test database');
function paymentAssert($ok,$message) { if (!$ok) throw new RuntimeException($message); }
function paymentReject($fn,$code) { try {$fn();} catch (DomainException $e) {paymentAssert($e->getCode()===$code,'Wrong rejection '.$e->getCode());return;} throw new RuntimeException('Expected rejection '.$code); }
class PaymentCreateDouble extends PaymentService {
    public $calls=0;
    protected function createGatewayPayment($sn,$uid,$openid,$url) {
        $this->calls++;
        $params=['timeStamp'=>'1','nonceStr'=>'synthetic','package'=>'prepay_id=synthetic','paySign'=>'not-a-real-signature'];
        Db::name('shop_payment_transaction')->where('channel_transaction_id','PREPAY:'.$sn)->update(['status'=>'PENDING','request_json'=>json_encode(['parameters'=>$params]),'updatetime'=>time()]);
        return ['parameters'=>$params];
    }
}
class PaymentQueryDouble extends WechatPaymentLifecycle {
    public $queries=[],$closes=[],$closeCalls=0;
    protected function queryGateway($sn) { $r=array_shift($this->queries); if ($r instanceof Throwable) throw $r; return $r ?? []; }
    protected function closeGateway($sn) { $this->closeCalls++; return array_shift($this->closes) ?? []; }
}
$suffix=bin2hex(random_bytes(6));
putenv('SHOP_WECHAT_APP_ID=wx1111111111111111'); putenv('SHOP_WECHAT_MCH_ID=synthetic-merchant');
$fakeKey=bin2hex(random_bytes(16)); putenv('SHOP_WECHAT_API_V2_KEY='.$fakeKey);
Db::startTrans();
try {
    $uid=Db::name('user')->insertGetId(['username'=>'payment_test_'.$suffix,'nickname'=>'Synthetic payment test','status'=>'normal']);
    Db::name('shop_miniapp_identity')->insert(['app_id'=>getenv('SHOP_WECHAT_APP_ID'),'openid'=>'synthetic-'.$suffix,'user_id'=>$uid,'createtime'=>time()]);
    $sku=(new CatalogService())->listProducts(['limit'=>1])['items'][0];
    Db::name('shop_goods_sku')->where('id',$sku['sku_id'])->update(['stocks'=>500,'reserved_stock'=>0]);
    $address=(new AddressService())->save($uid,['name'=>'TEST ONLY','phone'=>'13800000000','region'=>'上海市 徐汇区','detail'=>'TEST ONLY']);
    $creator=new PaymentCreateDouble(); $cart=new CartService(); $checkout=new CheckoutService();
    $make=function ($startPayment=true) use ($uid,$sku,$address,$creator,$cart,$checkout,$suffix) {
        $basket=$cart->add($uid,$sku['sku_id'],1); $line=$basket['items'][0];
        $quote=$checkout->preview($uid,['source_type'=>'cart','source_ref'=>(string)$uid,'source_version'=>1,'address_id'=>$address['id'],'cart_items'=>[['cart_item_id'=>$line['cart_item_id'],'version'=>$line['version']]]]);
        $order=$checkout->createOrder($uid,['checkout_token'=>$quote['checkout_token']],'payment-test-'.$suffix);
        if ($startPayment) $creator->createWechat($uid,$order['order_sn'],'ignored','payment-test-'.$suffix);
        return $order['order_sn'];
    };
    $response=function ($sn,$state) { return ['return_code'=>'SUCCESS','result_code'=>'SUCCESS','appid'=>getenv('SHOP_WECHAT_APP_ID'),'mch_id'=>getenv('SHOP_WECHAT_MCH_ID'),'out_trade_no'=>WechatPayService::gatewayOrderSn($sn),'total_fee'=>(int)round((float)Db::name('shop_order')->where('order_sn',$sn)->value('saleamount')*100),'trade_state'=>$state,'transaction_id'=>'synthetic-'.substr(hash('sha256',$sn),0,24)]; };
    $open=$make(false);
    $token=Db::name('shop_order_ext')->where('order_sn',$open)->value('checkout_token_hash');
    Db::name('shop_inventory_reservation')->where('source_ref',$token)->update(['expires_at'=>time()-1]);
    (new \addons\shop\library\v5\JobRunner())->expireReservations();
    paymentAssert(Db::name('shop_inventory_reservation')->where('source_ref',$token)->value('status')==='active','Reservation expiry cannot race an existing open order before its close transaction');
    $cancel=function ($sn,$key) use ($uid) {
        paymentAssert(\app\common\library\Auth::instance()->direct($uid),'Synthetic member authentication: '.\app\common\library\Auth::instance()->getError());
        $r=\think\Request::create('http://localhost/api/v1/commerce/orders/'.$sn.'/cancel','POST',[],[],[],['REMOTE_ADDR'=>'127.0.0.1','HTTP_IDEMPOTENCY_KEY'=>$key]);
        $r->controller('api.v1.commerce_order')->action('cancel')->route(['order_sn'=>$sn]);
        (new ReflectionProperty(\think\Request::class,'instance'))->setValue(null,$r);
        return (new \addons\shop\controller\api\v1\CommerceOrder($r))->cancel()->getData();
    };

    $sn=$make(); $calls=$creator->calls; $creator->createWechat($uid,$sn,'ignored','retry');
    paymentAssert($creator->calls===$calls,'Concurrent/repeated payment must reuse the prepay');
    paymentAssert(strlen($sn)>32 && strlen(WechatPayService::gatewayOrderSn($sn))===32,'Platform order retained; WeChat number fits its 32-character limit');
    $life=new PaymentQueryDouble(); $paid=$response($sn,'SUCCESS'); $life->queries=[$paid];
    paymentAssert($life->reconcile($sn,false,$uid)==='paid','Active query recovers a lost paid callback');
    paymentAssert((int)Db::name('shop_order')->where('order_sn',$sn)->value('paystate')===1,'Paid state persisted');
    $stock=Db::name('shop_goods_sku')->where('id',$sku['sku_id'])->value('stocks');
    Db::name('shop_order')->where('order_sn',$sn)->update(['orderstate'=>3,'shippingstate'=>2]);
    Db::name('shop_order_ext')->where('order_sn',$sn)->update(['business_status'=>'completed','fulfillment_status'=>'received']);
    WechatPayService::confirmPaidOrder($paid);
    paymentAssert(Db::name('shop_order_ext')->where('order_sn',$sn)->value('business_status')==='completed','Late real callback cannot regress completed fulfillment');
    paymentAssert(Db::name('shop_goods_sku')->where('id',$sku['sku_id'])->value('stocks')===$stock,'Duplicate success does not consume stock again');

    $sn=$make(); $life=new PaymentQueryDouble(); $life->queries=[$response($sn,'NOTPAY')]; $life->closes=[['return_code'=>'SUCCESS','result_code'=>'SUCCESS']];
    paymentAssert($life->reconcile($sn,true,$uid)==='closed' && $life->closeCalls===1,'Cancellation closes an unpaid gateway order');
    $result=$cancel($sn,'closed-'.$suffix); paymentAssert($result['code']===0,'Confirmed close allows real cancellation endpoint');
    paymentAssert((int)Db::name('shop_order')->where('order_sn',$sn)->value('orderstate')===1,'Cancelled state persisted');

    $sn=$make(); $life=new PaymentQueryDouble(); $life->queries=[$response($sn,'NOTPAY'),$response($sn,'SUCCESS')]; $life->closes=[['return_code'=>'SUCCESS','result_code'=>'FAIL','err_code'=>'ORDERPAID']];
    paymentAssert($life->reconcile($sn,true,$uid)==='paid','Payment that wins the close race is confirmed, not cancelled');

    $sn=$make(); $life=new PaymentQueryDouble(); $life->queries=[$response($sn,'USERPAYING')];
    paymentAssert($life->reconcile($sn,true,$uid)==='unknown' && $life->closeCalls===0,'USERPAYING cannot release reservations');
    $before=Db::name('shop_goods_sku')->where('id',$sku['sku_id'])->value('reserved_stock');
    putenv('SHOP_WECHAT_API_V2_KEY='); // The actual endpoint must not call a real gateway in this test.
    $result=$cancel($sn,'pending-'.$suffix);
    paymentAssert($result['code']===40936,'Direct API cancellation rejects pending payment even if UI is bypassed');
    paymentAssert((int)Db::name('shop_order')->where('order_sn',$sn)->value('orderstate')===0 && Db::name('shop_goods_sku')->where('id',$sku['sku_id'])->value('reserved_stock')===$before,'Unknown cancellation preserves order and stock');
    putenv('SHOP_WECHAT_API_V2_KEY='.$fakeKey);

    $sn=$make(); $life=new PaymentQueryDouble(); $absent=['return_code'=>'SUCCESS','result_code'=>'FAIL','err_code'=>'ORDERNOTEXIST']; $life->queries=[$absent];
    paymentAssert($life->reconcile($sn,true,$uid)==='unknown','Fresh missing order stays protected during create grace');
    Db::name('shop_payment_record')->where('order_sn',$sn)->update(['createtime'=>time()-180,'updatetime'=>time()-180]); $life->queries=[$absent];
    paymentAssert($life->reconcile($sn,true,$uid)==='closed','Old confirmed missing payment can release the cancelled intent');

    $sn=$make(); $life=new PaymentQueryDouble(); $wrong=$response($sn,'SUCCESS'); $wrong['total_fee']++; $life->queries=[$wrong];
    paymentAssert($life->reconcile($sn,true,$uid)==='unknown','Mismatched amount cannot confirm or close');
    $wrong=$response($sn,'SUCCESS'); $wrong['mch_id']='wrong-merchant'; $life->queries=[$wrong];
    paymentAssert($life->reconcile($sn,true,$uid)==='unknown','Mismatched merchant cannot confirm or close');
    $life->queries=[new RuntimeException('Synthetic timeout')]; paymentAssert($life->reconcile($sn,true,$uid)==='unknown','Query timeout preserves pending state');
    paymentReject(function () use ($life,$sn,$uid) {$life->reconcile($sn,true,$uid+1000000);},40409);

    $sn=$make(); $idem=new IdempotencyService(); $fn=function () use ($creator,$uid,$sn) {return $creator->createWechat($uid,$sn,'ignored','same-intent');};
    $idem->run('payment-replay-test','test:'.$uid,$suffix,['order_sn'=>$sn],$fn,1800,false);
    Db::name('shop_order')->where('order_sn',$sn)->update(['expiretime'=>time()-1]);
    paymentReject(function () use ($idem,$uid,$suffix,$sn,$fn) {$idem->run('payment-replay-test','test:'.$uid,$suffix,['order_sn'=>$sn],$fn,1800,false);},40924);
    Db::rollback();
    paymentAssert(!Db::name('user')->where('username','payment_test_'.$suffix)->find(),'Synthetic transactions rolled back');
    echo "WeChat lifecycle passed: mapped order number, prepay reuse, lost callback, duplicate late callback, close race, API cancellation guard, missing-order grace, identity/amount checks, timeout and expired replay. No real gateway or payment used.\n";
} catch (Throwable $e) { Db::rollback(); throw $e; }
