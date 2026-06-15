import { IDataSource } from '../Interfaces/IDataSource.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
export class ServerPagedDataSource extends IDataSource {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor(Url, Options = {}) {
        super();
        if (!Url) throw new Error('ServerPagedDataSource requires a Url');
        this._Url = Url;
        this._Fetch = Options.Fetch ?? ((typeof fetch !== 'undefined') ? fetch.bind(globalThis) : null);
        this._MaxCached = Options.MaxCached ?? 8;
        this._Cache = new Map();
        this._RowsKey = Options.RowsKey ?? 'Rows';
        this._TotalKey = Options.TotalKey ?? 'TotalCount';
        this._FilterParam = Options.FilterParam ?? 'q';
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    async GetRows(Query) {
        const Resp = await this._FetchPayload(Query);
        return Resp[this._RowsKey] ?? [];
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    async GetTotalCount(Query) {
        const Resp = await this._FetchPayload(Query);
        return Resp[this._TotalKey] ?? 0;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    async _FetchPayload(Query) {
        const Key = JSON.stringify(Query ?? {});
        if (this._Cache.has(Key)) return this._Cache.get(Key);
        if (!this._Fetch) throw new Error('No fetch implementation available');
        const Url = this._BuildUrl(Query);
        const Resp = await this._Fetch(Url, { method: 'GET', headers: { 'Accept': 'application/json' } });
        if (!Resp.ok) throw new Error(`HTTP ${Resp.status} from ${Url}`);
        const Json = await Resp.json();
        this._Cache.clear();
        if (this._Cache.size >= this._MaxCached) {
            const First = this._Cache.keys().next().value;
            this._Cache.delete(First);
        }
        this._Cache.set(Key, Json);
        return Json;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    _BuildUrl(Query) {
        const Params = new URLSearchParams();
        if (Query?.Page != null) Params.set('page', String(Query.Page));
        if (Query?.PageSize != null) Params.set('pageSize', String(Query.PageSize));
        if (Query?.Sort && Query.Sort.Key) {
            const Dir = (Query.Sort.Direction ?? 'DESC').toUpperCase();
            Params.set('sort', `${Query.Sort.Key}:${Dir}`);
        }
        const Filters = Query?.Filters ?? {};
        const FreeText = Filters._q ?? Filters.q ?? null;
        if (FreeText) Params.set(this._FilterParam, String(FreeText));
        for (const [K, V] of Object.entries(Filters)) {
            if (K === '_q' || K === 'q') continue;
            if (V == null || V === '') continue;
            Params.set(`filter.${K}`, String(V));
        }
        const Joiner = this._Url.includes('?') ? '&' : '?';
        const QueryStr = Params.toString();
        return QueryStr ? `${this._Url}${Joiner}${QueryStr}` : this._Url;
    }
}
