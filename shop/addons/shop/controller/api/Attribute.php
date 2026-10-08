<?php

namespace addons\shop\controller\api;

use addons\shop\model\Attribute as AttributeModel;

/**
 * 分类属性
 */
class Attribute extends Base
{
    protected $noNeedLogin = ['*'];

    //属性列表
    public function index()
    {
        $category_id = $this->request->param('category_id');
        if (empty($category_id)) {
            $this->error('分类不能为空');
        }
        $list = (new AttributeModel())->with(['AttributeValue'])->where('category_id', $category_id)->where('is_search', 1)->select();
        $this->success('获取成功', $list);
    }
}
