<?php

namespace addons\shop\model;

use think\Model;


class Navigation extends Model
{

    // 表名
    protected $name = 'shop_navigation';

    // 自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';

    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    protected $deleteTime = false;

    // 追加属性
    protected $append = [

    ];

    public function getImageAttr($value)
    {
        if (strpos($value, '/') === false) {
            return $value;
        } else {
            return cdnurl($value, true);
        }
    }

    public static function tableList()
    {
        return self::where('switch', 1)->field('name,image,path,size')->order('weigh desc')->select();
    }

}
