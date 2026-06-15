// directive: table-renderer-service | // see shared-table-renderer.S1
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { TableRenderer } from '../../static/js/TableRenderer/TableRenderer.js';
import { ColumnDefinition } from '../../static/js/TableRenderer/ColumnDefinition.js';
import { TableRendererConfig } from '../../static/js/TableRenderer/TableRendererConfig.js';
import { ClientArrayDataSource } from '../../static/js/TableRenderer/DataSources/ClientArrayDataSource.js';
import { ServerPagedDataSource } from '../../static/js/TableRenderer/DataSources/ServerPagedDataSource.js';
import { PaginationController } from '../../static/js/TableRenderer/PaginationController.js';
import { Virtualizer } from '../../static/js/TableRenderer/Virtualizer.js';
import { EventBus } from '../../static/js/TableRenderer/EventBus.js';
import { StubDataSource } from './_StubDataSource.js';
import { InstallGlobalDocument } from './_MockDocument.js';

// directive: table-renderer-service | // see shared-table-renderer.S1
function Seed(N) { return Array.from({ length: N }, (_, I) => ({ Id: I, Name: `n${I}`, Score: I % 100 })); }

// directive: table-renderer-service | // see shared-table-renderer.S1
function MakeColumns() {
    return [
        new ColumnDefinition({ Key: 'Id', Header: 'Id', Sortable: true }),
        new ColumnDefinition({ Key: 'Name', Header: 'Name', Sortable: true, Filterable: true }),
        new ColumnDefinition({ Key: 'Score', Header: 'Score', Sortable: true })
    ];
}

/** Constructor wires DataSource + Columns without throwing */
test('TableRenderer instantiates with stub data source', async () => {
    const Doc = InstallGlobalDocument();
    const Host = Doc.createElement('div');
    const T = new TableRenderer({
        Container: Host, Columns: MakeColumns(),
        DataSource: new StubDataSource(Seed(10)),
        Config: new TableRendererConfig()
    });
    await T.Render();
    assert.ok(T);
});

/** Subscribe('PageChanged') receives events from the renderer (C15) */
test('Subscribe PageChanged delivers events (C15)', async () => {
    const Doc = InstallGlobalDocument();
    const Host = Doc.createElement('div');
    const Cfg = new TableRendererConfig({ DefaultPageSize: 10 });
    const DS = new StubDataSource(Seed(100));
    const Bus = new EventBus();
    const Pag = new PaginationController(DS, Bus, Cfg);
    const T = new TableRenderer({
        Container: Host, Columns: MakeColumns(),
        DataSource: DS, Config: Cfg,
        Capabilities: { Paginatable: true },
        PaginationController: Pag
    });
    let Got = null;
    Bus.Subscribe('PageChanged', (P) => { Got = P; });
    await T.Render();
    Pag.SetTotalCount(100);
    T.NextPage();
    assert.ok(Got !== null, 'PageChanged should fire');
});

/** Unsubscribe stops further callbacks (C15) */
test('Unsubscribe stops further events (C15)', async () => {
    const Doc = InstallGlobalDocument();
    const Host = Doc.createElement('div');
    const Cfg = new TableRendererConfig({ DefaultPageSize: 10 });
    const DS = new StubDataSource(Seed(100));
    const Bus = new EventBus();
    const Pag = new PaginationController(DS, Bus, Cfg);
    const T = new TableRenderer({
        Container: Host, Columns: MakeColumns(),
        DataSource: DS, Config: Cfg,
        Capabilities: { Paginatable: true },
        PaginationController: Pag
    });
    let Count = 0;
    const Off = Bus.Subscribe('PageChanged', () => { Count++; });
    await T.Render();
    Pag.SetTotalCount(100);
    T.NextPage();
    Off();
    T.NextPage();
    assert.equal(Count, 1);
});

/** Renders a semantic <table> with <thead>/<tbody> */
test('DOM render produces table > thead + tbody', async () => {
    const Doc = InstallGlobalDocument();
    const Host = Doc.createElement('div');
    const T = new TableRenderer({
        Container: Host, Columns: MakeColumns(),
        DataSource: new StubDataSource(Seed(5)),
        Config: new TableRendererConfig()
    });
    await T.Render();
    assert.ok(Host.querySelector('table'), 'expected <table>');
    assert.ok(Host.querySelector('thead'), 'expected <thead>');
    assert.ok(Host.querySelector('tbody'), 'expected <tbody>');
});

/** C8 virtualization: 4000 rows yields < 150 tr elements when Virtualized capability on */
test('C8: virtualization keeps tr count < 150 at 4000 rows', async () => {
    const Doc = InstallGlobalDocument();
    const Host = Doc.createElement('div');
    Host.scrollTop = 0;
    Host.clientHeight = 320;
    const Cfg = new TableRendererConfig({ VirtualizationThreshold: 500, RowHeightPx: 32, BufferRows: 10 });
    const DS = new StubDataSource(Seed(4000));
    const Vrt = new Virtualizer(Cfg);
    const T = new TableRenderer({
        Container: Host, Columns: MakeColumns(),
        DataSource: DS, Config: Cfg,
        Capabilities: { Virtualized: true },
        Virtualizer: Vrt
    });
    await T.Render();
    const Trs = Host.querySelectorAll('tr');
    assert.ok(Trs.length < 150, `expected < 150 tr, got ${Trs.length}`);
});

/** C4 LSP: swapping DataSource needs no other changes */
test('C4 LSP: ClientArrayDataSource <-> ServerPagedDataSource swap', async () => {
    const Doc = InstallGlobalDocument();
    const Rows = Seed(20);
    const ClientDS = new ClientArrayDataSource(Rows);
    // directive: table-renderer-service | // see shared-table-renderer.S1
    const Fetch = async () => ({
        ok: true, status: 200,
        json: async () => ({ Rows, TotalCount: Rows.length })
    });
    const ServerDS = new ServerPagedDataSource('/api/Stub', { Fetch });
    const Host1 = Doc.createElement('div');
    const Host2 = Doc.createElement('div');
    const T1 = new TableRenderer({ Container: Host1, Columns: MakeColumns(), DataSource: ClientDS, Config: new TableRendererConfig() });
    const T2 = new TableRenderer({ Container: Host2, Columns: MakeColumns(), DataSource: ServerDS, Config: new TableRendererConfig() });
    await T1.Render();
    await T2.Render();
    const R1 = Host1.querySelectorAll('tr').length;
    const R2 = Host2.querySelectorAll('tr').length;
    assert.equal(R1, R2, `client ${R1} should equal server ${R2}`);
});

/** C13 ISP: read-only non-paginated table does not expose NextPage / SetFilter */
test('C13 ISP: read-only table has no NextPage or SetFilter', async () => {
    const Doc = InstallGlobalDocument();
    const Host = Doc.createElement('div');
    const T = new TableRenderer({
        Container: Host, Columns: MakeColumns(),
        DataSource: new StubDataSource(Seed(5)),
        Config: new TableRendererConfig(),
        Capabilities: { Paginatable: false, Sortable: false, Filterable: false, Editable: false }
    });
    await T.Render();
    assert.equal(T.NextPage, undefined, 'NextPage should not be exposed without Paginatable');
    assert.equal(T.SetFilter, undefined, 'SetFilter should not be exposed without Filterable');
});
