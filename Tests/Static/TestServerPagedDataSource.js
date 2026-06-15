// directive: table-renderer-service | // see shared-table-renderer.S1
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ServerPagedDataSource } from '../../static/js/TableRenderer/DataSources/ServerPagedDataSource.js';
import { BuildQuery } from '../../static/js/TableRenderer/Interfaces/IDataSource.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
function MakeStubFetch(ResponseBuilder) {
    const Calls = [];
    const Fn = async (Url) => {
        Calls.push(Url);
        const Body = ResponseBuilder(Url, Calls.length);
        return {
            ok: true,
            status: 200,
            json: async () => Body
        };
    };
    Fn.Calls = Calls;
    return Fn;
}

/** URL composition surfaces page / pageSize / sort / q */
test('URL embeds page, pageSize, sort, q', async () => {
    const Fetch = MakeStubFetch(() => ({ Rows: [], TotalCount: 0 }));
    const DS = new ServerPagedDataSource('/api/Things', { Fetch });
    await DS.GetRows(BuildQuery({
        Page: 2, PageSize: 25,
        Sort: { Key: 'Name', Direction: 'DESC' },
        Filters: { q: 'foo' }
    }));
    assert.equal(Fetch.Calls.length, 1);
    const Url = Fetch.Calls[0];
    assert.match(Url, /page=2/i);
    assert.match(Url, /pageSize=25/i);
    assert.match(Url, /sort=/i);
    assert.match(Url, /q=foo/i);
});

/** Fetch shape: returns Rows from response */
test('Parse response Rows array', async () => {
    const Fetch = MakeStubFetch(() => ({ Rows: [{ A: 1 }, { A: 2 }], TotalCount: 2 }));
    const DS = new ServerPagedDataSource('/api/Things', { Fetch });
    const Rows = await DS.GetRows(BuildQuery({ Page: 0, PageSize: 10 }));
    assert.equal(Rows.length, 2);
    assert.equal(Rows[0].A, 1);
});

/** GetTotalCount returns the response TotalCount */
test('GetTotalCount reads response TotalCount', async () => {
    const Fetch = MakeStubFetch(() => ({ Rows: [], TotalCount: 4242 }));
    const DS = new ServerPagedDataSource('/api/Things', { Fetch });
    const N = await DS.GetTotalCount(BuildQuery({ Page: 0, PageSize: 10 }));
    assert.equal(N, 4242);
});

/** Cache hit: identical query does not re-fetch */
test('Cache hit on identical query', async () => {
    const Fetch = MakeStubFetch(() => ({ Rows: [{ A: 1 }], TotalCount: 1 }));
    const DS = new ServerPagedDataSource('/api/Things', { Fetch });
    const Q = BuildQuery({ Page: 0, PageSize: 10 });
    await DS.GetRows(Q);
    await DS.GetRows(Q);
    assert.equal(Fetch.Calls.length, 1);
});

/** Cache miss when query changes */
test('Different query refetches', async () => {
    const Fetch = MakeStubFetch(() => ({ Rows: [], TotalCount: 0 }));
    const DS = new ServerPagedDataSource('/api/Things', { Fetch });
    await DS.GetRows(BuildQuery({ Page: 0, PageSize: 10 }));
    await DS.GetRows(BuildQuery({ Page: 1, PageSize: 10 }));
    assert.equal(Fetch.Calls.length, 2);
});
