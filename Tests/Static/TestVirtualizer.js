// directive: table-renderer-service | // see shared-table-renderer.S1
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Virtualizer } from '../../static/js/TableRenderer/Virtualizer.js';
import { TableRendererConfig } from '../../static/js/TableRenderer/TableRendererConfig.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
function MakeContainer(ScrollTop, ClientHeight) {
    const Listeners = new Map();
    return {
        scrollTop: ScrollTop,
        clientHeight: ClientHeight,
        addEventListener(N, H) {
            if (!Listeners.has(N)) Listeners.set(N, new Set());
            Listeners.get(N).add(H);
        },
        removeEventListener(N, H) {
            const S = Listeners.get(N);
            if (S) S.delete(H);
        }
    };
}

/** VisibleRange at scrollTop=0 starts at row 0 */
test('VisibleRange starts at 0 when scrollTop is 0', () => {
    const V = new Virtualizer(new TableRendererConfig({ RowHeightPx: 32, BufferRows: 5 }));
    V.Attach(MakeContainer(0, 320), 4000, 32);
    const R = V.VisibleRange();
    assert.equal(R.Start, 0);
    assert.ok(R.End <= 4000);
});

/** VisibleRange in the middle reflects scrollTop */
test('VisibleRange tracks scrollTop in the middle', () => {
    const V = new Virtualizer(new TableRendererConfig({ RowHeightPx: 32, BufferRows: 5 }));
    V.Attach(MakeContainer(32 * 1000, 320), 4000, 32);
    const R = V.VisibleRange();
    assert.ok(R.Start >= 990 && R.Start <= 1000, `Start=${R.Start}`);
    assert.ok(R.End >= 1010, `End=${R.End}`);
});

/** VisibleRange at end clamps to TotalRows */
test('VisibleRange clamps at end', () => {
    const V = new Virtualizer(new TableRendererConfig({ RowHeightPx: 32, BufferRows: 5 }));
    V.Attach(MakeContainer(32 * 4000, 320), 4000, 32);
    const R = V.VisibleRange();
    assert.equal(R.End, 4000);
});

/** Buffer rows extend the visible range */
test('Buffer rows extend the visible range', () => {
    const NoBuf = new Virtualizer(new TableRendererConfig({ RowHeightPx: 32, BufferRows: 0 }));
    NoBuf.Attach(MakeContainer(32 * 500, 320), 4000, 32);
    const Buf = new Virtualizer(new TableRendererConfig({ RowHeightPx: 32, BufferRows: 5 }));
    Buf.Attach(MakeContainer(32 * 500, 320), 4000, 32);
    const A = NoBuf.VisibleRange();
    const B = Buf.VisibleRange();
    assert.ok((B.End - B.Start) >= (A.End - A.Start));
});

/** TotalHeightPx equals TotalRows * RowHeightPx */
test('TotalHeightPx is rows times row height', () => {
    const V = new Virtualizer(new TableRendererConfig({ RowHeightPx: 32, BufferRows: 5 }));
    V.Attach(MakeContainer(0, 320), 4000, 32);
    assert.equal(V.TotalHeightPx(), 32 * 4000);
});

/** C8 visible-window count stays small at 4000 rows */
test('C8: visible window stays small at 4000 rows', () => {
    const V = new Virtualizer(new TableRendererConfig({ RowHeightPx: 32, BufferRows: 10 }));
    V.Attach(MakeContainer(0, 320), 4000, 32);
    const R = V.VisibleRange();
    assert.ok((R.End - R.Start) < 150, `range ${R.End - R.Start} should be < 150`);
});

/** Empty container returns Start=0 End=0 */
test('Zero TotalRows yields an empty range', () => {
    const V = new Virtualizer(new TableRendererConfig({ RowHeightPx: 32, BufferRows: 5 }));
    V.Attach(MakeContainer(0, 320), 0, 32);
    const R = V.VisibleRange();
    assert.equal(R.Start, 0);
    assert.equal(R.End, 0);
});
