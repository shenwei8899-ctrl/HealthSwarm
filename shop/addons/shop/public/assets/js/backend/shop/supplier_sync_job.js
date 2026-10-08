define(['jquery', 'bootstrap', 'backend', 'table', 'form'], function ($, undefined, Backend, Table, Form) {
    var Controller = {index: function () {
        Table.api.init({extend: {index_url: 'shop/supplier_sync_job/index' + location.search, table: 'shop_supplier_sync_job'}});
        var table = $('#table');
        table.bootstrapTable({url: $.fn.bootstrapTable.defaults.extend.index_url, pk: 'id', sortName: 'id', sortOrder: 'desc', columns: [[
            {field: 'id', title: 'ID'}, {field: 'job_sn', title: '任务号', operate: 'LIKE'},
            {field: 'supplier_id', title: '供应商ID'}, {field: 'sync_type', title: '同步类型'},
            {field: 'direction', title: '方向'}, {field: 'biz_key', title: '业务键', operate: 'LIKE'},
            {field: 'status', title: '状态', searchList: {PENDING:'待处理',RUNNING:'处理中',SUCCESS:'成功',FAILED:'失败待重试',MANUAL_REQUIRED:'需人工补偿'}, formatter: Table.api.formatter.status},
            {field: 'attempts', title: '次数'}, {field: 'next_retry_at', title: '下次重试', formatter: Table.api.formatter.datetime},
            {field: 'last_error', title: '失败原因', formatter: Table.api.formatter.content},
            {field: 'createtime', title: '创建时间', formatter: Table.api.formatter.datetime},
            {field: 'operate', title: '操作', table: table, events: Table.api.events.operate, formatter: Table.api.formatter.operate, buttons: [
                {name:'retry', text:'重试', title:'立即重试', classname:'btn btn-xs btn-warning btn-ajax', url:'shop/supplier_sync_job/retry/ids/{id}', confirm:'确认立即重试？', refresh:true, hidden:function(row){return ['FAILED','MANUAL_REQUIRED'].indexOf(row.status)<0;}},
                {name:'complete', text:'人工完成', title:'人工补偿完成', classname:'btn btn-xs btn-success btn-ajax', url:'shop/supplier_sync_job/complete/ids/{id}', confirm:'仅在已通过线下方式完成供应商处理后确认，是否继续？', refresh:true, hidden:function(row){return ['FAILED','MANUAL_REQUIRED'].indexOf(row.status)<0;}}
            ]}
        ]]}); Table.api.bindevent(table);
    }}; return Controller;
});
