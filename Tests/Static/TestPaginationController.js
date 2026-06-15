// directive: table-renderer-service | // see shared-table-renderer.S1
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PaginationController } from '../../static/js/TableRenderer/PaginationController.js';
import { EventBus } from '../../static/js/TableRenderer/EventBus.js';
import { TableRendererConfig } from '../../static/js/TableRenderer/TableRendererConfig.js';
import { StubDataSource } from './_StubDataSource.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
function NewCtl(Total = 100, PageSize = 10) {
    const Cfg = new TableRendererConfig({ DefaultPageSize: PageSize });
    const C = new PaginationController(new StubDataSource(), new EventBus(), Cfg);
    C.SetTotalCount(Total);
    return C;
}

/** NextPage advances when there is a next page */
test('NextPage advances when more pages exist', () => {
    const C = NewCtl(100, 10);
    C.NextPage();
    assert.equal(C.GetPage(), 1);
});

/** NextPage clamps at last page (no event, no advance) */
test('NextPage clamps at last page', () => {
    const C = NewCtl(25, 10);
    C.GoTo(2);
    C.NextPage();
    assert.equal(C.GetPage(), 2);
});

/** PrevPage clamps at 0 */
test('PrevPage clamps at zero', () => {
    const C = NewCtl(20, 10);
    C.PrevPage();
    assert.equal(C.GetPage(), 0);
});

/** GoTo with out-of-range index clamps to last page */
test('GoTo out of range clamps to last page', () => {
    const C = NewCtl(25, 10);
    C.GoTo(999);
    assert.equal(C.GetPage(), 2);
});

/** GoTo with negative index clamps to zero */
test('GoTo negative clamps to zero', () => {
    const C = NewCtl(25, 10);
    C.GoTo(-5);
    assert.equal(C.GetPage(), 0);
});

/** PageChanged fires when the page changes (C15) */
test('PageChanged fires on page change (C15)', () => {
    const Cfg = new TableRendererConfig({ DefaultPageSize: 10 });
    const Bus = new EventBus();
    let Count = 0;
    Bus.Subscribe('PageChanged', () => { Count++; });
    const C = new PaginationController(new StubDataSource(), Bus, Cfg);
    C.SetTotalCount(100);
    C.NextPage();
    assert.equal(Count, 1);
});

/** PageChanged does not fire when GoTo is a no-op */
test('PageChanged is silent when page is unchanged', () => {
    const Cfg = new TableRendererConfig({ DefaultPageSize: 10 });
    const Bus = new EventBus();
    let Count = 0;
    Bus.Subscribe('PageChanged', () => { Count++; });
    const C = new PaginationController(new StubDataSource(), Bus, Cfg);
    C.SetTotalCount(100);
    C.GoTo(0);
    assert.equal(Count, 0);
});

/** SetPageSize resets page to 0 */
test('SetPageSize resets page to zero', () => {
    const C = NewCtl(100, 10);
    C.GoTo(5);
    C.SetPageSize(25);
    assert.equal(C.GetPage(), 0);
    assert.equal(C.GetPageSize(), 25);
});
