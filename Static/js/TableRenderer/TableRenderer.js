import { TableRendererConfig } from './TableRendererConfig.js';
import { EventBus } from './EventBus.js';
import { ColumnDefinition } from './ColumnDefinition.js';
import { CellRendererRegistry } from './CellRenderers/CellRendererRegistry.js';
import { InlineEditorRegistry } from './InlineEditors/InlineEditorRegistry.js';
import { BuildQuery } from './Interfaces/IDataSource.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
export class TableRenderer {
    // directive: table-renderer-service | // see shared-table-renderer.S1
    constructor(Spec) {
        if (!Spec) throw new Error('TableRenderer requires a Spec');
        if (!Spec.Container) throw new Error('TableRenderer.Spec.Container is required');
        if (!Spec.DataSource) throw new Error('TableRenderer.Spec.DataSource is required');
        if (!Array.isArray(Spec.Columns) || Spec.Columns.length === 0) {
            throw new Error('TableRenderer.Spec.Columns must be a non-empty array');
        }
        this._Container = Spec.Container;
        this._DataSource = Spec.DataSource;
        this._Columns = Spec.Columns.map(C => C instanceof ColumnDefinition ? C : new ColumnDefinition(C));
        this._Config = Spec.Config instanceof TableRendererConfig ? Spec.Config : new TableRendererConfig(Spec.Config ?? {});
        this._Bus = new EventBus();
        this._CellRegistry = Spec.CellRendererRegistry instanceof CellRendererRegistry
            ? Spec.CellRendererRegistry : new CellRendererRegistry();
        this._EditorRegistry = Spec.InlineEditorRegistry instanceof InlineEditorRegistry
            ? Spec.InlineEditorRegistry : new InlineEditorRegistry();
        this._Capabilities = Object.freeze({
            Sortable: !!Spec.Capabilities?.Sortable,
            Filterable: !!Spec.Capabilities?.Filterable,
            Paginatable: !!Spec.Capabilities?.Paginatable,
            Editable: !!Spec.Capabilities?.Editable,
            Virtualized: !!Spec.Capabilities?.Virtualized
        });
        this._SortController = Spec.SortController ?? null;
        this._FilterController = Spec.FilterController ?? null;
        this._PaginationController = Spec.PaginationController ?? null;
        this._Virtualizer = Spec.Virtualizer ?? null;
        this._ActiveEditor = null;
        this._TableEl = null;
        this._TheadEl = null;
        this._TbodyEl = null;
        this._ScrollEl = null;
        this._SpacerEl = null;
        this._LiveRegion = null;
        this._CurrentRows = [];
        this._TotalCount = 0;
        this._WireControllerEvents();
        this._WireCapabilityGate();
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    get Capabilities() { return this._Capabilities; }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Subscribe(EventName, Handler) { return this._Bus.Subscribe(EventName, Handler); }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    async Render() {
        this._BuildScaffold();
        await this.Refresh();
        return this;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    async Refresh() {
        const Query = this._BuildCurrentQuery();
        const Rows = await this._DataSource.GetRows(Query);
        const Total = await this._DataSource.GetTotalCount(Query);
        this._CurrentRows = Rows;
        this._TotalCount = Total;
        if (this._Capabilities.Paginatable && this._PaginationController) {
            this._PaginationController.SetTotalCount(Total);
        }
        if (this._Capabilities.Virtualized && this._Virtualizer) {
            this._Virtualizer.SetTotalRows(Rows.length);
            this._RenderVirtualizedBody();
        } else {
            this._RenderFullBody(Rows);
        }
        this._UpdateHeaderSortIndicators();
        this._AnnounceLive(`Showing ${Rows.length} of ${Total} rows`);
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    Destroy() {
        if (this._Virtualizer && this._Capabilities.Virtualized) this._Virtualizer.Detach();
        if (this._ActiveEditor) { this._ActiveEditor.Close(); this._ActiveEditor = null; }
        this._Container.innerHTML = '';
        this._Bus.Clear();
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    GetData() { return { Rows: this._CurrentRows.slice(), TotalCount: this._TotalCount }; }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    _WireCapabilityGate() {
        const HideIfMissing = (CapKey, Method) => {
            if (!this._Capabilities[CapKey]) Object.defineProperty(this, Method, { value: undefined, writable: false, configurable: false });
        };
        if (!this._Capabilities.Paginatable) {
            this.NextPage = undefined; this.PrevPage = undefined; this.GoToPage = undefined;
        } else {
            this.NextPage = () => this._PaginationController && this._PaginationController.NextPage();
            this.PrevPage = () => this._PaginationController && this._PaginationController.PrevPage();
            this.GoToPage = P => this._PaginationController && this._PaginationController.GoTo(P);
        }
        if (!this._Capabilities.Filterable) {
            this.SetFilter = undefined; this.ClearFilters = undefined;
        } else {
            this.SetFilter = (K, V) => this._FilterController && this._FilterController.SetFilter(K, V);
            this.ClearFilters = () => this._FilterController && this._FilterController.Clear();
        }
        if (!this._Capabilities.Sortable) {
            this.SetSort = undefined; this.ResetSort = undefined;
        } else {
            this.SetSort = (K, D) => this._SortController && this._SortController.SetSort(K, D);
            this.ResetSort = () => this._SortController && this._SortController.Reset();
        }
        HideIfMissing('Sortable', '_SortIndicatorNoop');
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    _WireControllerEvents() {
        const OnChange = () => { this.Refresh().catch(Err => console.error('TableRenderer.Refresh failed:', Err)); };
        if (this._Capabilities.Sortable && this._SortController) {
            this._SortController.GetSortState && this._Bus.Subscribe(EventBus.EventNames.SortChanged, OnChange);
        }
        if (this._Capabilities.Filterable && this._FilterController) {
            this._Bus.Subscribe(EventBus.EventNames.FilterChanged, OnChange);
        }
        if (this._Capabilities.Paginatable && this._PaginationController) {
            this._Bus.Subscribe(EventBus.EventNames.PageChanged, OnChange);
        }
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    _BuildCurrentQuery() {
        const Sort = (this._Capabilities.Sortable && this._SortController) ? this._SortController.GetSortState() : null;
        const Filters = (this._Capabilities.Filterable && this._FilterController) ? this._FilterController.GetFilterState() : {};
        const Page = (this._Capabilities.Paginatable && this._PaginationController) ? this._PaginationController.GetPage() : 0;
        const PageSize = (this._Capabilities.Paginatable && this._PaginationController)
            ? this._PaginationController.GetPageSize()
            : this._Config.DefaultPageSize;
        return BuildQuery({ Page, PageSize, Sort, Filters });
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    _BuildScaffold() {
        this._Container.innerHTML = '';
        this._Container.classList.add('tr-root');
        const Live = document.createElement('div');
        Live.className = 'tr-live';
        Live.setAttribute('aria-live', 'polite');
        Live.setAttribute('aria-atomic', 'true');
        this._Container.appendChild(Live);
        this._LiveRegion = Live;
        const Scroll = document.createElement('div');
        Scroll.className = 'tr-scroll';
        Scroll.style.position = 'relative';
        Scroll.style.overflow = 'auto';
        this._Container.appendChild(Scroll);
        this._ScrollEl = Scroll;
        const Table = document.createElement('table');
        Table.className = 'tr-table';
        Table.setAttribute('role', 'table');
        Scroll.appendChild(Table);
        const Thead = document.createElement('thead');
        Table.appendChild(Thead);
        const Tbody = document.createElement('tbody');
        Table.appendChild(Tbody);
        this._TableEl = Table; this._TheadEl = Thead; this._TbodyEl = Tbody;
        this._BuildHeader();
        if (this._Capabilities.Virtualized && this._Virtualizer) {
            const Spacer = document.createElement('div');
            Spacer.className = 'tr-spacer';
            Spacer.style.position = 'absolute';
            Spacer.style.left = '0';
            Spacer.style.top = '0';
            Spacer.style.width = '1px';
            Spacer.style.pointerEvents = 'none';
            Scroll.appendChild(Spacer);
            this._SpacerEl = Spacer;
            this._Virtualizer.Attach(Scroll, this._CurrentRows.length, this._Config.RowHeightPx);
            this._Virtualizer.OnRangeChange(() => this._RenderVirtualizedBody());
        }
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    _BuildHeader() {
        this._TheadEl.innerHTML = '';
        const Tr = document.createElement('tr');
        for (const Col of this._Columns) {
            const Th = document.createElement('th');
            Th.setAttribute('scope', 'col');
            Th.className = `tr-th ${Col.HeaderClass}`.trim();
            Th.dataset.key = Col.Key;
            if (Col.Width) Th.style.width = Col.Width;
            Th.textContent = Col.Header;
            if (this._Capabilities.Sortable && Col.Sortable) {
                Th.classList.add('tr-th-sortable');
                Th.setAttribute('aria-sort', 'none');
                Th.tabIndex = 0;
                const DoSort = () => this._SortController && this._SortController.SetSort(Col.Key);
                Th.addEventListener('click', DoSort);
                Th.addEventListener('keydown', Evt => {
                    if (Evt.key === 'Enter' || Evt.key === ' ') { Evt.preventDefault(); DoSort(); }
                });
            }
            Tr.appendChild(Th);
        }
        this._TheadEl.appendChild(Tr);
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    _UpdateHeaderSortIndicators() {
        if (!this._Capabilities.Sortable || !this._SortController) return;
        const State = this._SortController.GetSortState();
        const Ths = this._TheadEl.querySelectorAll('th');
        Ths.forEach(Th => {
            const Key = Th.dataset.key;
            if (!Th.classList.contains('tr-th-sortable')) return;
            if (State && State.Key === Key) {
                Th.setAttribute('aria-sort', State.Direction === 'ASC' ? 'ascending' : 'descending');
            } else {
                Th.setAttribute('aria-sort', 'none');
            }
        });
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    _RenderFullBody(Rows) {
        this._TbodyEl.innerHTML = '';
        const Frag = document.createDocumentFragment();
        for (let I = 0; I < Rows.length; I += 1) {
            Frag.appendChild(this._BuildRow(Rows[I], I, null));
        }
        this._TbodyEl.appendChild(Frag);
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    _RenderVirtualizedBody() {
        if (!this._Virtualizer || !this._SpacerEl) return;
        const Range = this._Virtualizer.VisibleRange();
        this._SpacerEl.style.height = `${this._Virtualizer.TotalHeightPx()}px`;
        this._TbodyEl.innerHTML = '';
        const Frag = document.createDocumentFragment();
        for (let I = Range.Start; I < Range.End; I += 1) {
            const Row = this._CurrentRows[I];
            if (!Row) continue;
            const Tr = this._BuildRow(Row, I, this._Virtualizer.RowTopPx(I));
            Tr.style.position = 'absolute';
            Tr.style.top = `${this._Virtualizer.RowTopPx(I)}px`;
            Tr.style.left = '0';
            Tr.style.right = '0';
            Tr.style.height = `${this._Virtualizer.RowHeightPx()}px`;
            Frag.appendChild(Tr);
        }
        this._TbodyEl.appendChild(Frag);
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    _BuildRow(Row, Index, _TopPx) {
        const Tr = document.createElement('tr');
        Tr.className = 'tr-row';
        Tr.dataset.index = String(Index);
        Tr.addEventListener('click', Evt => {
            this._Bus.Emit(EventBus.EventNames.RowClicked, { Row, Index, Event: Evt });
        });
        for (const Col of this._Columns) {
            Tr.appendChild(this._BuildCell(Row, Index, Col));
        }
        return Tr;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    _BuildCell(Row, Index, Col) {
        const Td = document.createElement('td');
        Td.className = `tr-cell ${Col.CellClass}`.trim();
        Td.dataset.key = Col.Key;
        Td.style.textAlign = Col.Align;
        const Renderer = this._CellRegistry.Instantiate(Col.CellRendererName, Col.CellRendererOptions);
        const Value = Row ? Row[Col.Key] : null;
        Td.appendChild(Renderer.Render(Value, Row, Col));
        if (this._Capabilities.Editable && Col.Editable && Col.EditorName) {
            Td.classList.add('tr-cell-editable');
            Td.addEventListener('dblclick', Evt => {
                Evt.stopPropagation();
                this._OpenEditor(Td, Row, Index, Col, Value);
            });
        }
        return Td;
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    _OpenEditor(Cell, Row, Index, Col, CurrentValue) {
        if (!this._Capabilities.Editable) return;
        if (this._ActiveEditor) this._ActiveEditor.Close();
        const Editor = this._EditorRegistry.Instantiate(Col.EditorName, Col.EditorOptions);
        this._ActiveEditor = Editor;
        Editor.Open(Cell, Row, Col, CurrentValue,
            (NewValue) => {
                this._ActiveEditor = null;
                this._Bus.Emit(EventBus.EventNames.CellEdited, {
                    Row, Index, Column: Col, Key: Col.Key, OldValue: CurrentValue, NewValue
                });
            },
            () => { this._ActiveEditor = null; }
        );
    }

    // directive: table-renderer-service | // see shared-table-renderer.S1
    _AnnounceLive(Message) {
        if (!this._LiveRegion) return;
        this._LiveRegion.textContent = Message;
    }
}
