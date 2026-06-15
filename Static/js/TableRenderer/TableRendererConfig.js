// directive: table-renderer-service | // see shared-table-renderer.S1
export class TableRendererConfig {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor(overrides = {}) {
        this.DefaultPageSize = overrides.DefaultPageSize ?? 50;
        this.VirtualizationThreshold = overrides.VirtualizationThreshold ?? 500;
        this.DebounceMs = overrides.DebounceMs ?? 200;
        this.BufferRows = overrides.BufferRows ?? 10;
        this.RowHeightPx = overrides.RowHeightPx ?? 32;
        this.DefaultSortDirection = overrides.DefaultSortDirection ?? 'DESC';
        this.MaxCachedResponses = overrides.MaxCachedResponses ?? 8;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    With(overrides) {
        return new TableRendererConfig({ ...this, ...overrides });
    }
}
