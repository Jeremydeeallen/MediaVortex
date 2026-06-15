import { ICellRenderer } from '../Interfaces/ICellRenderer.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
export class NumberCellRenderer extends ICellRenderer {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor(Options = {}) {
        super();
        this._Locale = Options.Locale ?? undefined;
        this._FormatOptions = Options.FormatOptions ?? undefined;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Render(Value, _Row, _Column) {
        const Span = document.createElement('span');
        Span.className = 'tr-cell-number';
        if (Value == null || Value === '') { Span.textContent = ''; return Span; }
        const N = Number(Value);
        if (Number.isNaN(N)) { Span.textContent = String(Value); return Span; }
        Span.textContent = N.toLocaleString(this._Locale, this._FormatOptions);
        return Span;
    }
}
