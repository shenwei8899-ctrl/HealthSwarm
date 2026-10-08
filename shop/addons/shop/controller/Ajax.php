<?php

namespace addons\shop\controller;

use addons\shop\model\Collect;
use addons\shop\model\Goods;

/**
 * Ajax控制器
 * Class Ajax
 * @package addons\shop\controller
 */
class Ajax extends Base
{

    protected $noNeedLogin = ["share"];

    /**
     * 添加取消收藏
     */
    public function collect()
    {
        if (!$this->auth->isLogin()) {
            $this->error("请登录后操作");
        }
        $goods_id = $this->request->post('goods_id');
        if (!$this->request->isPost()) {
            $this->error('请求错误');
        }
        if (!$goods_id) {
            $this->error('缺少参数！');
        }
        $data = (new Goods())->get($goods_id);
        if (!$data || $data['status'] != 'normal') {
            $this->error('收藏的商品已失效！');
        }
        $data = Collect::where('user_id', $this->auth->id)->where('goods_id', $goods_id)->find();
        //不存在，添加收藏
        if (!$data) {
            (new Collect())->save([
                'user_id'  => $this->auth->id,
                'goods_id' => $goods_id
            ]);
            $this->success('收藏成功');
        } else {
            $this->error('请勿重复收藏');
        }
    }

    /**
     * 微信公众号内分享
     */
    public function share()
    {
        $url = $this->request->param('url', '', 'trim');
        $js_sdk = new \addons\shop\library\Jssdk();
        $data = $js_sdk->getSignedPackage($url);
        $this->success('', '', $data);
    }

}
