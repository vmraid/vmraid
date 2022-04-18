vmraid.provide("vmraid.ui");
vmraid.provide("vmraid.views");
vmraid.provide("vmraid.web_form_list");

export default class WebFormList {
	constructor(opts) {
		Object.assign(this, opts);
		vmraid.web_form_list = this;
		this.wrapper = document.getElementById("list-table");
		this.make_actions();
		this.make_filters();
		$('.link-btn').remove();
	}

	refresh() {
		if (this.table) {
			Array.from(this.table.tBodies).forEach(tbody => tbody.remove());
			let check = document.getElementById('select-all');
			if (check)
				check.checked = false;
		}
		this.rows = [];
		this.page_length = 20;
		this.web_list_start = 0;

		vmraid.run_serially([
			() => this.get_list_view_fields(),
			() => this.get_data(),
			() => this.make_table(),
			() => this.create_more()
		]);
	}

	make_filters() {
		this.filters = {};
		this.filter_input = [];
		const filter_area = document.getElementById('list-filters');

		vmraid.call('vmraid.website.doctype.web_form.web_form.get_web_form_filters', {
			web_form_name: this.web_form_name
		}).then(response => {
			let fields = response.message;
			fields.forEach(field => {
				let col = document.createElement('div.col-sm-4');
				col.classList.add('col', 'col-sm-3');
				filter_area.appendChild(col);
				if (field.default) this.add_filter(field.fieldname, field.default, field.fieldtype);

				let input = vmraid.ui.form.make_control({
					df: {
						fieldtype: field.fieldtype,
						fieldname: field.fieldname,
						options: field.options,
						only_select: true,
						label: __(field.label),
						onchange: (event) => {
							$('#more').remove();
							this.add_filter(field.fieldname, input.value, field.fieldtype);
							this.refresh();
						}
					},
					parent: col,
					value: field.default,
					render_input: 1,
				});
				this.filter_input.push(input);
			});
			this.refresh();
		});
	}

	add_filter(field, value, fieldtype) {
		if (!value) {
			delete this.filters[field];
		} else {
			if (fieldtype === 'Data') value = ['like', value + '%'];
			Object.assign(this.filters, Object.fromEntries([[field, value]]));
		}
	}

	get_list_view_fields() {
		return vmraid
			.call({
				method:
					"vmraid.website.doctype.web_form.web_form.get_in_list_view_fields",
				args: { doctype: this.doctype }
			})
			.then(response => (this.fields_list = response.message));
	}

	fetch_data() {
		return vmraid.call({
			method: "vmraid.www.list.get_list_data",
			args: {
				doctype: this.doctype,
				fields: this.fields_list.map(df => df.fieldname),
				limit_start: this.web_list_start,
				web_form_name: this.web_form_name,
				...this.filters
			}
		});
	}

	async get_data() {
		let response = await this.fetch_data();
		this.data = await response.message;
	}

	more() {
		this.web_list_start += this.page_length;
		this.fetch_data().then((res) => {
			if (res.message.length === 0) {
				vmraid.msgprint(__("No more items to display"));
			}
			this.append_rows(res.message);
		});

	}

	make_table() {
		this.columns = this.fields_list.map(df => {
			return {
				label: df.label,
				fieldname: df.fieldname,
				fieldtype: df.fieldtype
			};
		});

		if (!this.table) {
			this.table = document.createElement("table");
			this.table.classList.add("table");
			this.make_table_head();
		}

		if (this.data.length) {
			this.append_rows(this.data);
			this.wrapper.appendChild(this.table);
		} else {
			let new_button = "";
			let empty_state = document.createElement("div");
			empty_state.classList.add("no-result", "text-muted", "flex", "justify-center", "align-center");

			vmraid.has_permission(this.doctype, "", "create", () => {
				new_button = `
					<a
						class="btn btn-primary btn-sm btn-new-doc hidden-xs"
						href="${window.location.pathname}?new=1">
						${__("Create a new {0}", [__(this.doctype)])}
					</a>
				`;

				empty_state.innerHTML = `
					<div class="text-center">
						<div>
							<img
								src="/assets/vmraid/images/ui-states/list-empty-state.svg"
								alt="Generic Empty State"
								class="null-state">
						</div>
						<p class="small mb-2">${__("No {0} found", [__(this.doctype)])}</p>
						${new_button}
					</div>
				`;

				this.wrapper.appendChild(empty_state);
			});
		}
	}

	make_table_head() {
		// Create Heading
		let thead = this.table.createTHead();
		let row = thead.insertRow();

		let th = document.createElement("th");

		let checkbox = document.createElement("input");
		checkbox.type = "checkbox";
		checkbox.id = "select-all";
		checkbox.onclick = event =>
			this.toggle_select_all(event.target.checked);

		th.appendChild(checkbox);
		row.appendChild(th);

		add_heading(row, __("Sr"));
		this.columns.forEach(col => {
			add_heading(row, __(col.label));
		});

		function add_heading(row, label) {
			let th = document.createElement("th");
			th.innerText = label;
			row.appendChild(th);
		}
	}

	append_rows(row_data) {
		const tbody = this.table.childNodes[1] || this.table.createTBody();
		row_data.forEach((data_item) => {
			let row_element = tbody.insertRow();
			row_element.setAttribute("id", data_item.name);

			let row = new vmraid.ui.WebFormListRow({
				row: row_element,
				doc: data_item,
				columns: this.columns,
				serial_number: this.rows.length + 1,
				events: {
					onEdit: () => this.open_form(data_item.name),
					onSelect: () => this.toggle_delete()
				}
			});

			this.rows.push(row);
		});
	}

	make_actions() {
		const actions = document.querySelector(".list-view-actions");

		vmraid.has_permission(this.doctype, "", "delete", () => {
			this.addButton(actions, "delete-rows", "danger", true, "Delete", () =>
				this.delete_rows()
			);
		});

		this.addButton(
			actions,
			"new",
			"primary",
			false,
			"New",
			() => (window.location.href = window.location.pathname + "?new=1")
		);
	}

	addButton(wrapper, id, type, hidden, name, action) {
		if (document.getElementById(id)) return;
		const button = document.createElement("button");
		if (type == "secondary") {
			button.classList.add(
				"btn",
				"btn-secondary",
				"btn-sm",
				"ml-2"
			);
		}
		else if (type == "danger") {
			button.classList.add(
				"btn",
				"btn-danger",
				"button-delete",
				"btn-sm",
				"ml-2"
			);
		}
		else {
			button.classList.add("btn", "btn-primary", "btn-sm", "ml-2");
		}

		button.id = id;
		button.innerText = name;
		button.hidden = hidden;

		button.onclick = action;
		wrapper.appendChild(button);
	}

	create_more() {
		if (this.rows.length >= this.page_length) {
			const footer = document.querySelector(".list-view-footer");
			this.addButton(footer, "more", "secondary", false, "More", () =>  this.more());
		}
	}

	toggle_select_all(checked) {
		this.rows.forEach(row => row.toggle_select(checked));
	}

	open_form(name) {
		window.location.href = window.location.pathname + "?name=" + name;
	}

	get_selected() {
		return this.rows.filter(row => row.is_selected());
	}

	toggle_delete() {
		if (!this.settings.allow_delete) return
		let btn = document.getElementById("delete-rows");
		btn.hidden = !this.get_selected().length;
	}

	delete_rows() {
		if (!this.settings.allow_delete) return
		vmraid
			.call({
				type: "POST",
				method:
					"vmraid.website.doctype.web_form.web_form.delete_multiple",
				args: {
					web_form_name: this.web_form_name,
					docnames: this.get_selected().map(row => row.doc.name)
				}
			})
			.then(() => {
				this.refresh()
				this.toggle_delete()
			});
	}
};

vmraid.ui.WebFormListRow = class WebFormListRow {
	constructor({ row, doc, columns, serial_number, events, options }) {
		Object.assign(this, { row, doc, columns, serial_number, events });
		this.make_row();
	}

	make_row() {
		// Add Checkboxes
		let cell = this.row.insertCell();
		cell.classList.add('list-col-checkbox');

		this.checkbox = document.createElement("input");
		this.checkbox.type = "checkbox";
		this.checkbox.onclick = event => {
			this.toggle_select(event.target.checked);
			event.stopImmediatePropagation();
		}

		cell.appendChild(this.checkbox);

		// Add Serial Number
		let serialNo = this.row.insertCell();
		serialNo.classList.add('list-col-serial');
		serialNo.innerText = this.serial_number;

		this.columns.forEach(field => {
			let cell = this.row.insertCell();
			let formatter = vmraid.form.get_formatter(field.fieldtype);
			cell.innerHTML = this.doc[field.fieldname] &&
				__(formatter(this.doc[field.fieldname], field, {only_value: 1}, this.doc)) || "";
		});

		this.row.onclick = () => this.events.onEdit();
		this.row.style.cursor = "pointer";
	}

	toggle_select(checked) {
		this.checkbox.checked = checked;
		this.events.onSelect(checked);
	}

	is_selected() {
		return this.checkbox.checked;
	}
};
