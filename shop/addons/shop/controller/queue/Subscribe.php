<?php

namespace addons\shop\controller\queue;

use think\Controller;
use think\queue\Job;

class Subscribe extends Controller
{

    public function fire(Job $job, $param)
    {
        if ($job->attempts() > 3) {
            //通过这个方法可以检查这个任务已经重试了几次了
            $job->delete();
            return;
        }
        extract($param);
        $event = $event ?? '';
        $order_sn = $order_sn ?? '';
        // 推送消息
        $result = (new \addons\shop\model\TemplateMsg)->getSendOrderData($event, $order_sn);
        if ($result) {
            //如果任务执行成功后 记得删除任务，不然这个任务会重复执行，直到达到最大重试次数后失败后，执行failed方法
            $job->delete();
            print("成功\n");
        } else {
            // 也可以重新发布这个任务
            $delay = 0;
            $job->release($delay); //$delay为延迟时间
            print("失败\n");
        }
    }

    public function failed($data)
    {
        // ...任务达到最大重试次数后，失败了
        print("达到最大重度次数\n");
    }
}
