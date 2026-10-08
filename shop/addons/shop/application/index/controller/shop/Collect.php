<?php

namespace app\index\controller\shop;

use app\common\controller\Frontend;
use think\Db;

class Collect extends Frontend
{

    protected $layout = 'default';
    protected $noNeedLogin = [];
    protected $noNeedRight = ['*'];

    /**
     * 我的收藏
     */
    public function index()
    {
        $collectList = \addons\shop\model\Collect::with('goods')->where('user_id', $this->auth->id)->order('id', 'desc')->paginate(10);
        $this->view->assign('collectList', $collectList);
        $this->view->assign('title', "我的收藏");
        return $this->view->fetch();
    }

    /**
     * 移除收藏
     */
    public function del()
    {
        $id = $this->request->post("id/d");
        $collectInfo = \addons\shop\model\Collect::get($id);
        if (!$collectInfo) {
            $this->error('未找到相关信息');
        }
        if ($collectInfo['user_id'] != $this->auth->id) {
            $this->error('无法进行越权操作');
        }
        Db::startTrans();
        try {
            $collectInfo->delete();
            Db::commit();
        } catch (\Exception $e) {
            Db::rollback();
            $this->error('删除失败');
        }
        $this->success();
    }
}
