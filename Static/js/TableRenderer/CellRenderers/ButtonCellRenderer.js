import { ICellRenderer } from '../Interfaces/ICellRenderer.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
export class ButtonCellRenderer extends ICellRenderer {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor(Options = {}) {
        super();
        this._Label = Options.Label ?? 'Action';
        this._OnClick = Options.OnClick ?? null;
        this._ButtonClass = Options.ButtonClass ?? 'tr-button';
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Render(_Value, Row, Column) {
        const Button = document.createElement('button');
        Button.type = 'button';
        Button.className = this._ButtonClass;
        const Label = typeof this._Label === 'function' ? this._Label(Row, Column) : this._Label;
        Button.textContent = String(Label);
        if (this._OnClick) {
            Button.addEventListener('click', Evt => {
                Evt.stopPropagation();
                this._OnClick(Row, Column, Evt);
            });
        }
        return Button;
    }
}
