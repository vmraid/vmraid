// Copyright (c) 2018, VMRaid Technologies Pvt. Ltd. and Contributors
// MIT License. See license.txt

vmraid.ui.form.LinkSelector = class LinkSelector {
	constructor (opts) {
		/* help: Options: doctype, get_query, target */
		$.extend(this, opts);

		var me = this;
		if (this.doctype != "[Select]") {
			vmraid.model.with_doctype(this.doctype, function (r) {
				me.make();
			});
		} else {
			this.make();
		}
	}
	make () {
		var me = this;

		this.start = 0;
		this.dialog = new vmraid.ui.Dialog({
			title: __("Select {0}", [(this.doctype == '[Select]') ? __("value") : __(this.doctype)]),
			fields: [
				{
					fieldtype: "Data", fieldname: "txt", label: __("Beginning with"),
					description: __("You can use wildcard %"),
				},
				{
					fieldtype: "HTML", fieldname: "results"
				},
				{
					fieldtype: "Button", fieldname: "more", label: __("More"), click: () => {
						me.start += 20;
						me.search();
					}
				}
			],
			primary_action_label: __("Search"),
			primary_action: function () {
				me.start = 0;
				me.search();
			}
		});

		if (this.txt)
			this.dialog.fields_dict.txt.set_input(this.txt);

		this.dialog.get_input("txt").on("keypress", function (e) {
			if (e.which === 13) {
				me.start = 0;
				me.search();
			}
		});
		this.dialog.show();
		this.search();
	}
	search () {
		var args = {
			txt: this.dialog.fields_dict.txt.get_value(),
			searchfield: "name",
			start: this.start
		};
		var me = this;

		if (this.target.set_custom_query) {
			this.target.set_custom_query(args);
		}

		// load custom query from grid
		if (this.target.is_grid && this.target.fieldinfo[this.fieldname]
			&& this.target.fieldinfo[this.fieldname].get_query) {
			$.extend(args,
				this.target.fieldinfo[this.fieldname].get_query(cur_frm.doc));
		}

		vmraid.link_search(this.doctype, args, function (r) {
			var parent = me.dialog.fields_dict.results.$wrapper;
			if (args.start === 0) {
				parent.empty();
			}

			if (r.values.length) {
				$.each(r.values, function (i, v) {
					var row = $(repl('<div class="row link-select-row">\
						<div class="col-xs-4">\
							<b><a href="#">%(name)s</a></b></div>\
						<div class="col-xs-8">\
							<span class="text-muted">%(values)s</span></div>\
						</div>', {
							name: v[0],
							values: v.splice(1).join(", ")
						})).appendTo(parent);

					row.find("a")
						.attr('data-value', v[0])
						.click(function () {
							var value = $(this).attr("data-value");
							var $link = this;
							if (me.target.is_grid) {
								// set in grid
								me.set_in_grid(value);
							} else {
								if (me.target.doctype)
									me.target.parse_validate_and_set_in_model(value);
								else {
									me.target.set_input(value);
									me.target.$input.trigger("change");
								}
								me.dialog.hide();
							}
							return false;
						})
				})
			} else {
				$('<p><br><span class="text-muted">' + __("No Results") + '</span>'
					+ (vmraid.model.can_create(me.doctype) ?
						('<br><br><a class="new-doc btn btn-default btn-sm">'
							+ __('Create a new {0}', [__(me.doctype)]) + "</a>") : '')
					+ '</p>').appendTo(parent).find(".new-doc").click(function () {
						vmraid.new_doc(me.doctype);
					});
			}

			if (r.values.length < 20) {
				var more_btn = me.dialog.fields_dict.more.$wrapper;
				more_btn.hide();
			}

		}, this.dialog.get_primary_btn());

	}
	set_in_grid (value) {
		var me = this, updated = false;
		var d = null;
		if (this.qty_fieldname) {
			vmraid.prompt({
				fieldname: "qty", fieldtype: "Float", label: "Qty",
				"default": 1, reqd: 1
			}, function (data) {
				$.each(me.target.frm.doc[me.target.df.fieldname] || [], function (i, d) {
					if (d[me.fieldname] === value) {
						vmraid.model.set_value(d.doctype, d.name, me.qty_fieldname, data.qty);
						vmraid.show_alert(__("Added {0} ({1})", [value, d[me.qty_fieldname]]));
						updated = true;
						return false;
					}
				});
				if (!updated) {
					vmraid.run_serially([
						() => {
							d = me.target.add_new_row();
						},
						() => vmraid.timeout(0.1),
						() => {
							let args = {};
							args[me.fieldname] = value;
							args[me.qty_fieldname] = data.qty;

							return vmraid.model.set_value(d.doctype, d.name, args);
						},
						() => vmraid.show_alert(__("Added {0} ({1})", [value, data.qty]))
					]);
				}
			}, __("Set Quantity"), __("Set"));
		} else if (me.dynamic_link_field) {
			var d = me.target.add_new_row();
			vmraid.model.set_value(d.doctype, d.name, me.dynamic_link_field, me.dynamic_link_reference);
			vmraid.model.set_value(d.doctype, d.name, me.fieldname, value);
			vmraid.show_alert(__("{0} {1} added", [me.dynamic_link_reference, value]));
		} else {
			var d = me.target.add_new_row();
			vmraid.model.set_value(d.doctype, d.name, me.fieldname, value);
			vmraid.show_alert(__("{0} added", [value]));
		}
	}
};

vmraid.link_search = function (doctype, args, callback, btn) {
	if (!args) {
		args = {
			txt: ''
		}
	}
	args.doctype = doctype;
	if (!args.searchfield) {
		args.searchfield = 'name';
	}

	vmraid.call({
		method: "vmraid.desk.search.search_widget",
		type: "GET",
		args: args,
		callback: function (r) {
			callback && callback(r);
		},
		btn: btn
	});
}

