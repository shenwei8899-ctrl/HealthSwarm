define(['jquery','bootstrap','backend','table','form'], function($,undefined,Backend,Table,Form){
    var Controller={index:function(){Table.api.init({extend:{index_url:'shop/refund_transaction/index'+location.search,table:'shop_refund_transaction'}});var table=$('#table');
        table.bootstrapTable({url:$.fn.bootstrapTable.defaults.extend.index_url,pk:'id',sortName:'id',sortOrder:'desc',columns:[[
            {field:'id',title:'ID'},{field:'refund_sn',title:'退款单号',operate:'LIKE'},{field:'order_sn',title:'订单号',operate:'LIKE'},
            {field:'channel',title:'渠道'},{field:'amount',title:'退款金额'},{field:'local_action',title:'本地动作'},
            {field:'status',title:'状态',searchList:{CREATED:'已创建',PROCESSING:'处理中',FAILED:'失败',EXTERNAL_SUCCESS:'外部成功待补偿',COMPLETED:'已完成'},formatter:Table.api.formatter.status},
            {field:'attempt_count',title:'尝试次数'},{field:'gateway_refund_id',title:'渠道退款号'},{field:'error_message',title:'错误',formatter:Table.api.formatter.content},
            {field:'createtime',title:'创建时间',formatter:Table.api.formatter.datetime},
            {field:'operate',title:'操作',table:table,events:Table.api.events.operate,formatter:Table.api.formatter.operate,buttons:[
                {name:'reconcile',text:'本地补偿',classname:'btn btn-xs btn-warning btn-ajax',url:'shop/refund_transaction/reconcile/ids/{id}',confirm:'外部退款已成功，确认重做本地库存及售后处理？',refresh:true,hidden:function(row){return row.status!=='EXTERNAL_SUCCESS';}},
                {name:'confirm',text:'人工确认',classname:'btn btn-xs btn-success btn-ajax',url:'shop/refund_transaction/confirm/ids/{id}',confirm:'请确认款项已通过线下方式退回用户，是否继续？',refresh:true,hidden:function(row){return ['CREATED','FAILED'].indexOf(row.status)<0;}}
            ]}
        ]]});Table.api.bindevent(table);}};return Controller;
});
