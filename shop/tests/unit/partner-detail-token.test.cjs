const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../../public/assets/js/backend/shop/v5/workspace.js'), 'utf8');
const start = source.indexOf('partnerDetail: function');
const end = source.indexOf('reviewSupplierApplication:', start);
const expression = source.slice(start, end).trim().replace(/^partnerDetail:\s*/, '').replace(/,$/, '');

function fixture(canFollow) {
    let dialog, failure, sent;
    const data = {__token__: 'detail-token', can_follow: canFollow, location: []};
    const response = {code: 1, data};
    const $ = () => ({width: () => 800, find: () => ({val: () => 'contacted'})});
    $.getJSON = () => ({done(callback) { callback(response); return this; }, fail() { return this; }});
    const Layer = {open: options => { dialog = options; }, close() {}};
    const Fast = {api: {ajax(options, success, error) { sent = options; failure = error; }}};
    const Toastr = {error() {}, success() {}};
    const detail = new Function('$', 'Toastr', 'Layer', 'Fast', 'window', `return (${expression});`)($, Toastr, Layer, Fast, {});
    const workspace = {config: {csrfToken: 'old-token'}, textValue: () => '', escape: value => String(value || ''), load() {}};
    detail.call(workspace, {}, 1);
    return {workspace, dialog, fail: token => failure({__token__: token}), sent: () => sent};
}

test('reading and closing an application detail retains the newly issued token for later writes', () => {
    const page = fixture(false);
    assert.equal(page.workspace.config.csrfToken, 'detail-token');
    page.dialog.yes(1, {});
    assert.equal(page.sent(), undefined);
    assert.equal(page.workspace.config.csrfToken, 'detail-token');
});

test('a failed follow-up refreshes both the dialog and workspace tokens before retry', () => {
    const page = fixture(true);
    page.dialog.yes(1, {});
    assert.equal(page.sent().data.__token__, 'detail-token');
    page.fail('retry-token');
    assert.equal(page.workspace.config.csrfToken, 'retry-token');
    page.dialog.yes(1, {});
    assert.equal(page.sent().data.__token__, 'retry-token');
});
