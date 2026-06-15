import { IInlineEditor } from '../Interfaces/IInlineEditor.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
export class SelectInlineEditor extends IInlineEditor {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor(Options = {}) {
        super();
        this._OptionsLoader = Options.OptionsLoader ?? null;
        this._SelectClass = Options.SelectClass ?? 'tr-inline-select';
        this._ValueKey = Options.ValueKey ?? 'Value';
        this._LabelKey = Options.LabelKey ?? 'Label';
        this._Cell = null;
        this._Select = null;
        this._Prev = null;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    async Open(Cell, Row, Column, CurrentValue, OnCommit, OnCancel) {
        this.Close();
        this._Cell = Cell;
        this._Prev = Cell.innerHTML;
        const Select = document.createElement('select');
        Select.className = this._SelectClass;
        Cell.innerHTML = '';
        Cell.appendChild(Select);
        let Options = [];
        try {
            if (this._OptionsLoader) Options = await this._OptionsLoader(Row, Column);
        } catch (Err) {
            console.error('SelectInlineEditor options load failed:', Err);
            OnCancel && OnCancel(Row, Column);
            this._RestoreCell();
            return;
        }
        for (const Opt of (Options ?? [])) {
            const O = document.createElement('option');
            const Val = (Opt && typeof Opt === 'object') ? Opt[this._ValueKey] : Opt;
            const Lab = (Opt && typeof Opt === 'object') ? (Opt[this._LabelKey] ?? Val) : Opt;
            O.value = Val == null ? '' : String(Val);
            O.textContent = Lab == null ? '' : String(Lab);
            if (CurrentValue != null && String(CurrentValue) === O.value) O.selected = true;
            Select.appendChild(O);
        }
        Select.focus();
        const DoCommit = () => {
            Select.removeEventListener('change', OnChange);
            Select.removeEventListener('blur', OnBlur);
            Select.removeEventListener('keydown', OnKey);
            const NewValue = Select.value;
            this._RestoreCell();
            OnCommit && OnCommit(NewValue, Row, Column);
        };
        const DoCancel = () => {
            Select.removeEventListener('change', OnChange);
            Select.removeEventListener('blur', OnBlur);
            Select.removeEventListener('keydown', OnKey);
            this._RestoreCell();
            OnCancel && OnCancel(Row, Column);
        };
        const OnChange = () => DoCommit();
        const OnBlur = () => DoCommit();
        const OnKey = Evt => {
            if (Evt.key === 'Escape') { Evt.preventDefault(); DoCancel(); }
            else if (Evt.key === 'Enter') { Evt.preventDefault(); DoCommit(); }
        };
        Select.addEventListener('change', OnChange);
        Select.addEventListener('blur', OnBlur);
        Select.addEventListener('keydown', OnKey);
        this._Select = Select;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Close() {
        if (this._Cell && this._Select) this._RestoreCell();
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    _RestoreCell() {
        if (this._Cell && this._Prev != null) this._Cell.innerHTML = this._Prev;
        this._Cell = null;
        this._Select = null;
        this._Prev = null;
    }
}
