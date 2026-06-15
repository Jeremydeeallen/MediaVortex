// directive: table-renderer-service | // see shared-table-renderer.S1
export class IDataSource {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    async GetRows(_Query) { throw new Error('IDataSource.GetRows not implemented'); }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    async GetTotalCount(_Query) { throw new Error('IDataSource.GetTotalCount not implemented'); }
}

// directive: table-renderer-service | // see shared-table-renderer.S1
export function BuildQuery({ Page = 0, PageSize = 50, Sort = null, Filters = {} } = {}) {
    return Object.freeze({ Page, PageSize, Sort, Filters });
}
