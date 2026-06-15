// directive: table-renderer-service | // see shared-table-renderer.S1
export class IInlineEditor {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    Open(_Cell, _Row, _Column, _CurrentValue, _OnCommit, _OnCancel) {
        throw new Error('IInlineEditor.Open not implemented');
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Close() { throw new Error('IInlineEditor.Close not implemented'); }
}
