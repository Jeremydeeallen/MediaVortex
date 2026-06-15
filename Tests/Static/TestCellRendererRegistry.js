// directive: table-renderer-service | // see shared-table-renderer.S1
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { CellRendererRegistry } from '../../static/js/TableRenderer/CellRenderers/CellRendererRegistry.js';

/** Registered renderer is retrievable by name */
test('Register then Resolve returns the same class', () => {
    const R = new CellRendererRegistry();
    class Fake { Render() { return 'x'; } }
    R.Register('Fake', Fake);
    assert.equal(R.Resolve('Fake'), Fake);
});

/** Has reports membership */
test('Has reflects registration', () => {
    const R = new CellRendererRegistry();
    class Fake {}
    assert.equal(R.Has('Fake'), false);
    R.Register('Fake', Fake);
    assert.equal(R.Has('Fake'), true);
});

/** Resolve throws on unknown name (registry contract: throw, not null) */
test('Resolve throws on unknown name', () => {
    const R = new CellRendererRegistry();
    assert.throws(() => R.Resolve('Nope'));
});

/** Built-in renderers are pre-registered for Text/Number/Badge/Button */
test('Built-in renderers are registered out of the box', () => {
    const R = new CellRendererRegistry();
    for (const N of ['Text', 'Number', 'Badge', 'Button']) {
        assert.equal(R.Has(N), true, `expected built-in ${N}`);
    }
});

/** C3 OCP: a new column type registers without modifying core */
test('OCP: new ProgressBar renderer registers without core change (C3)', () => {
    const R = new CellRendererRegistry();
    class ProgressBarCellRenderer {
        Render(_Row, Value) { return `[bar:${Value}]`; }
    }
    R.Register('ProgressBar', ProgressBarCellRenderer);
    const Inst = R.Instantiate('ProgressBar');
    assert.equal(Inst.Render({}, 42), '[bar:42]');
});
