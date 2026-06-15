// directive: table-renderer-service | // see shared-table-renderer.S1
import { IDataSource } from '../../static/js/TableRenderer/Interfaces/IDataSource.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
export class StubDataSource extends IDataSource {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor(SeedRows = []) {
        super();
        this._Rows = SeedRows.slice();
        this.LastQuery = null;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    async GetRows(Query) {
        this.LastQuery = Query;
        const Page = Query?.Page ?? 0;
        const PageSize = Query?.PageSize ?? this._Rows.length;
        const Start = Page * PageSize;
        return this._Rows.slice(Start, Start + PageSize);
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    async GetTotalCount(_Query) {
        return this._Rows.length;
    }
}
