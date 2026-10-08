<?php

namespace addons\shop\model;

use think\Model;


class Collect extends Model
{

    // 表名
    protected $name = 'shop_collect';

    // 自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';

    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    protected $deleteTime = false;

    // 追加属性
    protected $append = [      
        'status_text'
    ];


    public function getStatusList()
    {
        return ['0' => __('Status 0'), '1' => __('Status 1')];
    }


    public function getStatusTextAttr($value, $data)
    {
        $value = $value ?: ($data['status'] ?? '');
        $list = $this->getStatusList();
        return $list[$value] ?? '';
    }

    /**
     * 添加收藏/取消收藏
     * @param [type] $user_id   
     * @param [type] $goods_id
     * @return true
     */
    public static function addOrCancel($user_id, $goods_id)
    {
        $data = self::where('user_id', $user_id)->where('goods_id', $goods_id)->find();
        //不存在，添加收藏
        if (!$data) {
            return (new self)->save([
                'user_id' => $user_id,
                'goods_id' => $goods_id
            ]);
        }
        if ($data->status == 1) { //已收藏，为取消
            $data->status = 0;
        } else { //已取消，添加收藏
            $data->status = 1;
        }
        return $data->save();
    }

    /**
     * 渲染收藏
     *
     * @param [type] $list
     * @param [type] $user_id  
     * @return void
     */
    public static function render($list, $user_id)
    {
        $data = self::where('user_id', $user_id)->where('status', 1)->select();
        $newData = [];
        foreach ($data as $item) {
            $newData[$item['goods_id']] = $item['status'];
        }
        foreach ($list as $res) {
            $res->isCollect = isset($newData[$res['id']]) ?? $newData[$res['id']]['status'];
        }
    }

    /**
     * 收藏列表
     *
     * @param [type] $param
     * @return \think\Paginator
     */
    public static function tableList($param)
    {
        $pageNum = 15;
        if (!empty($param['num'])) {
            $pageNum = $param['num'];
        }

        $list = self::with(['Goods' => function ($query) {
            $query->field('id,title,image,price,marketprice,description');
        }])
            ->field('id,goods_id,user_id,status,createtime')
            ->where(function ($query) use ($param) {

                $query->where('status', 1);

                if (!empty($param['user_id'])) {
                    $query->where('user_id', $param['user_id']);
                }
            })->order('createtime desc')->paginate($pageNum);


        return $list;
    }

    public function Goods()
    {
        return $this->belongsTo('Goods', 'goods_id', 'id', [], 'LEFT');
    }
}
