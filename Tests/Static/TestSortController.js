// directive: table-renderer-service | // see shared-table-renderer.S1
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SortController } from '../../static/js/TableRenderer/SortController.js';
import { EventBus } from '../../static/js/TableRenderer/EventBus.js';
import { TableRendererConfig } from '../../static/js/TableRenderer/TableRendererConfig.js';
import { StubDataSource } from './_StubDataSource.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
function NewController() {
    return new SortController(new StubDataSource(), new EventBus(), new TableRendererConfig());
}

/** SetSort without explicit direction on a new column uses DefaultSortDirection (DESC) */
test('SetSort defaults to DESC on a new column (C20)', () => {
    const C = NewController();
    C.SetSort('Name');
    const S = C.GetSortState();
    assert.equal(S.Key, 'Name');
    assert.equal(S.Direction, 'DESC');
});

/** Re-applying SetSort with no direction on same column toggles DESC -> ASC */
test('Re-SetSort same column DESC -> ASC', () => {
    const C = NewController();
    C.SetSort('Name');
    C.SetSort('Name');
    assert.equal(C.GetSortState().Direction, 'ASC');
});

/** Third call toggles ASC -> DESC */
test('Re-SetSort same column ASC -> DESC', () => {
    const C = NewController();
    C.SetSort('Name');
    C.SetSort('Name');
    C.SetSort('Name');
    assert.equal(C.GetSortState().Direction, 'DESC');
});

/** SortChanged fires exactly once per SetSort (C15) */
test('SortChanged fires once per SetSort call (C15)', () => {
    const Bus = new EventBus();
    let Count = 0;
    Bus.Subscribe('SortChanged', () => { Count++; });
    const C = new SortController(new StubDataSource(), Bus, new TableRendererConfig());
    C.SetSort('Name');
    assert.equal(Count, 1);
    C.SetSort('Name');
    assert.equal(Count, 2);
});

/** Reset clears state and emits SortChanged */
test('Reset clears sort state', () => {
    const C = NewController();
    C.SetSort('Name');
    C.Reset();
    assert.equal(C.GetSortState(), null);
});

/** SetSort with explicit ASC overrides default */
test('SetSort honors explicit direction', () => {
    const C = NewController();
    C.SetSort('Score', 'ASC');
    assert.equal(C.GetSortState().Direction, 'ASC');
});

/** Constructor refuses missing DataSource (C20 invariant) */
test('Constructor refuses missing DataSource', () => {
    assert.throws(() => new SortController(null, new EventBus(), new TableRendererConfig()));
});

/** Constructor refuses missing EventBus */
test('Constructor refuses missing EventBus', () => {
    assert.throws(() => new SortController(new StubDataSource(), null, new TableRendererConfig()));
});
