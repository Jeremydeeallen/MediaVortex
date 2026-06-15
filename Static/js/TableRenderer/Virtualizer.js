import { IVirtualizer } from './Interfaces/IVirtualizer.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
export class Virtualizer extends IVirtualizer {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor(Config) {
        super();
        if (!Config) throw new Error('Virtualizer requires a Config');
        this._Config = Config;
        this._Container = null;
        this._TotalRows = 0;
        this._RowHeight = Config.RowHeightPx;
        this._OnRangeChange = null;
        this._ScrollHandler = null;
        this._ResizeObserver = null;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Attach(Container, TotalRows, RowHeight) {
        if (!Container) throw new Error('Virtualizer.Attach requires a container');
        this._Container = Container;
        this._TotalRows = Math.max(0, Number(TotalRows) || 0);
        this._RowHeight = Math.max(1, Number(RowHeight) || this._Config.RowHeightPx);
        if (this._ScrollHandler) Container.removeEventListener('scroll', this._ScrollHandler);
        this._ScrollHandler = () => { if (this._OnRangeChange) this._OnRangeChange(this.VisibleRange()); };
        Container.addEventListener('scroll', this._ScrollHandler, { passive: true });
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    SetTotalRows(TotalRows) {
        this._TotalRows = Math.max(0, Number(TotalRows) || 0);
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    OnRangeChange(Handler) { this._OnRangeChange = Handler; }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    VisibleRange() {
        if (!this._Container || this._TotalRows === 0) return { Start: 0, End: 0 };
        const ScrollTop = this._Container.scrollTop || 0;
        const ViewportHeight = this._Container.clientHeight || 0;
        const Buffer = this._Config.BufferRows;
        const RawStart = Math.floor(ScrollTop / this._RowHeight) - Buffer;
        const VisibleCount = Math.ceil(ViewportHeight / this._RowHeight) + 2 * Buffer;
        const Start = Math.max(0, RawStart);
        const End = Math.min(this._TotalRows, Start + VisibleCount);
        return { Start, End };
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    TotalHeightPx() { return this._TotalRows * this._RowHeight; }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    RowTopPx(Index) { return Index * this._RowHeight; }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    RowHeightPx() { return this._RowHeight; }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Detach() {
        if (this._Container && this._ScrollHandler) {
            this._Container.removeEventListener('scroll', this._ScrollHandler);
        }
        this._Container = null;
        this._ScrollHandler = null;
        this._OnRangeChange = null;
    }
}
