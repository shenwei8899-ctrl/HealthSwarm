<?php

namespace app\common\library;

/** Keep ThinkPHP challenge generation and validation; adapt only the font path. */
class CaptchaImage extends \think\captcha\Captcha
{
    public function __set($name, $value)
    {
        // Windows FreeType cannot open the UTF-8 absolute paths in this checkout.
        if ($name === 'fontttf' && PHP_OS_FAMILY === 'Windows' && preg_match('/[^\x20-\x7e]/', (string)$value)) {
            $windows = str_replace('\\', '/', getenv('WINDIR') ?: 'C:/Windows');
            $fonts = $this->useZh ? ['msyh.ttc', 'simhei.ttf'] : ['arial.ttf', 'segoeui.ttf'];
            $font = null;
            foreach ($fonts as $filename) {
                $candidate = $windows . '/Fonts/' . $filename;
                if (is_file($candidate) && is_readable($candidate)) {
                    $font = $candidate;
                    break;
                }
            }
            if (!$font) throw new \RuntimeException('Windows 验证码字体不可用');
            $value = $font;
        }
        parent::__set($name, $value);
    }
}
