<?php

namespace addons\shop\model;

use think\Model;
use addons\shop\model\Order;
use addons\third\model\Third;
use addons\shop\library\message\Service;
use addons\shop\model\SubscribeLog;
use think\Queue;

class TemplateMsg extends Model
{

    // 表名
    protected $name = 'shop_template_msg';

    // 自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';

    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    protected $deleteTime = false;

    // 追加属性
    protected $append = [];

    public static function getTplIds()
    {
        return self::where('switch', 1)->where('type', 2)->column('tpl_id');
    }

    //获取发送模板消息的数据【付款成功】【商城发货通知】【退款通知】【售后回复】
    public static function sendTempMsg($event, $order_sn)
    {
        try {
            $config = get_addon_config('shop');
            if ($config['sendnoticemode'] == 'queue') {
                if (extension_loaded('redis') && class_exists('\think\Queue') && config('queue.connector') == 'redis') {
                    //使用队列发送
                    Queue::push('addons\shop\controller\queue\Subscribe', ['event' => $event, 'order_sn' => $order_sn], 'shopSubscribeQueue');
                }
            } elseif ($config['sendnoticemode'] == 'async') {
                //异步并发发送
                self::getSendOrderData($event, $order_sn);
            }
        } catch (\Exception $e) {
        }
        return true;
    }

    /**
     * @ 获取数据发送
     * @param $event
     * @param $order_sn
     * @return bool
     */
    public static function getSendOrderData($event, $order_sn)
    {
        try {
            //type 1=公众号,2=小程序,3=邮箱,4=短信
            $temps = self::where('event', $event)->where('switch', 1)->order('id asc')->column('*', 'type');
            //找订单
            $order = Order::field('o.*,u.mobile,u.email,u.nickname')
                ->alias('o')
                ->join('user u', 'u.id=o.user_id')
                ->where('order_sn', $order_sn)
                ->find();

            self::toSend($order, $temps);
        } catch (\Exception $e) {
            if (config('app_debug')) {
                \think\Log::write("Line:" . $e->getLine() . " Code:" . $e->getCode() . " Message:" . $e->getMessage() . " File:" . $e->getFile());
            }
            return false;
        }
        return true;
    }

    //去发送
    protected static function toSend($order, $temps)
    {
        $result = false;
        foreach ($temps as $tp) {
            switch ($tp['type']) {
                case 1:
                    //是否有openID
                    if (!empty($order['openid'])) {
                        $result = self::assembleMpData($order, $tp);
                    }
                    break;
                case 2:
                    //是否有openID
                    if (!empty($order['openid'])) {
                        //是否订阅有
                        $subscribe = SubscribeLog::where('order_sn', $order['order_sn'])->where('tpl_id', $tp['tpl_id'])->where('status', 0)->find();
                        if (!empty($subscribe)) {
                            $result = self::assembleMiniData($order, $tp);
                            $subscribe->status = 1;
                            $subscribe->save();
                        }
                    }
                    break;
                case 3:
                    if (!empty($order['email'])) {
                        $result = self::assembleMEData($order, $tp);
                    }
                    break;
                case 4:
                    if (!empty($order['mobile'])) {
                        $result = self::assembleMEData($order, $tp);
                    }
                    break;
            }
            \think\Log::record($result);
            $result && Service::send($tp['type'], $result);
        }
    }

    //组装公众号模板数据
    protected static function assembleMpData($param, $temp)
    {
        $data = self::prepareData($param, $temp);
        $templateData = [
            'touser'      => $param['openid'],
            'template_id' => $temp['tpl_id'],
            'data'        => $data
        ];
        if (strpos($temp['page'], 'http') !== false) {
            $templateData['url'] = $temp['page'];
        } else {
            $config = get_addon_config('shop');
            $templateData['miniprogram'] = [
                "appid"    => $config['wx_appid'],
                "pagepath" => $temp['page']
            ];
        }
        return $templateData;
    }

    //组装小程序模板数据
    protected static function assembleMiniData($param, $temp)
    {
        $data = self::prepareData($param, $temp);
        return [
            'touser'      => $param['openid'],
            'template_id' => $temp['tpl_id'],
            'page'        => $temp['page'],
            'data'        => $data
        ];
    }

    //组装邮箱，短信模板数据
    protected static function assembleMEData($param, $temp)
    {
        $data = self::prepareData($param, $temp);

        $msg = $temp['extend'];
        //替换内容中的变量 ${变量名}
        $msg = preg_replace_callback('/\$\{(.*?)\}/i', function ($matches) use ($data) {
            return $data[$matches[1]] ?? '';
        }, $msg);
        return [
            'template_id' => $temp['tpl_id'],
            'mobile'      => $param['mobile'],
            'email'       => $param['email'],
            'nickname'    => $param['nickname'],
            'title'       => $temp['title'],
            'message'     => $msg,
            'data'        => $data,
        ];
    }

    //准备数据
    protected static function prepareData($param, $temp)
    {
        $msg = $temp['extend'];
        $temp['content'] = is_array($temp['content']) ? $temp['content'] : (array)json_decode($temp['content'], true);
        $data = [];
        foreach ($temp['content'] as $res) {
            $value = $res['value'];
            $value = str_replace('.DATA}}', '', str_replace('{{', '', $value));
            if ($value) {
                $data[$value] = $res['key'] != 'diy_text' && isset($param[$res['key']]) ? $param[$res['key']] : $res['def_val'];
                //如果为时间字段且为数字则做转换
                if (is_numeric($data[$value]) && $data[$value] && preg_match("/([a-z]+)time\$/", $res['key'])) {
                    $data[$value] = date("Y-m-d H:i:s", $data[$value]);
                }
            }
        }
        return $data;
    }
}
