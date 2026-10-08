<?php

namespace addons\shop\library;

use addons\shop\library\aip\AipContentCensor;
use addons\shop\library\aip\AipNlp;
use addons\shop\library\SensitiveHelper;
use addons\shop\library\VicWord;
use think\View;

class Service
{

    /**
     * 检测内容是否合法
     * @param string $content 检测内容
     * @param string $type    类型
     * @return bool
     */
    public static function isContentLegal($content, $type = null)
    {
        $config = get_addon_config('shop');
        $type = is_null($type) ? $config['audittype'] : $type;
        if ($type == 'local') {
            // 敏感词过滤
            $handle = SensitiveHelper::init()->setTreeByFile(ADDON_PATH . 'shop/data/words.dic');
            //首先检测是否合法
            $isLegal = $handle->islegal($content);
            return $isLegal ? true : false;
        } elseif ($type == 'baiduyun') {
            $client = new AipContentCensor($config['aip_appid'], $config['aip_apikey'], $config['aip_secretkey']);
            $result = $client->textCensorUserDefined($content);
            if (!isset($result['conclusionType']) || $result['conclusionType'] > 1) {
                return false;
            }
        }
        return true;
    }

    /**
     * 获取标题的关键字
     * @param $title
     * @return array
     */
    public static function getContentTags($title)
    {
        $arr = [];
        $config = get_addon_config('shop');
        if ($config['nlptype'] == 'local') {
            !defined('_VIC_WORD_DICT_PATH_') && define('_VIC_WORD_DICT_PATH_', ADDON_PATH . 'shop/data/dict.json');
            $handle = new VicWord('json');
            $result = $handle->getAutoWord($title);
            foreach ($result as $index => $item) {
                $arr[] = $item[0];
            }
        } else {
            $client = new AipNlp($config['aip_appid'], $config['aip_apikey'], $config['aip_secretkey']);
            $result = $client->lexer($title);
            if (isset($result['items'])) {
                foreach ($result['items'] as $index => $item) {
                    if (!in_array($item['pos'], ['v', 'vd', 'nd', 'a', 'ad', 'an', 'd', 'm', 'q', 'r', 'p', 'c', 'u', 'xc', 'w'])) {
                        $arr[] = $item['item'];
                    }
                }
            }
        }
        foreach ($arr as $index => $item) {
            if (mb_strlen($item) == 1) {
                unset($arr[$index]);
            }
        }
        return array_filter(array_unique($arr));
    }

    /**
     * 内容关键字自动加链接
     */
    public static function autolinks($value)
    {
        $links = [];

        $value = preg_replace_callback('~(<a .*?>.*?</a>|<.*?>)~i', function ($match) use (&$links) {
            return '<' . array_push($links, $match[1]) . '>';
        }, $value);

        $config = get_addon_config('shop');
        $autolinks = $config['autolinks'];
        $value = preg_replace_callback('/(' . implode('|', array_keys($autolinks)) . ')/i', function ($match) use ($autolinks) {
            if (!isset($autolinks[$match[1]])) {
                return $match[0];
            } else {
                return '<a href="' . $autolinks[$match[1]] . '" target="_blank">' . $match[0] . '</a>';
            }
        }, $value);
        return preg_replace_callback('/<(\d+)>/', function ($match) use (&$links) {
            return $links[$match[1] - 1];
        }, $value);
    }

    /**
     * @ 获取商品模板
     * @return void
     */
    public static function getSourceTpl($tpl_id, $source_id)
    {
        if (!$tpl_id || !$source_id) {
            return '';
        }
        $row = \addons\shop\model\Card::where('status', 'normal')->where('id', $tpl_id)->find();
        if (empty($row)) {
            return '';
        }
        $source = null;
        switch ($row['type']) {
            case 1:
                $source = \addons\shop\model\Coupon::getCouponInfo($source_id);
                break;
            default:
                $source = \addons\shop\model\Goods::get($source_id);
        }
        if (empty($source)) {
            return '';
        }
        $view = new View();
        $html = $view->fetch($row->content, ['source' => $source, 'tpl' => $row], [], [], true);
        return $html;
    }

    /**
     * @ 替换多余的卡片信息
     * @param $value
     * @return void
     */
    public static function replaceSourceTpl($value)
    {
        if (!empty($value)) {
            return preg_replace('/(?<=data-id=\"shop\"\>).*?(?=\<div\s+data-id="end"\>(\s|[\r\n]|&nbsp;)*\<\/div\>)/is', '&nbsp;', $value);
        }
        return $value;
    }

    /**
     * @ 商品模板转化
     * @return void
     */
    public static function formatSourceTpl($value)
    {
        if (!empty($value)) {
            $value = preg_replace_callback('/\<div\s+data-tpl\=\"(\d+)"\s+data\-source=\"(\w+)\"[\s\S]*?\<div\s+data-id\=\"end\"\>[\s\S]*?\<\/div\>[\s\S]*?\<\/div\>/i', function ($match) {
                return \addons\shop\library\Service::getSourceTpl($match[1], $match[2]);
            }, $value);
        }
        return $value;
    }


    /**
     * @ uniapp商品模板转化
     * @return void
     */
    public static function formatTplToUniapp($value)
    {
        if (!empty($value)) {
            $value = preg_replace_callback("/href=\"(.*?)\"(\s|[\r\n]|&nbsp;)*data\-type=\"(goods|coupon)\"(\s|[\r\n]|&nbsp;)*data\-id=\"(\w+)\"/is", function ($matches) {
                return 'href="/pages/' . $matches[3] . '/detail?id=' . $matches[5] . '"';
            }, $value);
        }
        return $value;
    }

    /**
     * 获取缓存标签和时长
     * @param string $type
     * @param array  $tag
     * @return array
     */
    public static function getCacheKeyExpire($type, $tag = [])
    {
        $config = get_addon_config('shop');
        $cache = !isset($tag['cache']) ? $config['cachelifetime'] : $tag['cache'];
        $cache = in_array($cache, ['true', 'false', true, false], true) ? (in_array($cache, ['true', true], true) ? 0 : -1) : (int)$cache;
        $cacheKey = $cache > -1 ? "shop-taglib-{$type}-" . md5(serialize($tag)) : false;
        $cacheExpire = $cache > -1 ? $cache : null;
        return [$cacheKey, $cacheExpire];
    }

    public static function isInternalRequest()
    {
        // 获取当前域名和端口
        $currentDomain = request()->host();

        // 获取来源
        $referer = request()->server('HTTP_REFERER', '');
        if (!$referer) {
            return false;
        }

        $refererInfo = parse_url($referer);

        // 检查来源是否存在且域名与当前域名相同（考虑端口）
        if ($refererInfo && isset($refererInfo['host'])) {
            $refererHost = $refererInfo['host'];
            $currentHost = $currentDomain;

            // 如果Referer包含端口信息，则需要包含端口进行比较
            if (isset($refererInfo['port'])) {
                $refererHost .= ':' . $refererInfo['port'];
            }

            return $refererHost === $currentHost;
        }

        return false;
    }
}
