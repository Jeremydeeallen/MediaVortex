import { IDataSource } from '../Interfaces/IDataSource.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
export class ClientArrayDataSource extends IDataSource {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor(Rows) {
        super();
        if (!Array.isArray(Rows)) throw new Error('ClientArrayDataSource requires an array');
        this._Rows = Rows;
        this._LastQueryKey = null;
        this._LastFiltered = null;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    SetRows(Rows) {
        this._Rows = Rows ?? [];
        this._LastQueryKey = null;
        this._LastFiltered = null;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    async GetRows(Query) {
        const Processed = this._ApplyFilterAndSort(Query);
        const Page = Query?.Page ?? 0;
        const PageSize = Query?.PageSize ?? Processed.length;
        if (PageSize <= 0) return Processed.slice();
        const Start = Page * PageSize;
        return Processed.slice(Start, Start + PageSize);
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    async GetTotalCount(Query) {
        const Processed = this._ApplyFilterAndSort(Query);
        return Processed.length;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    _ApplyFilterAndSort(Query) {
        const Key = JSON.stringify({ S: Query?.Sort ?? null, F: Query?.Filters ?? {} });
        if (Key === this._LastQueryKey && this._LastFiltered) return this._LastFiltered;
        let Result = this._Rows;
        const Filters = Query?.Filters ?? {};
        const FilterKeys = Object.keys(Filters).filter(K => Filters[K] !== null && Filters[K] !== undefined && Filters[K] !== '');
        if (FilterKeys.length > 0) {
            Result = Result.filter(Row => {
                for (const K of FilterKeys) {
                    const Needle = String(Filters[K]).toLowerCase();
                    const Hay = Row[K] == null ? '' : String(Row[K]).toLowerCase();
                    if (!Hay.includes(Needle)) return false;
                }
                return true;
            });
        }
        const Sort = Query?.Sort;
        if (Sort && Sort.Key) {
            const Dir = Sort.Direction === 'ASC' ? 1 : -1;
            Result = Result.slice().sort((A, B) => {
                const Va = A[Sort.Key]; const Vb = B[Sort.Key];
                if (Va == null && Vb == null) return 0;
                if (Va == null) return 1;
                if (Vb == null) return -1;
                if (Va < Vb) return -1 * Dir;
                if (Va > Vb) return 1 * Dir;
                return 0;
            });
        }
        this._LastQueryKey = Key;
        this._LastFiltered = Result;
        return Result;
    }
}
