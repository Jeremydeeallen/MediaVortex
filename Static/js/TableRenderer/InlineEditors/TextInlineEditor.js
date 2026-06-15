import { IInlineEditor } from '../Interfaces/IInlineEditor.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
export class TextInlineEditor extends IInlineEditor {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor(Options = {}) {
        super();
        this._InputType = Options.InputType ?? 'text';
        this._InputClass = Options.InputClass ?? 'tr-inline-input';
        this._Cell = null;
        this._Input = null;
        this._Prev = null;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Open(Cell, Row, Column, CurrentValue, OnCommit, OnCancel) {
        this.Close();
        this._Cell = Cell;
        this._Prev = Cell.innerHTML;
        const Input = document.createElement('input');
        Input.type = this._InputType;
        Input.className = this._InputClass;
        Input.value = CurrentValue == null ? '' : String(CurrentValue);
        Cell.innerHTML = '';
        Cell.appendChild(Input);
        Input.focus();
        Input.select && Input.select();
        const DoCommit = () => {
            Input.removeEventListener('blur', OnBlur);
            Input.removeEventListener('keydown', OnKey);
            const NewValue = Input.value;
            this._RestoreCell();
            OnCommit && OnCommit(NewValue, Row, Column);
        };
        const DoCancel = () => {
            Input.removeEventListener('blur', OnBlur);
            Input.removeEventListener('keydown', OnKey);
            this._RestoreCell();
            OnCancel && OnCancel(Row, Column);
        };
        const OnBlur = () => DoCommit();
        const OnKey = Evt => {
            if (Evt.key === 'Enter') { Evt.preventDefault(); DoCommit(); }
            else if (Evt.key === 'Escape') { Evt.preventDefault(); DoCancel(); }
        };
        Input.addEventListener('blur', OnBlur);
        Input.addEventListener('keydown', OnKey);
        this._Input = Input;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Close() {
        if (this._Cell && this._Input) this._RestoreCell();
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    _RestoreCell() {
        if (this._Cell && this._Prev != null) this._Cell.innerHTML = this._Prev;
        this._Cell = null;
        this._Input = null;
        this._Prev = null;
    }
}
