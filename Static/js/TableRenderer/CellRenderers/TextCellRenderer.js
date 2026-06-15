import { ICellRenderer } from '../Interfaces/ICellRenderer.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
export class TextCellRenderer extends ICellRenderer {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor(Options = {}) {
        super();
        this._Options = Options;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Render(Value, _Row, _Column) {
        const Span = document.createElement('span');
        Span.className = 'tr-cell-text';
        Span.textContent = Value == null ? '' : String(Value);
        return Span;
    }
}
