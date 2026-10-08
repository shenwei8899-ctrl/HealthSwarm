<?php

namespace addons\shop\library\v5;

class DomainException extends \RuntimeException
{
    protected $httpStatus;
    protected $details;

    public function __construct($message, $code = 40000, $httpStatus = 400, array $details = [])
    {
        parent::__construct($message, (int)$code);
        $this->httpStatus = (int)$httpStatus;
        $this->details = $details;
    }

    public function getHttpStatus()
    {
        return $this->httpStatus;
    }

    public function getDetails()
    {
        return $this->details;
    }
}
