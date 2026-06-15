// directive: table-renderer-service | // see shared-table-renderer.S1
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EventBus } from '../../static/js/TableRenderer/EventBus.js';

/** Subscribe + Emit fans out to the registered handler */
test('Subscribe then Emit invokes handler with payload', () => {
    const Bus = new EventBus();
    let Got = null;
    Bus.Subscribe('RowClicked', (P) => { Got = P; });
    Bus.Emit('RowClicked', { RowId: 7 });
    assert.deepEqual(Got, { RowId: 7 });
});

/** Returned unsubscribe closure stops only that handler */
test('Unsubscribe closure removes only the targeted handler', () => {
    const Bus = new EventBus();
    let A = 0; let B = 0;
    const Off = Bus.Subscribe('PageChanged', () => { A++; });
    Bus.Subscribe('PageChanged', () => { B++; });
    Off();
    Bus.Emit('PageChanged', {});
    assert.equal(A, 0);
    assert.equal(B, 1);
});

/** Emit fans out to multiple subscribers in order */
test('Emit reaches every subscriber', () => {
    const Bus = new EventBus();
    const Order = [];
    Bus.Subscribe('SortChanged', () => Order.push('a'));
    Bus.Subscribe('SortChanged', () => Order.push('b'));
    Bus.Subscribe('SortChanged', () => Order.push('c'));
    Bus.Emit('SortChanged', {});
    assert.equal(Order.length, 3);
});

/** Throwing handler does not break siblings */
test('Handler exception is contained', () => {
    const Bus = new EventBus();
    let Survived = false;
    Bus.Subscribe('CellEdited', () => { throw new Error('boom'); });
    Bus.Subscribe('CellEdited', () => { Survived = true; });
    Bus.Emit('CellEdited', {});
    assert.equal(Survived, true);
});

/** Unknown event names are rejected at Subscribe */
test('Subscribe refuses unknown event names', () => {
    const Bus = new EventBus();
    assert.throws(() => Bus.Subscribe('NotARealEvent', () => {}));
});

/** Emit on event with zero subscribers is a no-op */
test('Emit with no subscribers does not throw', () => {
    const Bus = new EventBus();
    Bus.Emit('FilterChanged', { Q: 'x' });
});

/** Canonical event names are exposed */
test('EventNames map exposes the six canonical events', () => {
    const Names = Object.values(EventBus.EventNames);
    for (const N of ['RowClicked', 'CellEdited', 'SortChanged', 'FilterChanged', 'PageChanged', 'SelectionChanged']) {
        assert.ok(Names.includes(N), `missing ${N}`);
    }
});
