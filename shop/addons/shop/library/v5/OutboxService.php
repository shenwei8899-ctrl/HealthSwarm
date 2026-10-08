<?php

namespace addons\shop\library\v5;

use think\Db;

class OutboxService
{
    public function append($eventType, $aggregateType, $aggregateRef, $aggregateVersion, $destination, array $payload)
    {
        $eventId = Identifiers::make('evt');
        Db::name('shop_outbox_event')->insert([
            'event_id'          => $eventId,
            'event_type'        => $eventType,
            'aggregate_type'    => $aggregateType,
            'aggregate_ref'     => (string)$aggregateRef,
            'aggregate_version' => (int)$aggregateVersion,
            'destination'       => $destination,
            'payload_json'      => Json::encode($payload),
            'status'            => 'pending',
            'attempts'          => 0,
            'next_retry_at'     => time(),
            'createtime'        => time(),
            'updatetime'        => time(),
        ]);
        return $eventId;
    }
}
