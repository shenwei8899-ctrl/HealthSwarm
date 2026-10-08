<?php

namespace addons\shop\taglib;

use fast\Random;
use think\Cache;
use think\template\TagLib;

class Shop extends TagLib
{

    /**
     * 定义标签列表
     */
    protected $tags = [
        // 标签定义： attr 属性列表 close 是否闭合（0 或者1 默认1） alias 标签别名 level 嵌套层次
        'channel'       => ['attr' => 'name', 'close' => 0],
        'block'         => ['attr' => 'id,name', 'close' => 0],
        'config'        => ['attr' => 'name', 'close' => 0],
        'page'          => ['attr' => 'name', 'close' => 0],
        'nav'           => ['attr' => 'name,maxlevel,condition,cache', 'close' => 0],
        'menu'          => ['attr' => 'name,maxlevel,condition,cache', 'close' => 0],
        'execute'       => ['attr' => 'sql', 'close' => 0],
        'query'         => ['attr' => 'id,empty,key,mod,sql,cache', 'close' => 1],
        'blocklist'     => ['attr' => 'id,row,limit,empty,key,mod,cache,orderby,orderway,condition,name,paginate', 'close' => 1],
        'menulist'      => ['attr' => 'id,row,limit,empty,key,mod,cache,orderby,orderway,condition,type,typeid,fragment,paginate', 'close' => 1],
        'commentlist'   => ['attr' => 'id,row,limit,empty,key,mod,cache,orderby,orderway,condition,pid,fragment,paginate', 'close' => 1],
        'breadcrumb'    => ['attr' => 'id,empty,key,mod', 'close' => 1],
        'goodslist'     => ['attr' => 'id,row,limit,empty,key,mod,cache,orderby,orderway,condition,type,field,flag,category,paginate', 'close' => 1],
        'catelist'      => ['attr' => 'id,row,limit,empty,key,mod,cache,orderby,orderway,condition,type,typeid,field', 'close' => 1],
        'searchloglist' => ['attr' => 'id,row,limit,empty,key,mod,cache,orderby,orderway,condition', 'close' => 1],
        'spagelist'   => ['attr' => 'id,row,limit,empty,key,mod,cache,orderby,orderway,imgwidth,imgheight,condition,type,paginate', 'close' => 1],
        'spageinfo'   => ['attr' => 'id,sid,empty,cache,imgwidth,imgheight,orderby,orderway,condition', 'close' => 1],
    ];

    public function tagBreadcrumb($tag, $content)
    {
        $id = $tag['id'] ?? 0;
        $empty = $tag['empty'] ?? '';
        $key = !empty($tag['key']) ? $tag['key'] : 'i';
        $mod = $tag['mod'] ?? '2';

        $var = Random::alnum(10);
        $parse = '<?php ';
        $parse .= '$__' . $var . '__ = \addons\shop\model\Category::getBreadcrumb($__category__??[], $__goods__??[], $__page__??[]);';
        $parse .= ' ?>';
        $parse .= '{volist name="$__' . $var . '__" id="' . $id . '" empty="' . $empty . '" key="' . $key . '" mod="' . $mod . '"}';
        $parse .= $content;
        $parse .= '{/volist}';
        $parse .= '{php}$__LASTLIST__=$__' . $var . '__;{/php}';
        return $parse;
    }

    public function tagExecute($tag, $content)
    {
        $sql = $tag['sql'] ?? '';
        $bind = $tag['bind'] ?? '';
        $bind = explode(',', $bind);
        $sql = addslashes($sql);
        $parse = '<?php ';
        $parse .= '\think\Db::execute(\'' . $sql . '\', ' . json_encode($bind) . ');';
        $parse .= ' ?>';
        return $parse;
    }

    public function tagQuery($tag, $content)
    {
        $id = $tag['id'] ?? 'item';
        $empty = $tag['empty'] ?? '';
        $key = !empty($tag['key']) ? $tag['key'] : 'i';
        $mod = $tag['mod'] ?? '2';
        $params = [];
        foreach ($tag as $k => & $v) {
            $origin = $v;
            if (in_array($k, ['bind'])) {
                $this->autoBuildVar($v);
            }
            $v = $origin == $v ? '"' . $v . '"' : $v;
            $params[] = '"' . $k . '"=>' . $v;
        }
        $var = Random::alnum(10);
        $parse = '<?php ';
        $parse .= '$__' . $var . '__ = \addons\shop\model\Goods::getQueryList([' . implode(',', $params) . ']);';
        $parse .= ' ?>';
        $parse .= '{volist name="$__' . $var . '__" id="' . $id . '" empty="' . $empty . '" key="' . $key . '" mod="' . $mod . '"}';
        $parse .= $content;
        $parse .= '{/volist}';
        $parse .= '{php}$__LASTLIST__=$__' . $var . '__;{/php}';
        return $parse;
    }

    public function tagPage($tag)
    {
        return '{$__page__.' . $tag['name'] . '}';
    }

    public function tagBlock($tag)
    {
        return \addons\shop\model\Block::getBlockContent($tag);
    }

    public function tagNav($tag)
    {
        $params = [];
        foreach ($tag as $k => & $v) {
            $origin = $v;
            if (in_array($k, ['condition'])) {
                $this->autoBuildVar($v);
            }
            $v = $origin == $v ? '"' . $v . '"' : $v;
            $params[] = '"' . $k . '"=>' . $v;
        }
        $var = Random::alnum(10);
        $parse = '<?php ';
        $parse .= '$__' . $var . '__ = \addons\shop\model\Category::getNav(isset($__CATEGORY__)?$__CATEGORY__:[], [' . implode(',', $params) . ']);';
        $parse .= ' ?>';
        $parse .= '{:$__' . $var . '__}';
        return $parse;
    }

    public function tagMenu($tag)
    {
        $params = [];
        foreach ($tag as $k => & $v) {
            $origin = $v;
            if (in_array($k, ['condition'])) {
                $this->autoBuildVar($v);
            }
            $v = $origin == $v ? '"' . $v . '"' : $v;
            $params[] = '"' . $k . '"=>' . $v;
        }
        $var = Random::alnum(10);
        $parse = '<?php ';
        $parse .= '$__' . $var . '__ = \addons\shop\model\Menu::getMenu([' . implode(',', $params) . ']);';
        $parse .= ' ?>';
        $parse .= '{:$__' . $var . '__}';
        return $parse;
    }

    public function tagBlocklist($tag, $content)
    {
        $id = $tag['id'];
        $empty = $tag['empty'] ?? '';
        $key = !empty($tag['key']) ? $tag['key'] : 'i';
        $mod = $tag['mod'] ?? '2';
        $params = [];
        foreach ($tag as $k => & $v) {
            $origin = $v;
            if (in_array($k, ['condition'])) {
                $this->autoBuildVar($v);
            }
            $v = $origin == $v ? '"' . $v . '"' : $v;
            $params[] = '"' . $k . '"=>' . $v;
        }
        $var = Random::alnum(10);
        $parse = '<?php ';
        $parse .= '$__' . $var . '__ = \addons\shop\model\Block::getBlockList([' . implode(',', $params) . ']);';
        $parse .= ' ?>';
        $parse .= '{volist name="$__' . $var . '__" id="' . $id . '" empty="' . $empty . '" key="' . $key . '" mod="' . $mod . '"}';
        $parse .= $content;
        $parse .= '{/volist}';
        $parse .= '{php}$__LASTLIST__=$__' . $var . '__;{/php}';
        return $parse;
    }

    public function tagGoodslist($tag, $content)
    {
        $id = $tag['id'];
        $empty = $tag['empty'] ?? '';
        $key = !empty($tag['key']) ? $tag['key'] : 'i';
        $mod = $tag['mod'] ?? '2';
        $params = [];
        foreach ($tag as $k => & $v) {
            $origin = $v;
            if (in_array($k, ['category', 'condition', 'tags'])) {
                $this->autoBuildVar($v);
            }
            $v = $origin == $v ? '"' . $v . '"' : $v;
            $params[] = '"' . $k . '"=>' . $v;
        }
        $var = Random::alnum(10);
        $parse = '<?php ';
        $parse .= '$__' . $var . '__ = \addons\shop\model\Goods::getGoodsList([' . implode(',', $params) . ']);';
        $parse .= ' ?>';
        $parse .= '{volist name="$__' . $var . '__" id="' . $id . '" empty="' . $empty . '" key="' . $key . '" mod="' . $mod . '"}';
        $parse .= $content;
        $parse .= '{/volist}';
        $parse .= '{php}$__LASTLIST__=$__' . $var . '__;{/php}';
        return $parse;
    }

    /**
     * 栏目标签
     * @param array  $tag
     * @param string $content
     * @return string
     */
    public function tagCatelist($tag, $content)
    {
        $id = $tag['id'];
        $empty = $tag['empty'] ?? '';
        $key = !empty($tag['key']) ? $tag['key'] : 'i';
        $mod = $tag['mod'] ?? '2';
        $params = [];
        foreach ($tag as $k => & $v) {
            $origin = $v;
            if (in_array($k, ['typeid', 'model', 'condition', 'special'])) {
                $this->autoBuildVar($v);
            }
            $v = $origin == $v ? '"' . $v . '"' : $v;
            $params[] = '"' . $k . '"=>' . $v;
        }
        $var = Random::alnum(10);
        $parse = '<?php ';
        $parse .= '$__' . $var . '__ = \addons\shop\model\Category::getCategoryList([' . implode(',', $params) . ']);';
        $parse .= ' ?>';
        $parse .= '{volist name="$__' . $var . '__" id="' . $id . '" empty="' . $empty . '" key="' . $key . '" mod="' . $mod . '"}';
        $parse .= $content;
        $parse .= '{/volist}';
        $parse .= '{php}$__LASTLIST__=$__' . $var . '__;{/php}';

        return $parse;
    }

    /**
     * 栏目标签
     * @param array  $tag
     * @param string $content
     * @return string
     */
    public function tagMenulist($tag, $content)
    {
        $id = $tag['id'];
        $empty = $tag['empty'] ?? '';
        $key = !empty($tag['key']) ? $tag['key'] : 'i';
        $mod = $tag['mod'] ?? '2';
        $params = [];
        foreach ($tag as $k => & $v) {
            $origin = $v;
            if (in_array($k, ['typeid', 'model', 'condition', 'special'])) {
                $this->autoBuildVar($v);
            }
            $v = $origin == $v ? '"' . $v . '"' : $v;
            $params[] = '"' . $k . '"=>' . $v;
        }
        $var = Random::alnum(10);
        $parse = '<?php ';
        $parse .= '$__' . $var . '__ = \addons\shop\model\Menu::getMenuList([' . implode(',', $params) . ']);';
        $parse .= ' ?>';
        $parse .= '{volist name="$__' . $var . '__" id="' . $id . '" empty="' . $empty . '" key="' . $key . '" mod="' . $mod . '"}';
        $parse .= $content;
        $parse .= '{/volist}';
        $parse .= '{php}$__LASTLIST__=$__' . $var . '__;{/php}';

        return $parse;
    }

    /**
     * 搜索记录列表
     * @param array  $tag
     * @param string $content
     * @return string
     */
    public function tagSearchloglist($tag, $content)
    {
        $id = $tag['id'];
        $empty = $tag['empty'] ?? '';
        $key = !empty($tag['key']) ? $tag['key'] : 'i';
        $mod = $tag['mod'] ?? '2';
        $params = [];
        foreach ($tag as $k => & $v) {
            $origin = $v;
            if (in_array($k, ['pid', 'model', 'condition'])) {
                $this->autoBuildVar($v);
            }
            $v = $origin == $v ? '"' . $v . '"' : $v;
            $params[] = '"' . $k . '"=>' . $v;
        }
        $var = Random::alnum(10);
        $parse = '<?php ';
        $parse .= '$__' . $var . '__ = \addons\shop\model\SearchLog::getSearchlogList([' . implode(',', $params) . ']);';
        $parse .= ' ?>';
        $parse .= '{volist name="$__' . $var . '__" id="' . $id . '" empty="' . $empty . '" key="' . $key . '" mod="' . $mod . '"}';
        $parse .= $content;
        $parse .= '{/volist}';
        $parse .= '{php}$__LASTLIST__=$__' . $var . '__;{/php}';

        return $parse;
    }

    public function tagSpagelist($tag, $content)
    {
        $id = $tag['id'];
        $empty = $tag['empty'] ?? '';
        $key = !empty($tag['key']) ? $tag['key'] : 'i';
        $mod = $tag['mod'] ?? '2';

        $params = [];
        foreach ($tag as $k => & $v) {
            $origin = $v;
            if (in_array($k, ['condition'])) {
                $this->autoBuildVar($v);
            }
            $v = $origin == $v ? '"' . $v . '"' : $v;
            $params[] = '"' . $k . '"=>' . $v;
        }
        $var = Random::alnum(10);
        $parse = '<?php ';
        $parse .= '$__' . $var . '__ = \addons\shop\model\Page::getPageList([' . implode(',', $params) . ']);';
        $parse .= ' ?>';
        $parse .= '{volist name="$__' . $var . '__" id="' . $id . '" empty="' . $empty . '" key="' . $key . '" mod="' . $mod . '"}';
        $parse .= $content;
        $parse .= '{/volist}';
        $parse .= '{php}$__LASTLIST__=$__' . $var . '__;{/php}';
        return $parse;
    }

    public function tagSpageinfo($tag, $content)
    {
        $id = $tag['id'];
        $empty = isset($tag['empty']) ? $tag['empty'] : '';

        $params = [];
        foreach ($tag as $k => & $v) {
            $origin = $v;
            if (in_array($k, ['condition'])) {
                $this->autoBuildVar($v);
            }
            $v = $origin == $v ? '"' . $v . '"' : $v;
            $params[] = '"' . $k . '"=>' . $v;
        }
        $parse = '<?php ';
        $parse .= '$' . $id . ' = \addons\shop\model\Page::getPageInfo([' . implode(',', $params) . ']);';
        $parse .= ' ?>';
        $parse .= '{if $' . $id . '}';
        $parse .= $content;
        $parse .= '{else /}';
        $parse .= '{$' . $empty . '}';
        $parse .= '{/if}';
        return $parse;
    }

    public function tagConfig($tag)
    {
        $name = $tag['name'];
        $parse = '{$Think.config.' . $name . '}';
        return $parse;
    }

    public function autoBuildVar(&$name)
    {
        //如果是字符串则特殊处理
        if (preg_match("/^('|\")(.*)('|\")\$/i", $name, $matches)) {
            $quote = $matches[1] == '"' ? "'" : '"';
            $name = $quote . $matches[2] . $quote;
            return $name;
        }
        return parent::autoBuildVar($name);
    }
}
