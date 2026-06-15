import { ISortController } from './Interfaces/ISortController.js';
import { EventBus } from './EventBus.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
export class SortController extends ISortController {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor(DataSource, Bus, Config) {
        super();
        if (!DataSource) throw new Error('SortController requires a DataSource');
        if (!Bus) throw new Error('SortController requires an EventBus');
        if (!Config) throw new Error('SortController requires a Config');
        this._DataSource = DataSource;
        this._Bus = Bus;
        this._Config = Config;
        this._State = null;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    GetSortState() { return this._State ? { ...this._State } : null; }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    SetSort(ColumnKey, Direction) {
        if (!ColumnKey) { this.Reset(); return; }
        let NextDir = Direction;
        if (!NextDir) {
            if (this._State && this._State.Key === ColumnKey) {
                NextDir = this._State.Direction === 'ASC' ? 'DESC' : 'ASC';
            } else {
                NextDir = this._Config.DefaultSortDirection;
            }
        }
        NextDir = String(NextDir).toUpperCase();
        if (NextDir !== 'ASC' && NextDir !== 'DESC') NextDir = this._Config.DefaultSortDirection;
        this._State = { Key: ColumnKey, Direction: NextDir };
        this._Bus.Emit(EventBus.EventNames.SortChanged, { ...this._State });
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Reset() {
        if (this._State === null) return;
        this._State = null;
        this._Bus.Emit(EventBus.EventNames.SortChanged, null);
    }
}
