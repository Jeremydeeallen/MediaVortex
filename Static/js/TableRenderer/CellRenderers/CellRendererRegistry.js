import { TextCellRenderer } from './TextCellRenderer.js';
import { NumberCellRenderer } from './NumberCellRenderer.js';
import { BadgeCellRenderer } from './BadgeCellRenderer.js';
import { ButtonCellRenderer } from './ButtonCellRenderer.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
export class CellRendererRegistry {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor() {
        this._Map = new Map();
        this.Register('Text', TextCellRenderer);
        this.Register('Number', NumberCellRenderer);
        this.Register('Badge', BadgeCellRenderer);
        this.Register('Button', ButtonCellRenderer);
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Register(Name, Cls) {
        if (!Name || typeof Name !== 'string') throw new Error('Register requires a Name string');
        if (typeof Cls !== 'function') throw new Error('Register requires a class');
        this._Map.set(Name, Cls);
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Resolve(Name) {
        const Cls = this._Map.get(Name);
        if (!Cls) throw new Error(`No CellRenderer registered for '${Name}'`);
        return Cls;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Has(Name) { return this._Map.has(Name); }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Instantiate(Name, Options) {
        const Cls = this.Resolve(Name);
        return new Cls(Options);
    }
}
