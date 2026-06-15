// directive: table-renderer-service | // see shared-table-renderer.S1
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ColumnDefinition } from '../../static/js/TableRenderer/ColumnDefinition.js';

/** Construct with only the required Key */
test('ColumnDefinition with only Key defaults the rest', () => {
    const C = new ColumnDefinition({ Key: 'Title' });
    assert.equal(C.Key, 'Title');
    assert.equal(C.Header, 'Title');
    assert.equal(C.Sortable, false);
    assert.equal(C.Filterable, false);
    assert.equal(C.Editable, false);
    assert.equal(C.CellRendererName, 'Text');
});

/** Missing Key is rejected */
test('ColumnDefinition without Key throws', () => {
    assert.throws(() => new ColumnDefinition({}));
    assert.throws(() => new ColumnDefinition(null));
});

/** Spec values override defaults */
test('ColumnDefinition copies declared fields', () => {
    const C = new ColumnDefinition({
        Key: 'Status', Header: 'St', Sortable: true, Filterable: true,
        Editable: true, CellRendererName: 'Badge', EditorName: 'Select',
        Width: 120, Align: 'right'
    });
    assert.equal(C.Header, 'St');
    assert.equal(C.Sortable, true);
    assert.equal(C.CellRendererName, 'Badge');
    assert.equal(C.EditorName, 'Select');
    assert.equal(C.Width, 120);
    assert.equal(C.Align, 'right');
});
