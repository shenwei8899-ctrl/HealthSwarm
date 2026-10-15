<?php
namespace addons\shop\controller\api\v1;
use addons\shop\library\v5\DomainException;
use addons\shop\library\v5\IdempotencyService;
use addons\shop\library\v5\PaymentService;
use think\Db;

class LocalTestPayment extends Base
{
    /** 三重限制的本地测试通道，不能用于实际商城付款。 */
    public static function enabled()
    {
        return config('database.database')==='healthflow_link_test' && getenv('HEALTHFLOW_LOCAL_TEST_PAYMENT')==='1' && in_array(\think\Request::instance()->server('REMOTE_ADDR'),['127.0.0.1','::1'],true);
    }
    public function pay($order_sn=null)
    {
        $order_sn=$order_sn??$this->request->route('order_sn');
        return $this->execute(function () use ($order_sn) {
            $this->requireMethod('POST');
            if (!self::enabled()) throw new DomainException('本地测试支付未启用',40301,403);
            $uid=$this->userId();
            return (new IdempotencyService())->run('local-test.payment','miniapp:'.$uid,$this->request->header('idempotency-key'),['order_sn'=>$order_sn],function () use ($uid,$order_sn) {
                Db::startTrans();
                try {
                    $order=Db::name('shop_order')->where('order_sn',$order_sn)->where('user_id',$uid)->lock(true)->find();
                    if (!$order) throw new DomainException('订单不存在',40409,404);
                    if ($order['order_type']!=='normal' || ((int)$order['paystate']===0 && ((int)$order['orderstate']!==0 || (int)$order['expiretime']<=time()))) throw new DomainException('订单已失效',40924,409);
                    $payment=Db::name('shop_payment_record')->where('order_sn',$order_sn)->order('id','desc')->find();
                    if ($payment && $payment['channel']!=='local_test') throw new DomainException('已有实际支付意图，不能改用本地测试付款',40938,409);
                    $confirmed=(new PaymentService())->onPaid($order_sn,(int)round((float)$order['saleamount']*100),'LOCAL-TEST-'.$order_sn,'local-test','local_test');
                    if (!$confirmed) throw new DomainException('订单缺少付款快照，不能确认测试支付',40917,409);
                    Db::commit(); return ['order_sn'=>$order_sn,'status'=>'paid','channel'=>'local_test','real_charge'=>false];
                } catch (\Throwable $e) { Db::rollback(); throw $e; }
            });
        });
    }
}
