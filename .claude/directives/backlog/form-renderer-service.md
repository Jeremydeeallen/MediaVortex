# Form Renderer Service

**Set:** 2026-06-13
**Status:** Backlog -- sequence position 6 in perfect-codebase set
**Slug:** form-renderer-service

## Outcome

Every form in the WebService is rendered by a single `FormRenderer` service that takes a declarative field config and produces a rendered, validated, submittable form. Validation rules, field types, edit modes, and submission flow are composable strategies. The shared `InlineEditor` pattern from `TableRenderer` extends here so an inline-edit cell and a form field reuse the same editor primitives.

## Acceptance Criteria

1. **Single form renderer.** `static/js/Forms/FormRenderer.js` accepts `{Model, Fields, Submit, Options}` and renders a form. Returns a `FormHandle` exposing `Submit()`, `Validate()`, `GetModel()`, `Reset()`, `Subscribe(EventName, Handler)`.

2. **No ad-hoc form HTML in templates for migrated forms.** Verifiable: each migrated template's form section is replaced by a `<div data-form="<slug>">` mount point and a `new FormRenderer({...}).MountTo(...)` call.

3. **SRP -- one responsibility per class.** `FormRenderer` (orchestrator + DOM mutation), `FieldDefinition` (declarative config), `ValidationController` (validation state + run), `SubmissionController` (submit flow), `FieldRenderer` (per-field rendering strategy), `FieldEditor` (per-field editor strategy), `DataBinder` (model<->form binding), `FormConfig`.

4. **Editor reuse with `TableRenderer`.** `FieldEditor` and `InlineEditor` from `table-renderer-service` share the same `IEditor` interface. A field's editor is interchangeable with a table-cell's editor. Verifiable: `ProfileSelectEditor` works in both a form field and a table cell with the same constructor.

5. **OCP -- new field type without renderer change.** Adding a new field type (e.g. tag-input, color-picker, file-drop) creates a `FieldRenderer` + `FieldEditor` pair. `FormRenderer.js` is not edited.

6. **LSP -- field renderer substitution.** Any `IFieldRenderer` plugs in.

7. **ISP -- focused interfaces.** `IFieldRenderer` (`Render(Field, Value)`, `Extract(Element)`), `IValidator` (`Validate(Value, Context)`), `ISubmissionStrategy` (`Submit(Model)`). No god-interface.

8. **DIP -- pages depend on `FormRenderer` abstract.** No page constructs form HTML strings.

9. **Validation pipeline.** Validation is a chain of `IValidator` instances per field (Required, MinLength, Regex, Custom). Composable. Field-level + form-level validation distinct. Verifiable: contract test composes a 4-validator chain, asserts failure at first triggered rule.

10. **Submission via `HttpClient`.** Default submission uses `HttpClient` from `ajax-client-service`. Pluggable for custom flows. Verifiable: grep ensures `FormRenderer` core does not import `fetch` / `$.ajax`.

11. **Accessibility.** Each field has an associated `<label>`; required fields announced via `aria-required`; validation errors announced via `aria-describedby` + `aria-invalid`. Axe-core zero violations.

12. **Feature doc owns the contract.** `Features/Forms/form-renderer.feature.md` exists with Workflows, Seams, Criteria, API Version.

13. **Contract tests.** `Tests/Static/TestFormRenderer.js` covers field rendering, validation chains, model binding round-trip, submission via stub transport.

14. **Migration completeness.** Forms migrated: Settings page, Profile editor, ShowSettings per-show config, Operations forms, Queue add-form, ClipBuilder. Single-input search boxes are out of scope (handled by `TableRenderer` filter API).

## Out of Scope

- Multi-step wizards (separate concern if pursued).
- File upload UI (separate concern; depends on chunking, progress).
- Rich-text / WYSIWYG editing.

## Constraints

- PascalCase per CLAUDE.md.
- No hardcoded validation messages -- all from a `FormConfig.Messages` table; pluggable for i18n later.
- No vendor form library.
- Built on top of `HttpClient`, `NotificationService`, `ClientLogger`, and reuses `TableRenderer`'s `IEditor` interface.

## Engineering Calls Already Made

- Validation as composable chain over monolithic validators.
- `IEditor` shared with `TableRenderer` -- same primitive used inline and in forms.
- Declarative `Fields` config over component subclassing.

## Status

Backlog 2026-06-13 -- sequence position 6. Depends on `table-renderer-service` (`IEditor` interface), `ajax-client-service`, `notification-service`, `client-logging-service`.

### Files

```
static/js/Forms/FormRenderer.js                     -- CREATE: orchestrator
static/js/Forms/FieldDefinition.js                  -- CREATE
static/js/Forms/ValidationController.js             -- CREATE
static/js/Forms/SubmissionController.js             -- CREATE
static/js/Forms/FieldRenderer.js                    -- CREATE: base + built-ins (text/number/select/checkbox/textarea/date)
static/js/Forms/DataBinder.js                       -- CREATE
static/js/Forms/FormConfig.js                       -- CREATE
static/js/Forms/Validators/RequiredValidator.js     -- CREATE
static/js/Forms/Validators/MinLengthValidator.js    -- CREATE
static/js/Forms/Validators/RegexValidator.js        -- CREATE
static/js/Forms/Validators/CustomValidator.js       -- CREATE
static/js/Forms/Interfaces/IFieldRenderer.js        -- CREATE
static/js/Forms/Interfaces/IValidator.js            -- CREATE
static/js/Forms/Interfaces/ISubmissionStrategy.js   -- CREATE
Features/Forms/form-renderer.feature.md             -- CREATE: the contract
Tests/Static/TestFormRenderer.js                    -- CREATE
Tests/Static/TestValidationChain.js                 -- CREATE
Tests/Static/TestDataBinder.js                      -- CREATE
Templates/Settings.html                             -- EDIT
Templates/ShowSettings.html                         -- EDIT (only the form portions; TableRenderer handles the tables)
Templates/Queue.html                                -- EDIT (add-form portion)
Templates/ClipBuilder.html                          -- EDIT
Templates/Operations.html                           -- EDIT
```

### Promotions / Verification / Decisions Made

To populate at appropriate phases.
