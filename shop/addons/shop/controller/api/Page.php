<?php

namespace addons\shop\controller\api;

use addons\shop\model\Page as PageModel;

/**
 * 单页
 */
class Page extends Base
{

    protected $noNeedLogin = ['index', 'lists'];

    //单页详情
    public function index()
    {
        $diyname = $this->request->param('diyname');
        if ($diyname && !is_numeric($diyname)) {
            $page = PageModel::getByDiyname($diyname);
        } else {
            $id = $diyname ? $diyname : $this->request->param('id', '');
            $page = PageModel::get($id);
        }
        if (!$page || $page['status'] != 'normal') {
            $this->error('未找到指定的单页');
        }
        $page->setInc('views');
        $image = $page->getData('image');
        $fields = explode(',', 'id,title,content,image,description,status,createtime');
        $page = array_intersect_key($page->toArray(), array_flip($fields));
        $page['content'] = \addons\shop\library\Service::formatTplToUniapp($page['content']);
        $page['image'] = $image ? cdnurl($image, true) : $image;
        $this->success('获取成功', $page);
    }

    //单页列表
    public function lists()
    {
        $type = $this->request->param('type');

        $list = PageModel::field('id,title,description,status,createtime')
            ->where('status', 'normal')->where('type', $type)->order('createtime desc')->paginate(15);

        $this->success('获取成功', $list);
    }
}
