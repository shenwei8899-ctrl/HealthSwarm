<?php
$_SERVER['REMOTE_ADDR']='127.0.0.1';
require dirname(__DIR__).'/bootstrap.php';
set_exception_handler(function ($error) { fwrite(STDERR,(string)$error."\n");exit(1); });

use think\Db;
use addons\shop\library\v5\{DomainException,PartnerApplicationService};

if(config('database.database')!=='partner_intake_test_20261101'||getenv('HEALTHFLOW_RELEASE_TEST')!=='1')throw new RuntimeException('Dedicated partner intake test database required');
Db::query("SELECT setval(pg_get_serial_sequence('fa_user','id'), (SELECT COALESCE(MAX(id),0)+1 FROM fa_user), false)");
function partnerCheck($value,$message){if(!$value)throw new RuntimeException($message);}
function partnerReject($fn,$code){try{$fn();}catch(DomainException $error){partnerCheck($error->getCode()===$code,'Unexpected rejection '.$error->getCode());return;}throw new RuntimeException('Expected rejection '.$code);}

$service=new PartnerApplicationService();
$users=[];
foreach(['owner','other'] as $name)$users[$name]=Db::name('user')->insertGetId(['username'=>'partner_'.uniqid().'_'.$name,'status'=>'normal']);
$area=Db::name('shop_area')->where('level',3)->where('status','normal')->find();
if(!$area){
    $parent=0;
    foreach([1=>'合成测试省',2=>'合成测试市',3=>'合成测试区'] as $level=>$name)$parent=Db::name('shop_area')->insertGetId(['pid'=>$parent,'level'=>$level,'name'=>$name,'adcode'=>'99000'.$level,'status'=>'normal']);
    $area=Db::name('shop_area')->where('id',$parent)->find();
}
partnerCheck((bool)$area,'Synthetic test installation needs its region directory');
$payload=['partner_type'=>'supplier','company_name'=>'个人申请人','contact_name'=>'测试联系人','contact_mobile'=>'13800000000','location_area_id'=>$area['id'],'capacity_summary'=>'提供本地合作资源','contact_wechat'=>'synthetic_wechat','privacy_consent_version'=>PartnerApplicationService::POLICY];
$rows=[];
foreach(['supplier','channel','distributor'] as $type){
    $input=$payload;$input['partner_type']=$type;$key='synthetic-'.uniqid();
    $first=$service->submit($users['owner'],$key,$input);
    $retry=$service->submit($users['owner'],$key,$input);
    partnerCheck($first===$retry,'Same key must return the original committed receipt');
    partnerCheck((int)Db::name('shop_supplier_application')->where('user_id',$users['owner'])->where('submission_key',$key)->count()===1,'Submission was duplicated');
    $row=Db::name('shop_supplier_application')->where('application_sn',$first['application_sn'])->find();$rows[]=$row;
    partnerCheck(strpos($row['contact_mobile_encrypted'],'enc:v1:')===0 && strpos($row['contact_mobile_encrypted'],'13800000000')===false,'Phone must be encrypted at rest');
    partnerCheck($row['qualification_files_json']==='[]' && (int)$row['supplier_id']===0,'Intake must not require qualifications or create a supplier');
    partnerCheck(count(json_decode($row['location_json'],true))===3,'Province, city and district must be resolved by the server');
    partnerReject(function()use($service,$users,$key,$input){$input['capacity_summary']='different';$service->submit($users['owner'],$key,$input);},40901);
    $other=$service->submit($users['other'],$key,$input);
    partnerCheck($other['application_sn']!==$first['application_sn'],'Different accounts must own separate requests');
}
foreach(['partner_type','location_area_id','capacity_summary','privacy_consent_version'] as $field){
    $input=$payload;unset($input[$field]);partnerReject(function()use($service,$users,$input){$service->submit($users['owner'],'missing-'.uniqid(),$input);},40001);
}
$invalid=$payload;$invalid['capacity_summary']=str_repeat('字',501);
partnerReject(function()use($service,$users,$invalid){$service->submit($users['owner'],'oversize-'.uniqid(),$invalid);},40001);
$invalid=$payload;$invalid['location_area_id']=2147483647;
partnerReject(function()use($service,$users,$invalid){$service->submit($users['owner'],'area-'.uniqid(),$invalid);},40001);
$before=Db::name('shop_supplier')->count();
$zeroReceipt=$service->submit($users['owner'],'0',$payload);
$zeroApplication=Db::name('shop_supplier_application')->where('application_sn',$zeroReceipt['application_sn'])->find();
partnerCheck(PartnerApplicationService::isContactIntake($zeroApplication),'The valid key 0 must remain a contact intake');
partnerCheck((int)$zeroApplication['supplier_id']===0,'A contact intake must not create a formal supplier');
$detail=$service->detail($rows[0]['id']);partnerCheck($detail['contact_mobile']==='13800000000','Authorized detail must recover the contact phone');
$service->followUp($rows[0]['id'],999,['version'=>1,'follow_up_status'=>'contacted','follow_up_note'=>'已联系，等待后续资料']);
partnerCheck($service->detail($rows[0]['id'])['follow_up_status']==='contacted','Follow-up did not persist');
partnerReject(function()use($service,$rows){$service->followUp($rows[0]['id'],998,['version'=>1,'follow_up_status'=>'closed']);},40910);
partnerCheck(Db::name('shop_supplier')->count()===$before,'Follow-up must not create a formal supplier');
$auth=new \app\common\library\Auth();partnerCheck($auth->direct($users['owner']),$auth->getError());
$state=['owner_id'=>$users['owner'],'other_id'=>$users['other'],'owner_token'=>$auth->getToken(),'payload'=>$payload];
$otherAuth=new \app\common\library\Auth();partnerCheck($otherAuth->direct($users['other']),$otherAuth->getError());$state['other_token']=$otherAuth->getToken();
file_put_contents(dirname(__DIR__).'/fixtures/partner-http-state.json',json_encode($state));
echo "Partner intake PostgreSQL passed: 3 types, personal applicant, encrypted phone, no qualifications, replay, payload conflicts, account isolation, required fields, location validation and manual follow-up.\n";
