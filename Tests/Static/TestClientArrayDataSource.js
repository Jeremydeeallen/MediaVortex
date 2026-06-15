// directive: table-renderer-service | // see shared-table-renderer.S1
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ClientArrayDataSource } from '../../static/js/TableRenderer/DataSources/ClientArrayDataSource.js';
import { BuildQuery } from '../../static/js/TableRenderer/Interfaces/IDataSource.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
function Seed() {
    return [
        { Id: 1, Name: 'Charlie', Score: 80 },
        { Id: 2, Name: 'Alice', Score: 95 },
        { Id: 3, Name: 'Bob', Score: 70 },
        { Id: 4, Name: 'Dave', Score: 95 },
        { Id: 5, Name: 'Eve', Score: 60 }
    ];
}

/** Sort ASC by string column orders alphabetically */
test('Sort ASC by Name', async () => {
    const DS = new ClientArrayDataSource(Seed());
    const Rows = await DS.GetRows(BuildQuery({ Sort: { Key: 'Name', Direction: 'ASC' }, PageSize: 50 }));
    assert.deepEqual(Rows.map(R => R.Name), ['Alice', 'Bob', 'Charlie', 'Dave', 'Eve']);
});

/** Sort DESC reverses order */
test('Sort DESC by Score', async () => {
    const DS = new ClientArrayDataSource(Seed());
    const Rows = await DS.GetRows(BuildQuery({ Sort: { Key: 'Score', Direction: 'DESC' }, PageSize: 50 }));
    assert.equal(Rows[0].Score, 95);
    assert.equal(Rows[Rows.length - 1].Score, 60);
});

/** Contains filter is case-insensitive substring (default filter semantic) */
test('Filter contains on Name', async () => {
    const DS = new ClientArrayDataSource(Seed());
    const Rows = await DS.GetRows(BuildQuery({ Filters: { Name: 'a' }, PageSize: 50 }));
    for (const R of Rows) assert.ok(R.Name.toLowerCase().includes('a'));
    assert.ok(Rows.length > 0);
});

/** Filter narrows by stringified equality (Score=95) */
test('Filter by Score value narrows', async () => {
    const DS = new ClientArrayDataSource(Seed());
    const Rows = await DS.GetRows(BuildQuery({ Filters: { Score: '95' }, PageSize: 50 }));
    assert.equal(Rows.length, 2);
});

/** Pagination boundary: page 0 of size 2 */
test('Page 0 returns the first slice', async () => {
    const DS = new ClientArrayDataSource(Seed());
    const Rows = await DS.GetRows(BuildQuery({ Page: 0, PageSize: 2 }));
    assert.equal(Rows.length, 2);
});

/** Last page returns the remaining slice */
test('Last page returns trailing rows', async () => {
    const DS = new ClientArrayDataSource(Seed());
    const Rows = await DS.GetRows(BuildQuery({ Page: 2, PageSize: 2 }));
    assert.equal(Rows.length, 1);
});

/** Beyond last page returns empty */
test('Page beyond end yields empty', async () => {
    const DS = new ClientArrayDataSource(Seed());
    const Rows = await DS.GetRows(BuildQuery({ Page: 99, PageSize: 2 }));
    assert.equal(Rows.length, 0);
});

/** Empty seed yields empty page and zero total */
test('Empty seed', async () => {
    const DS = new ClientArrayDataSource([]);
    const Rows = await DS.GetRows(BuildQuery({ Page: 0, PageSize: 10 }));
    const Total = await DS.GetTotalCount(BuildQuery({}));
    assert.equal(Rows.length, 0);
    assert.equal(Total, 0);
});

/** GetTotalCount reflects filter narrowing */
test('GetTotalCount applies filters', async () => {
    const DS = new ClientArrayDataSource(Seed());
    const N = await DS.GetTotalCount(BuildQuery({ Filters: { Score: '95' } }));
    assert.equal(N, 2);
});
