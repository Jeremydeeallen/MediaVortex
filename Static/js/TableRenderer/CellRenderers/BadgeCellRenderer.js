import { ICellRenderer } from '../Interfaces/ICellRenderer.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
export class BadgeCellRenderer extends ICellRenderer {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor(Options = {}) {
        super();
        this._ClassMap = Options.ClassMap ?? {};
        this._DefaultClass = Options.DefaultClass ?? 'tr-badge-default';
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Render(Value, _Row, _Column) {
        const Span = document.createElement('span');
        const Key = Value == null ? '' : String(Value);
        const Extra = this._ClassMap[Key] ?? this._DefaultClass;
        Span.className = `tr-badge ${Extra}`.trim();
        Span.textContent = Key;
        return Span;
    }
}
