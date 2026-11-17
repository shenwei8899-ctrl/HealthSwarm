<?php

use addons\shop\library\v5\DomainException;
use addons\shop\library\v5\PlanScheduleService;

require dirname(__DIR__, 2) . '/addons/shop/library/v5/DomainException.php';
require dirname(__DIR__, 2) . '/addons/shop/library/v5/PlanScheduleService.php';

function check($condition, $message)
{
    if (!$condition) throw new RuntimeException($message);
}

$timezone = new DateTimeZone('Asia/Shanghai');
$now = (new DateTimeImmutable('2026-11-14', $timezone))->getTimestamp();
$config = ['first_lead_days'=>1, 'resume_lead_days'=>1, 'booking_horizon_days'=>21, 'cutoff_lead_days'=>0, 'cutoff_time'=>'12:00'];
$region = ['weekdays'=>range(1, 7), 'closed_dates'=>[]];
foreach (['daily'=>21, 'weekly_2'=>6, 'weekly_3'=>9] as $frequency => $count) {
    $ranges = PlanScheduleService::menuRanges($frequency, 21);
    $batches = PlanScheduleService::dates($config, $region, '2026-11-16', count($ranges), false, $now, $ranges);
    check(count($batches) === $count, 'Unexpected batch count');
    $days = [];
    foreach ($batches as $index => $batch) {
        $days = array_merge($days, range($batch['menu_day_start'], $batch['menu_day_end']));
        if ($index > 0) check($batch['delivery_date'] === $batches[$index - 1]['meal_end_date'], 'Gap between batches');
    }
    check($days === range(1, 21), 'Menu coverage must include each day exactly once');
    check(end($batches)['meal_end_date'] === '2026-12-07', 'The last meal date must be independent of frequency');
}

$paused = [
    ['batch_no'=>2, 'menu_day_start'=>4, 'menu_day_end'=>7],
    ['batch_no'=>3, 'menu_day_start'=>8, 'menu_day_end'=>10],
];
check(PlanScheduleService::menuRanges('weekly_2', 2, $paused) === [[4, 7], [8, 10]], 'Resume must retain the purchased menu ranges');
check(PlanScheduleService::purchaseFrequency(['delivery_frequency'=>'daily'], null) === 'daily', 'Legacy clients retain daily delivery');
try {
    PlanScheduleService::purchaseFrequency(['delivery_frequency'=>'selectable'], 'daily');
    throw new RuntimeException('Selectable plans must require a weekly frequency');
} catch (DomainException $error) {
    check($error->getCode() === 40011, 'Unexpected frequency error');
}

$ranges = PlanScheduleService::menuRanges('weekly_2', 21);
$region['closed_dates'] = ['2026-11-19'];
try {
    PlanScheduleService::dates($config, $region, '2026-11-16', count($ranges), false, $now, $ranges);
    throw new RuntimeException('Blackout must reject the affected schedule');
} catch (DomainException $error) {
    check($error->getDetails()['delivery_date'] === '2026-11-19', 'Wrong blackout date');
}
echo "Plan delivery coverage passed.\n";
