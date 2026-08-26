/**
 * Tesla Maintenance Tracker - Lovelace card
 *
 * A full maintenance console: view, add, edit and delete service records,
 * maintenance items, schedules, tires and brakes without leaving the dashboard.
 *
 * Usage:
 *   type: custom:tesla-maintenance-card
 *   vehicle_id: 1          # optional, only needed with multiple vehicles
 *   history_limit: 50      # optional
 */

const VERSION = "1.3.0";

const STATUS_META = {
  OVERDUE: { label: "Overdue", icon: "⛔", cls: "st-overdue" },
  DUE: { label: "Due", icon: "⚠️", cls: "st-due" },
  DUE_SOON: { label: "Due soon", icon: "⚠️", cls: "st-soon" },
  OK: { label: "OK", icon: "✅", cls: "st-ok" },
  COMPLETED: { label: "Completed", icon: "✅", cls: "st-ok" },
  DISABLED: { label: "Disabled", icon: "⏸", cls: "st-off" },
};

const TIRE_POSITIONS = ["Front Left", "Front Right", "Rear Left", "Rear Right"];
const BRAKE_CONDITIONS = ["Good", "Fair", "Needs Service", "Replace"];

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]
  );

// Escapes first, then applies a tiny, safe markdown subset so notes can carry
// **bold** and *italic* emphasis. Because escaping runs first, raw HTML typed
// into a note can never be injected - only these two patterns are recognized.
const richText = (value) => {
  let out = esc(value);
  out = out.replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>");
  out = out.replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, "<i>$1</i>");
  return out;
};

const today = () => new Date().toISOString().slice(0, 10);

const money = (value, currency) =>
  value === null || value === undefined || value === ""
    ? "—"
    : `${currency === "USD" ? "$" : ""}${Number(value).toFixed(2)}${
        currency === "USD" ? "" : " " + currency
      }`;

const num = (value) =>
  value === null || value === undefined || value === ""
    ? "—"
    : Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });

class TeslaMaintenanceCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "overview";
    this._data = null;
    this._loading = false;
    this._error = null;
    this._editing = null; // {kind, id}
    this._openRecord = null;
    this._search = "";
    this._rendered = false;
  }

  setConfig(config) {
    this._config = config || {};
  }

  static getStubConfig() {
    return {};
  }

  getCardSize() {
    return 12;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._render();
      this._load();
    }
  }

  // ----------------------------------------------------------------- data
  _target(extra = {}) {
    const target = { ...extra };
    if (this._config.vehicle_id) target.vehicle_id = this._config.vehicle_id;
    if (this._config.entry_id) target.entry_id = this._config.entry_id;
    return target;
  }

  async _call(service, data = {}, wantResponse = false) {
    const result = await this._hass.callWS({
      type: "call_service",
      domain: "tesla_maintenance",
      service,
      service_data: this._target(data),
      return_response: wantResponse,
    });
    return wantResponse ? result.response : result;
  }

  async _load() {
    this._loading = true;
    this._error = null;
    this._paint();
    try {
      this._data = await this._call(
        "get_data",
        { history_limit: this._config.history_limit || 50 },
        true
      );
    } catch (err) {
      this._error =
        (err && (err.message || err.error)) ||
        "Could not load maintenance data. Is the integration set up?";
    }
    this._loading = false;
    this._paint();
  }

  async _act(service, data, confirmText) {
    if (confirmText && !window.confirm(confirmText)) return;
    try {
      await this._call(service, data);
      this._editing = null;
      await this._load();
      this._toast("Saved");
    } catch (err) {
      this._toast((err && (err.message || err.error)) || "Action failed", true);
    }
  }

  _toast(message, isError) {
    const el = this.shadowRoot.getElementById("toast");
    if (!el) return;
    el.textContent = message;
    el.className = `toast show${isError ? " err" : ""}`;
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => (el.className = "toast"), 3200);
  }

  // ----------------------------------------------------------------- render
  _render() {
    this.shadowRoot.innerHTML = `<style>${this._css()}</style>
      <ha-card>
        <div id="root"></div>
        <div id="toast" class="toast"></div>
      </ha-card>`;
    this._rendered = true;
    this.shadowRoot.getElementById("root").addEventListener("click", (event) =>
      this._onClick(event)
    );
    this.shadowRoot.getElementById("root").addEventListener("input", (event) => {
      if (event.target.id === "search") {
        this._search = event.target.value;
        this._paint(true);
        const box = this.shadowRoot.getElementById("search");
        if (box) {
          box.focus();
          box.setSelectionRange(box.value.length, box.value.length);
        }
      }
    });
  }

  _paint() {
    if (!this._rendered) return;
    const root = this.shadowRoot.getElementById("root");
    if (this._loading && !this._data) {
      root.innerHTML = `<div class="pad muted">Loading maintenance data…</div>`;
      return;
    }
    if (this._error) {
      root.innerHTML = `<div class="pad"><div class="err-box">${esc(
        this._error
      )}</div><button class="btn" data-act="reload">Retry</button></div>`;
      return;
    }
    if (!this._data) return;

    const d = this._data;
    root.innerHTML = `
      <div class="head">
        <div class="head-main">
          <div class="title-row">
            <div class="title">${esc(d.vehicle.name)}</div>
            <div class="health ${this._healthClass(d.health)}">
              <span class="health-dot"></span>${esc(d.health)}
            </div>
          </div>
          <div class="sub">
            <span class="sub-mileage">${num(d.current_mileage)} ${esc(d.distance_unit)}</span>
            ${
              d.telemetry_available
                ? ""
                : '<span class="pill pill-warn">Telemetry offline</span>'
            }
          </div>
        </div>
      </div>
      <div class="tabs">
        ${this._tabBtn("overview", "Overview")}
        ${this._tabBtn("schedules", "Schedules")}
        ${this._tabBtn("history", "History")}
        ${this._tabBtn("add", "Add")}
        ${this._tabBtn("tires", "Tires")}
      </div>
      <div class="body">${this._tabBody()}</div>`;
  }

  _healthClass(health) {
    return health === "OVERDUE"
      ? "st-overdue"
      : health === "NEEDS ATTENTION"
        ? "st-due"
        : health === "GOOD"
          ? "st-ok"
          : "st-off";
  }

  _tabBtn(id, label) {
    return `<button class="tab ${this._tab === id ? "on" : ""}" data-tab="${id}">${label}</button>`;
  }

  _tabBody() {
    switch (this._tab) {
      case "schedules":
        return this._viewSchedules();
      case "history":
        return this._viewHistory();
      case "add":
        return this._viewAdd();
      case "tires":
        return this._viewTires();
      default:
        return this._viewOverview();
    }
  }
  // ----------------------------------------------------------------- views
  _viewOverview() {
    const d = this._data;
    const a = d.analytics || {};
    const attention = (d.statuses || []).filter(
      (s) => s.status !== "OK" && s.status !== "DISABLED"
    );
    const recent = (d.records || []).slice(0, 3);

    return `
      <div class="stats">
        ${this._stat("Total spent", money(a.total_cost, d.currency), "primary")}
        ${this._stat("This year", money(a.cost_this_year, d.currency))}
        ${this._stat("Records", a.service_count ?? 0)}
        ${this._stat(
          `Cost / ${d.distance_unit}`,
          a.cost_per_mile == null ? "—" : money(a.cost_per_mile, d.currency)
        )}
      </div>

      <div class="section-head">Needs attention</div>
      ${
        attention.length === 0
          ? this._emptyGood("Everything is up to date")
          : attention.map((s) => this._scheduleRow(s, true)).join("")
      }

      <div class="section-head">Recent service</div>
      ${
        recent.length === 0
          ? this._emptyState("No service records yet", "Use the Add tab to log your first one.")
          : recent.map((r) => this._recordRow(r)).join("")
      }

      ${this._costBreakdown(a, d.currency)}
      ${this._telemetryDetails(d)}`;
  }

  _details(label, bodyHtml) {
    return `<details class="acc">
      <summary>${esc(label)}</summary>
      <div class="acc-body">${bodyHtml}</div>
    </details>`;
  }

  _barRow(label, value, max, currency) {
    const pct = max > 0 ? Math.round((value / max) * 100) : 0;
    return `<div class="bar-row">
      <div class="bar-label">${esc(label)}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
      <div class="bar-value">${esc(money(value, currency))}</div>
    </div>`;
  }

  _costBreakdown(a, currency) {
    const byCategory = Object.entries(a.cost_by_category || {});
    const byProvider = Object.entries(a.cost_by_provider || {});
    if (byCategory.length === 0 && byProvider.length === 0) return "";

    const maxCat = Math.max(...byCategory.map(([, v]) => v), 0);
    const maxProv = Math.max(...byProvider.map(([, v]) => v), 0);

    const body = `
      ${
        byCategory.length
          ? `<div class="lbl2">By category</div>${byCategory
              .sort((a, b) => b[1] - a[1])
              .map(([name, value]) => this._barRow(name, value, maxCat, currency))
              .join("")}`
          : ""
      }
      ${
        byProvider.length
          ? `<div class="lbl2">By provider</div>${byProvider
              .sort((a, b) => b[1] - a[1])
              .map(([name, value]) => this._barRow(name, value, maxProv, currency))
              .join("")}`
          : ""
      }
      ${
        a.average_annual_cost != null
          ? `<div class="kv"><span>Average per year</span><b>${esc(
              money(a.average_annual_cost, currency)
            )}</b></div>`
          : ""
      }`;
    return this._details("Cost breakdown", body);
  }

  _telemetryDetails(d) {
    const entries = Object.values(d.optional_entities || {});
    if (entries.length === 0) return "";
    const body = entries
      .map((e) => {
        const cls =
          e.status === "Connected" ? "st-ok" : e.status === "Unavailable" ? "st-due" : "st-off";
        return `<div class="kv">
          <span>${esc(e.label)}</span>
          <b class="status-label ${cls}">${esc(e.status)}</b>
        </div>`;
      })
      .join("");
    return this._details("Tesla telemetry entities", body);
  }

  _emptyGood(message) {
    return `<div class="empty empty-good"><span class="check-icon"></span>${esc(message)}</div>`;
  }

  _emptyState(title, subtitle) {
    return `<div class="empty">
      <div class="empty-title">${esc(title)}</div>
      ${subtitle ? `<div class="empty-sub">${esc(subtitle)}</div>` : ""}
    </div>`;
  }

  _stat(label, value, variant) {
    return `<div class="stat ${variant === "primary" ? "stat-primary" : ""}">
      <div class="lbl">${esc(label)}</div>
      <div class="val">${esc(value)}</div>
    </div>`;
  }

  _viewSchedules() {
    const d = this._data;
    const statusById = {};
    (d.statuses || []).forEach((s) => (statusById[s.schedule_id] = s));

    return `
      <div class="rowbtns">
        <button class="btn primary" data-act="new-schedule">+ New schedule</button>
      </div>
      ${
        this._editing && this._editing.kind === "schedule-new"
          ? this._formSchedule(null)
          : ""
      }
      ${
        (d.schedules || []).length === 0
          ? `<div class="empty">No schedules yet.</div>`
          : d.schedules
              .map((sch) => {
                if (
                  this._editing &&
                  this._editing.kind === "schedule" &&
                  this._editing.id === sch.id
                )
                  return this._formSchedule(sch);
                return this._scheduleRow(statusById[sch.id] || {
                  schedule_id: sch.id,
                  item_name: sch.item_name,
                  category: sch.category,
                  source: sch.source,
                  status: sch.enabled ? "OK" : "DISABLED",
                  miles_remaining: null,
                  days_remaining: null,
                  notes: sch.notes,
                });
              })
              .join("")
      }`;
  }

  _scheduleRow(s, compact) {
    const meta = STATUS_META[s.status] || STATUS_META.OK;
    const bits = [];
    if (s.miles_remaining !== null && s.miles_remaining !== undefined)
      bits.push(
        `${s.miles_remaining < 0 ? "overdue by " : ""}${num(
          Math.abs(s.miles_remaining)
        )} ${this._data.distance_unit}`
      );
    if (s.days_remaining !== null && s.days_remaining !== undefined)
      bits.push(
        `${s.days_remaining < 0 ? "overdue by " : ""}${Math.abs(s.days_remaining)} days`
      );

    return `
      <div class="item">
        <div class="item-main">
          <div class="item-title">
            <span class="status-dot ${meta.cls}"></span>${esc(s.item_name)}
          </div>
          <div class="item-sub">
            <span class="status-label ${meta.cls}">${esc(meta.label)}</span>${
              bits.length ? " · " + esc(bits.join(" or ")) : ""
            }
            <span class="tag">${esc(s.category || "")}</span>
            <span class="src">${esc(s.source || "")}</span>
          </div>
          ${s.notes ? `<div class="note">${richText(s.notes)}</div>` : ""}
        </div>
        ${
          compact
            ? `<div class="item-actions"><button class="btn sm ok" data-act="complete" data-id="${s.schedule_id}">Done</button></div>`
            : `<div class="item-actions">
                 <button class="btn sm ok" data-act="complete" data-id="${s.schedule_id}">Done</button>
                 <button class="btn sm ghost" data-act="edit-schedule" data-id="${s.schedule_id}">Edit</button>
                 <button class="btn sm ghost danger" data-act="del-schedule" data-id="${s.schedule_id}">Delete</button>
               </div>`
        }
      </div>`;
  }

  _formSchedule(sch) {
    const isNew = !sch;
    const v = sch || {
      item_name: "",
      category: "Other",
      interval_miles: "",
      interval_days: "",
      notes: "",
      enabled: true,
      source: "User Defined",
    };
    return `
      <div class="form">
        <div class="form-title">${isNew ? "New schedule" : "Edit schedule"}</div>
        ${this._field("sch_name", "Item name", v.item_name)}
        ${this._select("sch_category", "Category", this._categoryNames(), v.category)}
        ${this._field("sch_miles", `Repeat every (${this._data.distance_unit})`, v.interval_miles, "number")}
        ${this._field("sch_days", "Repeat every (days)", v.interval_days, "number")}
        ${this._area("sch_notes", "Notes", v.notes)}
        ${
          isNew
            ? `${this._select("sch_source", "Source", ["User Defined", "Default", "Tesla Recommendation"], v.source)}
               <div class="hint">Only choose "Tesla Recommendation" for intervals you have verified in Tesla's own documentation.</div>`
            : `<label class="check"><input type="checkbox" id="sch_enabled" ${
                v.enabled ? "checked" : ""
              }> Enabled</label>`
        }
        <div class="rowbtns">
          <button class="btn primary" data-act="${isNew ? "save-new-schedule" : "save-schedule"}" data-id="${
            sch ? sch.id : ""
          }">Save</button>
          <button class="btn" data-act="cancel">Cancel</button>
        </div>
      </div>`;
  }

  _viewHistory() {
    const d = this._data;
    const query = this._search.toLowerCase();
    const records = (d.records || []).filter((r) => {
      if (!query) return true;
      const hay = [
        r.title,
        r.notes,
        r.service_provider,
        r.location,
        ...(r.items || []).map((i) => `${i.name} ${i.notes}`),
      ]
        .join(" ")
        .toLowerCase();
      return hay.includes(query);
    });

    return `
      <input id="search" class="search" placeholder="Search history, including notes…" value="${esc(
        this._search
      )}">
      ${
        records.length === 0
          ? `<div class="empty">No matching records.</div>`
          : records
              .map((r) =>
                this._editing &&
                this._editing.kind === "record" &&
                this._editing.id === r.id
                  ? this._formRecord(r)
                  : this._recordRow(r, this._openRecord === r.id)
              )
              .join("")
      }`;
  }

  _recordRow(r, open) {
    const d = this._data;
    const items = (r.items || []).map((i) => i.name).join(", ");
    return `
      <div class="item ${open ? "open" : ""}">
        <div class="item-main" data-act="open-record" data-id="${r.id}">
          <div class="item-title">${esc(r.title || items || "Service")}</div>
          <div class="item-sub">${esc(r.service_date)} · ${num(r.mileage)} ${esc(
            d.distance_unit
          )} · ${esc(money(r.total_cost, d.currency))}${
            r.service_provider ? " · " + esc(r.service_provider) : ""
          }</div>
          ${
            !open && r.notes
              ? `<div class="note">${esc(r.notes.slice(0, 90))}${
                  r.notes.length > 90 ? "…" : ""
                }</div>`
              : ""
          }
        </div>
        <div class="item-actions">
          <button class="btn sm ghost" data-act="edit-record" data-id="${r.id}">Edit</button>
          <button class="btn sm ghost danger" data-act="del-record" data-id="${r.id}">Delete</button>
        </div>
        ${open ? this._recordDetail(r) : ""}
      </div>`;
  }

  _recordDetail(r) {
    const d = this._data;
    return `
      <div class="detail">
        <div class="kv"><span>Date</span><b>${esc(r.service_date)}</b></div>
        <div class="kv"><span>Mileage</span><b>${num(r.mileage)} ${esc(
          d.distance_unit
        )}</b></div>
        <div class="kv"><span>Labor</span><b>${esc(
          money(r.labor_cost, d.currency)
        )}</b></div>
        <div class="kv"><span>Parts</span><b>${esc(
          money(r.parts_cost, d.currency)
        )}</b></div>
        <div class="kv"><span>Total</span><b>${esc(
          money(r.total_cost, d.currency)
        )}</b></div>
        <div class="kv"><span>Provider</span><b>${esc(r.service_provider || "—")}</b></div>
        <div class="kv"><span>Location</span><b>${esc(r.location || "—")}</b></div>

        <div class="sec">Items serviced</div>
        ${
          (r.items || []).length === 0
            ? `<div class="empty sm">No items recorded.</div>`
            : r.items
                .map((i) =>
                  this._editing &&
                  this._editing.kind === "item" &&
                  this._editing.id === i.id
                    ? this._formItem(i)
                    : `<div class="subitem">
                         <div>
                           <b>${esc(i.name)}</b>
                           <span class="tag">${esc(i.category)}</span>
                           ${i.is_custom ? '<span class="tag custom">custom</span>' : ""}
                           ${i.cost ? ` · ${esc(money(i.cost, d.currency))}` : ""}
                           ${i.notes ? `<div class="note">${richText(i.notes)}</div>` : ""}
                         </div>
                         <div class="item-actions">
                           <button class="btn sm ghost" data-act="edit-item" data-id="${i.id}">Edit</button>
                           <button class="btn sm ghost danger" data-act="del-item" data-id="${i.id}">Delete</button>
                         </div>
                       </div>`
                )
                .join("")
        }

        <div class="sec">Notes</div>
        <div class="notes-box">${
          r.notes ? richText(r.notes) : '<span class="muted">No notes recorded.</span>'
        }</div>

        <div class="sec">Attachments</div>
        ${
          (r.attachments || []).length === 0
            ? `<div class="empty sm">None. Use the Add tab to attach a receipt.</div>`
            : r.attachments
                .map(
                  (a) =>
                    `<div class="subitem"><div>📎 ${esc(a.filename)} <span class="muted">${esc(
                      a.mime_type
                    )}</span></div></div>`
                )
                .join("")
        }
        <div class="rowbtns">
          <button class="btn sm" data-act="attach" data-id="${r.id}">+ Attach file</button>
          <button class="btn sm" data-act="add-item-to" data-id="${r.id}">+ Add item</button>
        </div>
      </div>`;
  }

  _formRecord(r) {
    const d = this._data;
    return `
      <div class="form">
        <div class="form-title">Edit service record</div>
        ${this._field("rec_date", "Date", r.service_date, "date")}
        ${this._field("rec_mileage", `Mileage (${d.distance_unit})`, r.mileage, "number")}
        ${this._field("rec_title", "Title", r.title)}
        ${this._field("rec_provider", "Service provider", r.service_provider)}
        ${this._field("rec_location", "Location", r.location)}
        ${this._field("rec_labor", "Labor cost", r.labor_cost, "number")}
        ${this._field("rec_parts", "Parts cost", r.parts_cost, "number")}
        ${this._field("rec_total", "Total cost", r.total_cost, "number")}
        ${this._area("rec_notes", "Notes", r.notes)}
        <div class="rowbtns">
          <button class="btn primary" data-act="save-record" data-id="${r.id}">Save</button>
          <button class="btn" data-act="cancel">Cancel</button>
        </div>
      </div>`;
  }

  _formItem(i) {
    return `
      <div class="form">
        <div class="form-title">Edit item</div>
        ${this._field("it_name", "Name", i.name)}
        ${this._select("it_category", "Category", this._categoryNames(), i.category)}
        ${this._field("it_cost", "Cost", i.cost, "number")}
        ${this._area("it_notes", "Notes", i.notes)}
        <div class="rowbtns">
          <button class="btn primary" data-act="save-item" data-id="${i.id}">Save</button>
          <button class="btn" data-act="cancel">Cancel</button>
        </div>
      </div>`;
  }

  _viewAdd() {
    const d = this._data;
    const defaults = [
      ["Tire Rotation", "Tires"],
      ["Brake Inspection", "Brakes"],
      ["Brake Service", "Brakes"],
      ["Battery Inspection", "Battery"],
      ["Cabin Air Filter", "Filters"],
      ["Wiper Blades", "Exterior"],
      ["Tire Inspection", "Tires"],
      ["Brake Fluid", "Fluids"],
    ];
    return `
      <div class="form">
        <div class="form-title">Add service record</div>
        ${this._field("add_date", "Date", today(), "date")}
        ${this._field(
          "add_mileage",
          `Mileage (${d.distance_unit})`,
          d.current_mileage ? Math.round(d.current_mileage) : "",
          "number"
        )}
        ${this._field("add_title", "Title", "")}
        ${this._field("add_provider", "Service provider", "")}
        ${this._field("add_location", "Location", "")}
        ${this._field("add_labor", "Labor cost", "", "number")}
        ${this._field("add_parts", "Parts cost", "", "number")}
        <div class="lbl2">Items serviced</div>
        <div class="checks">
          ${defaults
            .map(
              ([name, cat]) =>
                `<label class="check"><input type="checkbox" class="def-item" data-name="${esc(
                  name
                )}" data-cat="${esc(cat)}"> ${esc(name)}</label>`
            )
            .join("")}
        </div>
        ${this._area("add_notes", "Notes", "")}
        <div class="rowbtns">
          <button class="btn primary" data-act="save-new-record">SAVE SERVICE RECORD</button>
        </div>
      </div>

      <div class="form">
        <div class="form-title">+ Add custom maintenance</div>
        <div class="hint">Anything you like — frunk struts, ceramic coating, window tint. A new category is created automatically.</div>
        ${this._field("cm_name", "Name", "")}
        ${this._combo("cm_category", "Category", this._categoryNames())}
        ${this._field("cm_date", "Date completed", today(), "date")}
        ${this._field(
          "cm_mileage",
          `Mileage (${d.distance_unit})`,
          d.current_mileage ? Math.round(d.current_mileage) : "",
          "number"
        )}
        ${this._field("cm_cost", "Cost", "", "number")}
        ${this._field("cm_provider", "Service provider", "")}
        ${this._area("cm_notes", "Notes", "")}
        <label class="check"><input type="checkbox" id="cm_recurring"> Make this recurring</label>
        ${this._field("cm_miles", `Repeat every (${d.distance_unit})`, "", "number")}
        ${this._field("cm_days", "Repeat every (days)", "", "number")}
        <div class="rowbtns">
          <button class="btn primary" data-act="save-custom">SAVE MAINTENANCE</button>
        </div>
      </div>

      <div class="form">
        <div class="form-title">Data</div>
        <div class="rowbtns">
          <button class="btn" data-act="export-json">Export JSON</button>
          <button class="btn" data-act="export-csv">Export CSV</button>
          <button class="btn" data-act="backup">Back up database</button>
        </div>
      </div>`;
  }

  _viewTires() {
    const d = this._data;
    return `
      <div class="section-head">Tires</div>
      ${
        (d.tires || []).length === 0
          ? `<div class="empty">No tire records yet.</div>`
          : d.tires
              .map((t) =>
                this._editing &&
                this._editing.kind === "tire" &&
                this._editing.id === t.id
                  ? this._formTire(t)
                  : `<div class="item">
                       <div class="item-main">
                         <div class="item-title">${esc(t.position)} — ${esc(
                           t.brand || "—"
                         )} ${esc(t.model || "")}</div>
                         <div class="item-sub">Tread ${t.current_tread_depth ?? "—"}/${
                           t.original_tread_depth ?? "—"
                         } · ${esc(t.size || "")} · ${esc(
                           money(t.purchase_cost, d.currency)
                         )}</div>
                         ${t.notes ? `<div class="note">${richText(t.notes)}</div>` : ""}
                       </div>
                       <div class="item-actions">
                         <button class="btn sm ghost" data-act="edit-tire" data-id="${t.id}">Edit</button>
                         <button class="btn sm ghost danger" data-act="del-tire" data-id="${t.id}">Delete</button>
                       </div>
                     </div>`
              )
              .join("")
      }
      <div class="form">
        <div class="form-title">Add tire</div>
        ${this._select("nt_position", "Position", TIRE_POSITIONS, "Front Left")}
        ${this._field("nt_brand", "Brand", "")}
        ${this._field("nt_model", "Model", "")}
        ${this._field("nt_size", "Size", "")}
        ${this._field("nt_tread", "Current tread (32nds)", "", "number")}
        ${this._field("nt_orig", "Original tread (32nds)", "", "number")}
        ${this._field("nt_cost", "Purchase cost", "", "number")}
        ${this._area("nt_notes", "Notes", "")}
        <div class="rowbtns"><button class="btn primary" data-act="save-tire">Add tire</button></div>
      </div>

      <div class="section-head">Brakes</div>
      ${
        (d.brakes || []).length === 0
          ? `<div class="empty">No brake inspections yet.</div>`
          : d.brakes
              .map((b) =>
                this._editing &&
                this._editing.kind === "brake" &&
                this._editing.id === b.id
                  ? this._formBrake(b)
                  : `<div class="item">
                       <div class="item-main">
                         <div class="item-title">${esc(b.axle)} — ${esc(b.condition)}</div>
                         <div class="item-sub">Pads ${b.pad_thickness ?? "—"} mm · ${esc(
                           b.rotor_condition || "—"
                         )} · ${esc(b.inspection_date || "—")}</div>
                         ${b.notes ? `<div class="note">${richText(b.notes)}</div>` : ""}
                       </div>
                       <div class="item-actions">
                         <button class="btn sm ghost" data-act="edit-brake" data-id="${b.id}">Edit</button>
                         <button class="btn sm ghost danger" data-act="del-brake" data-id="${b.id}">Delete</button>
                       </div>
                     </div>`
              )
              .join("")
      }
      <div class="form">
        <div class="form-title">Add brake inspection</div>
        ${this._select("nb_axle", "Axle", ["Front", "Rear"], "Front")}
        ${this._select("nb_condition", "Condition", BRAKE_CONDITIONS, "Good")}
        ${this._field("nb_pad", "Pad thickness (mm)", "", "number")}
        ${this._field("nb_rotor", "Rotor condition", "")}
        ${this._area("nb_notes", "Notes", "")}
        <div class="rowbtns"><button class="btn primary" data-act="save-brake">Add inspection</button></div>
      </div>`;
  }

  _formTire(t) {
    return `
      <div class="form">
        <div class="form-title">Edit tire</div>
        ${this._select("et_position", "Position", TIRE_POSITIONS, t.position)}
        ${this._field("et_brand", "Brand", t.brand)}
        ${this._field("et_model", "Model", t.model)}
        ${this._field("et_size", "Size", t.size)}
        ${this._field("et_tread", "Current tread (32nds)", t.current_tread_depth, "number")}
        ${this._field("et_cost", "Purchase cost", t.purchase_cost, "number")}
        ${this._area("et_notes", "Notes", t.notes)}
        <div class="rowbtns">
          <button class="btn primary" data-act="save-tire-edit" data-id="${t.id}">Save</button>
          <button class="btn" data-act="cancel">Cancel</button>
        </div>
      </div>`;
  }

  _formBrake(b) {
    return `
      <div class="form">
        <div class="form-title">Edit brake inspection</div>
        ${this._select("eb_condition", "Condition", BRAKE_CONDITIONS, b.condition)}
        ${this._field("eb_pad", "Pad thickness (mm)", b.pad_thickness, "number")}
        ${this._field("eb_rotor", "Rotor condition", b.rotor_condition)}
        ${this._area("eb_notes", "Notes", b.notes)}
        <div class="rowbtns">
          <button class="btn primary" data-act="save-brake-edit" data-id="${b.id}">Save</button>
          <button class="btn" data-act="cancel">Cancel</button>
        </div>
      </div>`;
  }

  // ----------------------------------------------------------------- inputs
  _categoryNames() {
    return (this._data.categories || []).map((c) => c.name);
  }

  _field(id, label, value, type = "text") {
    return `<label class="f"><span>${esc(label)}</span>
      <input id="${id}" type="${type}" value="${esc(value ?? "")}"></label>`;
  }

  _area(id, label, value) {
    return `<label class="f"><span>${esc(label)}</span>
      <textarea id="${id}" rows="3">${esc(value ?? "")}</textarea>
      <span class="f-hint">**bold** and *italic* are supported</span></label>`;
  }

  _select(id, label, options, selected) {
    return `<label class="f"><span>${esc(label)}</span>
      <select id="${id}">${options
        .map(
          (o) =>
            `<option value="${esc(o)}"${o === selected ? " selected" : ""}>${esc(
              o
            )}</option>`
        )
        .join("")}</select></label>`;
  }

  _combo(id, label, options) {
    return `<label class="f"><span>${esc(label)}</span>
      <input id="${id}" list="${id}_list" placeholder="Existing or brand new">
      <datalist id="${id}_list">${options
        .map((o) => `<option value="${esc(o)}">`)
        .join("")}</datalist></label>`;
  }

  _val(id) {
    const el = this.shadowRoot.getElementById(id);
    return el ? el.value.trim() : "";
  }

  _numVal(id) {
    const raw = this._val(id);
    return raw === "" ? null : Number(raw);
  }

  _checked(id) {
    const el = this.shadowRoot.getElementById(id);
    return el ? el.checked : false;
  }

  // ----------------------------------------------------------------- events
  async _onClick(event) {
    const tabBtn = event.target.closest("[data-tab]");
    if (tabBtn) {
      this._tab = tabBtn.dataset.tab;
      this._editing = null;
      this._paint();
      return;
    }
    const el = event.target.closest("[data-act]");
    if (!el) return;
    const act = el.dataset.act;
    const id = el.dataset.id ? Number(el.dataset.id) : null;

    switch (act) {
      case "reload":
        return this._load();
      case "cancel":
        this._editing = null;
        return this._paint();
      case "open-record":
        this._openRecord = this._openRecord === id ? null : id;
        this._tab = "history";
        return this._paint();

      case "new-schedule":
        this._editing = { kind: "schedule-new" };
        return this._paint();
      case "edit-schedule":
        this._editing = { kind: "schedule", id };
        return this._paint();
      case "save-new-schedule":
        return this._act("add_schedule", {
          name: this._val("sch_name"),
          category: this._val("sch_category"),
          interval_miles: this._numVal("sch_miles"),
          interval_days: this._numVal("sch_days"),
          notes: this._val("sch_notes"),
          source: this._val("sch_source") || "User Defined",
        });
      case "save-schedule":
        return this._act("update_schedule", {
          schedule_id: id,
          name: this._val("sch_name"),
          category: this._val("sch_category"),
          interval_miles: this._numVal("sch_miles"),
          interval_days: this._numVal("sch_days"),
          notes: this._val("sch_notes"),
          enabled: this._checked("sch_enabled"),
        });
      case "del-schedule":
        return this._act(
          "delete_schedule",
          { schedule_id: id },
          "Delete this schedule? Service history is not affected."
        );
      case "complete":
        return this._act("complete_maintenance", {
          schedule_id: id,
          mileage: this._data.current_mileage,
        });

      case "edit-record":
        this._editing = { kind: "record", id };
        this._tab = "history";
        return this._paint();
      case "save-record":
        return this._act("update_service_record", {
          service_record_id: id,
          service_date: this._val("rec_date"),
          mileage: this._numVal("rec_mileage"),
          title: this._val("rec_title"),
          service_provider: this._val("rec_provider"),
          location: this._val("rec_location"),
          labor_cost: this._numVal("rec_labor") ?? 0,
          parts_cost: this._numVal("rec_parts") ?? 0,
          total_cost: this._numVal("rec_total") ?? 0,
          notes: this._val("rec_notes"),
        });
      case "del-record":
        return this._act(
          "delete_service_record",
          { service_record_id: id },
          "Delete this service record and its items? This cannot be undone."
        );

      case "edit-item":
        this._editing = { kind: "item", id };
        return this._paint();
      case "save-item":
        return this._act("update_maintenance_item", {
          item_id: id,
          name: this._val("it_name"),
          category: this._val("it_category"),
          cost: this._numVal("it_cost") ?? 0,
          notes: this._val("it_notes"),
        });
      case "del-item":
        return this._act(
          "delete_maintenance_item",
          { item_id: id },
          "Delete this maintenance item?"
        );
      case "add-item-to": {
        const name = window.prompt("Item name");
        if (!name) return;
        const category = window.prompt("Category", "Other") || "Other";
        return this._act("add_maintenance_item", {
          service_record_id: id,
          name,
          category,
          is_custom: true,
        });
      }
      case "attach": {
        const path = window.prompt(
          "Full path to a JPG, PNG, WEBP or PDF that Home Assistant can read\n(e.g. /media/receipts/invoice.pdf)"
        );
        if (!path) return;
        return this._act("add_attachment", {
          service_record_id: id,
          file_path: path,
        });
      }

      case "save-new-record": {
        const items = [...this.shadowRoot.querySelectorAll(".def-item")]
          .filter((box) => box.checked)
          .map((box) => ({
            name: box.dataset.name,
            category: box.dataset.cat,
            is_custom: false,
          }));
        return this._act("add_service_record", {
          service_date: this._val("add_date"),
          mileage: this._numVal("add_mileage"),
          title: this._val("add_title"),
          service_provider: this._val("add_provider"),
          location: this._val("add_location"),
          labor_cost: this._numVal("add_labor") ?? 0,
          parts_cost: this._numVal("add_parts") ?? 0,
          notes: this._val("add_notes"),
          items,
        });
      }
      case "save-custom": {
        if (!this._val("cm_name")) return this._toast("Name is required", true);
        const recurring = this._checked("cm_recurring");
        const payload = {
          name: this._val("cm_name"),
          category: this._val("cm_category") || "Other",
          date_completed: this._val("cm_date"),
          mileage: this._numVal("cm_mileage"),
          cost: this._numVal("cm_cost") ?? 0,
          service_provider: this._val("cm_provider"),
          notes: this._val("cm_notes"),
          is_custom: true,
          create_schedule: recurring,
        };
        if (recurring) {
          payload.interval_miles = this._numVal("cm_miles");
          payload.interval_days = this._numVal("cm_days");
          if (!payload.interval_miles && !payload.interval_days)
            return this._toast(
              "Recurring maintenance needs a mileage or day interval",
              true
            );
        }
        return this._act("add_maintenance_item", payload);
      }

      case "save-tire":
        if (!this._val("nt_position")) return;
        return this._act("add_tire_record", {
          position: this._val("nt_position"),
          brand: this._val("nt_brand"),
          model: this._val("nt_model"),
          size: this._val("nt_size"),
          current_tread_depth: this._numVal("nt_tread"),
          original_tread_depth: this._numVal("nt_orig"),
          purchase_cost: this._numVal("nt_cost") ?? 0,
          notes: this._val("nt_notes"),
        });
      case "edit-tire":
        this._editing = { kind: "tire", id };
        return this._paint();
      case "save-tire-edit":
        return this._act("update_tire_record", {
          tire_id: id,
          position: this._val("et_position"),
          brand: this._val("et_brand"),
          model: this._val("et_model"),
          size: this._val("et_size"),
          current_tread_depth: this._numVal("et_tread"),
          purchase_cost: this._numVal("et_cost") ?? 0,
          notes: this._val("et_notes"),
        });
      case "del-tire":
        return this._act("delete_tire_record", { tire_id: id }, "Delete this tire record?");

      case "save-brake":
        return this._act("add_brake_record", {
          axle: this._val("nb_axle"),
          condition: this._val("nb_condition"),
          pad_thickness: this._numVal("nb_pad"),
          rotor_condition: this._val("nb_rotor"),
          notes: this._val("nb_notes"),
        });
      case "edit-brake":
        this._editing = { kind: "brake", id };
        return this._paint();
      case "save-brake-edit":
        return this._act("update_brake_record", {
          brake_id: id,
          condition: this._val("eb_condition"),
          pad_thickness: this._numVal("eb_pad"),
          rotor_condition: this._val("eb_rotor"),
          notes: this._val("eb_notes"),
        });
      case "del-brake":
        return this._act(
          "delete_brake_record",
          { brake_id: id },
          "Delete this brake inspection?"
        );

      case "export-json":
      case "export-csv":
        try {
          const res = await this._call(
            "export_data",
            { format: act === "export-csv" ? "csv" : "json" },
            true
          );
          this._toast(`Written to ${res.path}`);
        } catch (err) {
          this._toast("Export failed", true);
        }
        return;
      case "backup":
        try {
          const res = await this._call("backup_database", {}, true);
          this._toast(`Backed up to ${res.path}`);
        } catch (err) {
          this._toast("Backup failed", true);
        }
        return;
    }
  }

  // ----------------------------------------------------------------- styles
  _css() {
    return `
      :host {
        --tm-radius: 14px;
        --tm-radius-sm: 10px;
        --tm-gap: 10px;
        --tm-good: #22c55e;
        --tm-warn: #f59e0b;
        --tm-bad: #ef4444;
        --tm-muted: #8a8f98;
      }
      * { box-sizing: border-box; }
      ha-card { padding: 0; overflow: hidden; }
      .pad { padding: 20px; }
      .muted { color: var(--secondary-text-color); }

      /* ---------- header ---------- */
      .head {
        padding: 20px 20px 14px;
        border-bottom: 1px solid var(--divider-color);
      }
      .head-main { display: flex; flex-direction: column; gap: 6px; }
      .title-row {
        display: flex; align-items: center; justify-content: space-between;
        gap: 12px; flex-wrap: wrap;
      }
      .title {
        font-size: 1.5rem; font-weight: 700; line-height: 1.2;
        letter-spacing: -0.01em;
      }
      .sub {
        display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
        font-size: .92rem; color: var(--secondary-text-color);
      }
      .sub-mileage { font-weight: 600; color: var(--primary-text-color); }

      .health {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 5px 12px 5px 10px; border-radius: 999px;
        font-size: .72rem; font-weight: 700; letter-spacing: .04em;
        white-space: nowrap; text-transform: uppercase;
      }
      .health-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
      .st-ok { background: color-mix(in srgb, var(--tm-good) 15%, transparent); color: var(--tm-good); }
      .st-due, .st-soon { background: color-mix(in srgb, var(--tm-warn) 16%, transparent); color: var(--tm-warn); }
      .st-overdue { background: color-mix(in srgb, var(--tm-bad) 15%, transparent); color: var(--tm-bad); }
      .st-off { background: color-mix(in srgb, var(--tm-muted) 18%, transparent); color: var(--tm-muted); }

      .pill {
        display: inline-flex; align-items: center; padding: 3px 10px;
        border-radius: 999px; font-size: .72rem; font-weight: 600;
      }
      .pill-warn { background: color-mix(in srgb, var(--tm-warn) 16%, transparent); color: var(--tm-warn); }
      .pill-muted { background: color-mix(in srgb, var(--tm-muted) 16%, transparent); color: var(--tm-muted); }

      /* ---------- tabs ---------- */
      .tabs {
        display: flex; flex-wrap: wrap; gap: 2px; padding: 6px 12px 0;
        border-bottom: 1px solid var(--divider-color);
      }
      .tab {
        flex: 0 0 auto; background: none; border: none; cursor: pointer;
        padding: 10px 14px; font-size: .88rem; font-weight: 500;
        color: var(--secondary-text-color); border-bottom: 2px solid transparent;
        font-family: inherit; border-radius: 8px 8px 0 0; transition: color .15s;
      }
      .tab:hover { color: var(--primary-text-color); }
      .tab.on {
        color: var(--primary-color); border-bottom-color: var(--primary-color);
        font-weight: 700;
      }

      .body { padding: 18px 20px 24px; }
      .section-head {
        font-size: .72rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: .07em; color: var(--secondary-text-color);
        margin: 22px 0 10px;
      }
      .section-head:first-child { margin-top: 0; }

      /* ---------- stat grid ---------- */
      .stats { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
      .stat {
        background: var(--secondary-background-color); border-radius: var(--tm-radius-sm);
        padding: 14px; border: 1px solid transparent;
      }
      .stat-primary {
        background: color-mix(in srgb, var(--primary-color) 10%, var(--secondary-background-color));
        border-color: color-mix(in srgb, var(--primary-color) 25%, transparent);
      }
      .stat .lbl {
        font-size: .68rem; font-weight: 600; color: var(--secondary-text-color);
        text-transform: uppercase; letter-spacing: .05em;
      }
      .stat .val { font-size: 1.3rem; font-weight: 700; margin-top: 5px; letter-spacing: -0.01em; }

      /* ---------- rows / cards ---------- */
      .item {
        display: flex; flex-wrap: wrap; align-items: flex-start; gap: 10px;
        padding: 14px; border-radius: var(--tm-radius-sm); margin-bottom: 8px;
        background: var(--secondary-background-color);
        border: 1px solid transparent; transition: border-color .15s;
      }
      .item.open { border-color: var(--primary-color); }
      .item-main { flex: 1 1 200px; min-width: 0; cursor: pointer; }
      .item-title {
        display: flex; align-items: center; gap: 8px;
        font-weight: 600; font-size: .96rem;
      }
      .item-sub {
        display: flex; align-items: center; flex-wrap: wrap; gap: 6px;
        font-size: .82rem; color: var(--secondary-text-color); margin-top: 4px;
      }
      .item-actions { display: flex; gap: 6px; flex-wrap: wrap; align-self: center; }

      .status-dot {
        width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto;
        background: currentColor;
      }
      .status-dot.st-ok { color: var(--tm-good); }
      .status-dot.st-due, .status-dot.st-soon { color: var(--tm-warn); }
      .status-dot.st-overdue { color: var(--tm-bad); }
      .status-dot.st-off { color: var(--tm-muted); }

      .status-label { font-weight: 600; }
      .status-label.st-ok { color: var(--tm-good); }
      .status-label.st-due, .status-label.st-soon { color: var(--tm-warn); }
      .status-label.st-overdue { color: var(--tm-bad); }
      .status-label.st-off { color: var(--tm-muted); }

      .tag {
        display: inline-flex; align-items: center; font-size: .68rem;
        font-weight: 600; padding: 2px 8px; border-radius: 999px;
        background: color-mix(in srgb, var(--tm-muted) 16%, transparent);
        color: var(--secondary-text-color);
      }
      .tag.custom {
        background: color-mix(in srgb, var(--primary-color) 16%, transparent);
        color: var(--primary-color);
      }
      .src { font-size: .72rem; opacity: .7; font-style: italic; }
      .note {
        font-size: .85rem; margin-top: 8px; padding: 8px 10px;
        border-radius: 8px; background: var(--card-background-color);
        color: var(--primary-text-color); line-height: 1.4;
        white-space: pre-wrap;
      }

      /* ---------- empty states ---------- */
      .empty {
        padding: 18px; text-align: center; border-radius: var(--tm-radius-sm);
        background: var(--secondary-background-color);
      }
      .empty-good {
        display: flex; align-items: center; justify-content: center; gap: 8px;
        color: var(--tm-good); font-weight: 600; font-size: .9rem;
      }
      .check-icon {
        width: 18px; height: 18px; border-radius: 50%; flex: 0 0 auto;
        background: var(--tm-good); position: relative;
      }
      .check-icon::after {
        content: ""; position: absolute; left: 5px; top: 3px;
        width: 5px; height: 9px; border: solid white;
        border-width: 0 2px 2px 0; transform: rotate(45deg);
      }
      .empty-title { font-weight: 600; font-size: .92rem; }
      .empty-sub { font-size: .82rem; color: var(--secondary-text-color); margin-top: 4px; }
      .empty.sm { padding: 10px; font-size: .85rem; }

      /* ---------- collapsible sections ---------- */
      .acc {
        margin-top: 10px; border-radius: var(--tm-radius-sm);
        background: var(--secondary-background-color); overflow: hidden;
      }
      .acc summary {
        list-style: none; cursor: pointer; padding: 13px 14px;
        font-size: .84rem; font-weight: 600; color: var(--primary-text-color);
        display: flex; align-items: center; justify-content: space-between;
        user-select: none;
      }
      .acc summary::-webkit-details-marker { display: none; }
      .acc summary::after {
        content: "›"; font-size: 1.1rem; color: var(--secondary-text-color);
        transform: rotate(90deg); transition: transform .15s; line-height: 1;
      }
      .acc[open] summary::after { transform: rotate(-90deg); }
      .acc-body { padding: 2px 14px 14px; }
      .bar-row {
        display: grid; grid-template-columns: 90px 1fr 64px; align-items: center;
        gap: 10px; padding: 5px 0; font-size: .82rem;
      }
      .bar-label { color: var(--secondary-text-color); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .bar-track {
        height: 6px; border-radius: 999px; background: var(--card-background-color);
        overflow: hidden;
      }
      .bar-fill { height: 100%; border-radius: 999px; background: var(--primary-color); }
      .bar-value { text-align: right; font-weight: 600; }

      /* ---------- detail panel ---------- */
      .detail {
        flex: 1 1 100%; margin-top: 12px; padding-top: 14px;
        border-top: 1px solid var(--divider-color);
      }
      .kv { display: flex; justify-content: space-between; padding: 5px 0; font-size: .88rem; }
      .kv span { color: var(--secondary-text-color); }
      .sec {
        font-size: .68rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: .06em; color: var(--secondary-text-color);
        margin: 16px 0 8px;
      }
      .subitem {
        display: flex; justify-content: space-between; align-items: flex-start;
        gap: 8px; padding: 10px 0; border-bottom: 1px solid var(--divider-color);
      }
      .subitem:last-child { border-bottom: none; }
      .notes-box {
        background: var(--card-background-color); border-radius: 10px;
        padding: 12px; font-size: .88rem; white-space: pre-wrap; line-height: 1.5;
      }

      /* ---------- forms ---------- */
      .form {
        background: var(--secondary-background-color); border-radius: var(--tm-radius);
        padding: 16px; margin-bottom: 14px;
      }
      .form-title { font-weight: 700; font-size: 1rem; margin-bottom: 12px; }
      .hint { font-size: .8rem; color: var(--secondary-text-color); margin-bottom: 12px; line-height: 1.4; }
      .f { display: block; margin-bottom: 12px; }
      .f span {
        display: block; font-size: .76rem; font-weight: 600;
        color: var(--secondary-text-color); margin-bottom: 5px;
      }
      .f input, .f select, .f textarea {
        width: 100%; box-sizing: border-box; padding: 10px 12px; border-radius: 9px;
        border: 1px solid var(--divider-color); background: var(--card-background-color);
        color: var(--primary-text-color); font-family: inherit; font-size: .92rem;
        transition: border-color .15s;
      }
      .f input:focus, .f select:focus, .f textarea:focus {
        outline: none; border-color: var(--primary-color);
      }
      .f-hint {
        display: block; font-size: .7rem; color: var(--secondary-text-color);
        margin-top: 4px; opacity: .75;
      }
      .lbl2 {
        font-size: .76rem; font-weight: 600; color: var(--secondary-text-color);
        margin: 14px 0 8px;
      }
      .checks { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 2px; }
      .check {
        display: flex; align-items: center; gap: 9px; padding: 7px 0;
        font-size: .9rem; cursor: pointer;
      }
      .check input { width: 17px; height: 17px; accent-color: var(--primary-color); }

      .search {
        width: 100%; box-sizing: border-box; padding: 11px 16px; margin-bottom: 14px;
        border-radius: 999px; border: 1px solid var(--divider-color);
        background: var(--secondary-background-color); color: var(--primary-text-color);
        font-family: inherit; font-size: .92rem; transition: border-color .15s;
      }
      .search:focus { outline: none; border-color: var(--primary-color); }

      /* ---------- buttons ---------- */
      .rowbtns { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
      .btn {
        padding: 10px 16px; border-radius: 10px; border: 1px solid var(--divider-color);
        background: var(--card-background-color); color: var(--primary-text-color);
        cursor: pointer; font-family: inherit; font-size: .88rem; font-weight: 600;
        transition: background .15s, border-color .15s, color .15s;
      }
      .btn:hover { background: var(--secondary-background-color); }
      .btn.sm { padding: 7px 12px; font-size: .8rem; }
      .btn.primary {
        background: var(--primary-color); color: var(--text-primary-color, #fff);
        border-color: var(--primary-color);
      }
      .btn.primary:hover { filter: brightness(1.08); }
      .btn.ok { border-color: var(--tm-good); color: var(--tm-good); }
      .btn.ok:hover { background: color-mix(in srgb, var(--tm-good) 12%, transparent); }

      /* Ghost buttons stay quiet until hovered - destructive actions don't shout. */
      .btn.ghost {
        background: transparent; border-color: transparent; color: var(--secondary-text-color);
      }
      .btn.ghost:hover { background: var(--card-background-color); color: var(--primary-text-color); }
      .btn.ghost.danger:hover {
        background: color-mix(in srgb, var(--tm-bad) 12%, transparent); color: var(--tm-bad);
      }
      .btn.danger { border-color: color-mix(in srgb, var(--tm-bad) 45%, transparent); color: var(--tm-bad); }
      .btn.danger:hover { background: color-mix(in srgb, var(--tm-bad) 12%, transparent); }

      .err-box {
        background: color-mix(in srgb, var(--tm-bad) 12%, transparent); color: var(--tm-bad);
        padding: 14px; border-radius: 10px; margin-bottom: 12px; font-size: .9rem;
      }

      .toast {
        position: sticky; bottom: 0; opacity: 0; pointer-events: none;
        transition: opacity .2s, transform .2s; transform: translateY(4px);
        background: #2b2f36; color: #fff; padding: 12px 18px; margin: 0 20px 16px;
        border-radius: 10px; font-size: .88rem; font-weight: 500;
        box-shadow: 0 4px 16px rgba(0,0,0,.25);
      }
      .toast.show { opacity: 1; transform: translateY(0); }
      .toast.err { background: var(--tm-bad); }

      @media (min-width: 560px) {
        .stats { grid-template-columns: repeat(4, 1fr); }
      }`;
  }
}

customElements.define("tesla-maintenance-card", TeslaMaintenanceCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "tesla-maintenance-card",
  name: "Tesla Maintenance",
  description:
    "View, add and edit service records, schedules, tires and brakes for the Tesla Maintenance Tracker.",
  preview: false,
});

console.info(`%c TESLA-MAINTENANCE-CARD %c ${VERSION} `,
  "color:#fff;background:#3d5afe;font-weight:700",
  "color:#3d5afe;background:#fff");