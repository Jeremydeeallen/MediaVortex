// directive: table-renderer-service | // see shared-table-renderer.S1
export class IVirtualizer {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    Attach(_Container, _TotalRows, _RowHeight) { throw new Error('IVirtualizer.Attach not implemented'); }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    VisibleRange() { throw new Error('IVirtualizer.VisibleRange not implemented'); }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Detach() { throw new Error('IVirtualizer.Detach not implemented'); }
}
