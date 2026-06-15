// directive: table-renderer-service | // see shared-table-renderer.S1
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { FilterController } from '../../static/js/TableRenderer/FilterController.js';
import { EventBus } from '../../static/js/TableRenderer/EventBus.js';
import { TableRendererConfig } from '../../static/js/TableRenderer/TableRendererConfig.js';
import { StubDataSource } from './_StubDataSource.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
function Wait(Ms) { return new Promise((R) => setTimeout(R, Ms)); }

/** SetFilter records the column / value pair */
test('SetFilter stores column value', () => {
    const C = new FilterController(new StubDataSource(), new EventBus(), new TableRendererConfig({ DebounceMs: 0 }));
    C.SetFilter('Name', 'foo');
    const S = C.GetFilterState();
    assert.equal(S.Name, 'foo');
});

/** Clear empties the filter state */
test('Clear empties filter state', () => {
    const C = new FilterController(new StubDataSource(), new EventBus(), new TableRendererConfig({ DebounceMs: 0 }));
    C.SetFilter('Name', 'foo');
    C.Clear();
    assert.equal(Object.keys(C.GetFilterState()).length, 0);
});

/** Debounce coalesces rapid SetFilter calls into one FilterChanged */
test('Debounce coalesces rapid SetFilter calls', async () => {
    const Bus = new EventBus();
    let Count = 0;
    Bus.Subscribe('FilterChanged', () => { Count++; });
    const C = new FilterController(new StubDataSource(), Bus, new TableRendererConfig({ DebounceMs: 30 }));
    C.SetFilter('Name', 'a');
    C.SetFilter('Name', 'ab');
    C.SetFilter('Name', 'abc');
    await Wait(80);
    assert.equal(Count, 1);
});

/** Two separated batches emit two events */
test('Two separated batches emit two events', async () => {
    const Bus = new EventBus();
    let Count = 0;
    Bus.Subscribe('FilterChanged', () => { Count++; });
    const C = new FilterController(new StubDataSource(), Bus, new TableRendererConfig({ DebounceMs: 20 }));
    C.SetFilter('Name', 'a');
    await Wait(60);
    C.SetFilter('Name', 'b');
    await Wait(60);
    assert.equal(Count, 2);
});

/** DebounceMs=0 emits synchronously per call */
test('DebounceMs=0 fires synchronously per call', () => {
    const Bus = new EventBus();
    let Count = 0;
    Bus.Subscribe('FilterChanged', () => { Count++; });
    const C = new FilterController(new StubDataSource(), Bus, new TableRendererConfig({ DebounceMs: 0 }));
    C.SetFilter('Name', 'x');
    C.SetFilter('Name', 'y');
    assert.equal(Count, 2);
});

/** Empty-string value removes the filter entry */
test('Empty value clears that column filter', () => {
    const C = new FilterController(new StubDataSource(), new EventBus(), new TableRendererConfig({ DebounceMs: 0 }));
    C.SetFilter('Name', 'foo');
    C.SetFilter('Name', '');
    assert.equal(C.GetFilterState().Name, undefined);
});
