// special features for link
// buttons
// autocomplete
// link validation
// custom queries
// add_fetches
import Awesomplete from 'awesomplete';

vmraid.ui.form.recent_link_validations = {};

vmraid.ui.form.ControlLink = class ControlLink extends vmraid.ui.form.ControlData {
	static trigger_change_on_input_event = false
	make_input() {
		var me = this;
		$(`<div class="link-field ui-front" style="position: relative;">
			<input type="text" class="input-with-feedback form-control">
			<span class="link-btn">
				<a class="btn-open no-decoration" title="${__("Open Link")}">
					${vmraid.utils.icon('arrow-right', 'xs')}
				</a>
			</span>
		</div>`).prependTo(this.input_area);
		this.$input_area = $(this.input_area);
		this.$input = this.$input_area.find('input');
		this.$link = this.$input_area.find('.link-btn');
		this.$link_open = this.$link.find('.btn-open');
		this.set_input_attributes();
		this.$input.on("focus", function() {
			setTimeout(function() {
				if(me.$input.val() && me.get_options()) {
					let doctype = me.get_options();
					let name = me.$input.val();
					me.$link.toggle(true);
					me.$link_open.attr('href', vmraid.utils.get_form_link(doctype, name));
				}

				if(!me.$input.val()) {
					me.$input.val("").trigger("input");
				}
			}, 500);
		});
		this.$input.on("blur", function() {
			// if this disappears immediately, the user's click
			// does not register, hence timeout
			setTimeout(function() {
				me.$link.toggle(false);
			}, 500);
		});
		this.$input.attr('data-target', this.df.options);
		this.input = this.$input.get(0);
		this.has_input = true;
		this.translate_values = true;
		this.setup_buttons();
		this.setup_awesomeplete();
		this.bind_change_event();
	}
	get_options() {
		return this.df.options;
	}
	get_reference_doctype() {
		// this is used to get the context in which link field is loaded
		if (this.doctype) return this.doctype;
		else {
			return vmraid.get_route && vmraid.get_route()[0] === 'List' ? vmraid.get_route()[1] : null;
		}
	}
	setup_buttons() {
		if(this.only_input && !this.with_link_btn) {
			this.$input_area.find(".link-btn").remove();
		}
	}
	open_advanced_search() {
		var doctype = this.get_options();
		if(!doctype) return;
		new vmraid.ui.form.LinkSelector({
			doctype: doctype,
			target: this,
			txt: this.get_input_value()
		});
		return false;
	}
	new_doc() {
		var doctype = this.get_options();
		var me = this;

		if (!doctype) return;

		let df = this.df;
		if (this.frm && this.frm.doctype !== this.df.parent) {
			// incase of grid use common df set in grid
			df = this.frm.get_docfield(this.doc.parentfield, this.df.fieldname);
		}
		// set values to fill in the new document
		if (df && df.get_route_options_for_new_doc) {
			vmraid.route_options = df.get_route_options_for_new_doc(this);
		} else {
			vmraid.route_options = {};
		}

		// partially entered name field
		vmraid.route_options.name_field = this.get_value();

		// reference to calling link
		vmraid._from_link = this;
		vmraid._from_link_scrollY = $(document).scrollTop();

		vmraid.ui.form.make_quick_entry(doctype, (doc) => {
			return me.set_value(doc.name);
		});

		return false;
	}
	setup_awesomeplete() {
		var me = this;

		this.$input.cache = {};

		this.awesomplete = new Awesomplete(me.input, {
			minChars: 0,
			maxItems: 99,
			autoFirst: true,
			list: [],
			data: function (item) {
				return {
					label: item.label || item.value,
					value: item.value
				};
			},
			filter: function() {
				return true;
			},
			item: function (item) {
				var d = this.get_item(item.value);
				if(!d.label) {	d.label = d.value; }

				var _label = (me.translate_values) ? __(d.label) : d.label;
				var html = d.html || "<strong>" + _label + "</strong>";
				if(d.description && d.value!==d.description) {
					html += '<br><span class="small">' + __(d.description) + '</span>';
				}
				return $('<li></li>')
					.data('item.autocomplete', d)
					.prop('aria-selected', 'false')
					.html(`<a><p class="ellipsis" title="${_label}">${html}</p></a>`)
					.get(0);
			},
			sort: function() {
				return 0;
			}
		});

		this.custom_awesomplete_filter && this.custom_awesomplete_filter(this.awesomplete);

		this.$input.on("input", vmraid.utils.debounce(function(e) {
			var doctype = me.get_options();
			if(!doctype) return;
			if (!me.$input.cache[doctype]) {
				me.$input.cache[doctype] = {};
			}

			var term = e.target.value;

			if (me.$input.cache[doctype][term]!=null) {
				// immediately show from cache
				me.awesomplete.list = me.$input.cache[doctype][term];
			}
			var args = {
				'txt': term,
				'doctype': doctype,
				'ignore_user_permissions': me.df.ignore_user_permissions,
				'reference_doctype': me.get_reference_doctype() || ""
			};

			me.set_custom_query(args);

			vmraid.call({
				type: "POST",
				method:'vmraid.desk.search.search_link',
				no_spinner: true,
				args: args,
				callback: function(r) {
					if(!me.$input.is(":focus")) {
						return;
					}
					r.results = me.merge_duplicates(r.results);

					// show filter description in awesomplete
					if (args.filters) {
						let filter_string = me.get_filter_description(args.filters);
						if (filter_string) {
							r.results.push({
								html: `<span class="text-muted" style="line-height: 1.5">${filter_string}</span>`,
								value: '',
								action: () => {}
							});
						}
					}

					if(!me.df.only_select) {
						if(vmraid.model.can_create(doctype)) {
							// new item
							r.results.push({
								html: "<span class='text-primary link-option'>"
									+ "<i class='fa fa-plus' style='margin-right: 5px;'></i> "
									+ __("Create a new {0}", [__(me.get_options())])
									+ "</span>",
								label: __("Create a new {0}", [__(me.get_options())]),
								value: "create_new__link_option",
								action: me.new_doc
							});
						}
						// advanced search

						if (locals && locals['DocType']) {
							// not applicable in web forms
							r.results.push({
								html: "<span class='text-primary link-option'>"
									+ "<i class='fa fa-search' style='margin-right: 5px;'></i> "
									+ __("Advanced Search")
									+ "</span>",
								label: __("Advanced Search"),
								value: "advanced_search__link_option",
								action: me.open_advanced_search
							});
						}
					}
					me.$input.cache[doctype][term] = r.results;
					me.awesomplete.list = me.$input.cache[doctype][term];
					me.toggle_href(doctype);
				}
			});
		}, 500));

		this.$input.on("blur", function() {
			if(me.selected) {
				me.selected = false;
				return;
			}
			var value = me.get_input_value();
			if(value!==me.last_value) {
				me.parse_validate_and_set_in_model(value);
			}
		});

		this.$input.on("awesomplete-open", () => {
			this.autocomplete_open = true;
		});

		this.$input.on("awesomplete-close", () => {
			this.autocomplete_open = false;
		});

		this.$input.on("awesomplete-select", function(e) {
			var o = e.originalEvent;
			var item = me.awesomplete.get_item(o.text.value);

			me.autocomplete_open = false;

			// prevent selection on tab
			var TABKEY = 9;
			if(e.keyCode === TABKEY) {
				e.preventDefault();
				me.awesomplete.close();
				return false;
			}

			if(item.action) {
				item.value = "";
				item.action.apply(me);
			}

			// if remember_last_selected is checked in the doctype against the field,
			// then add this value
			// to defaults so you do not need to set it again
			// unless it is changed.
			if(me.df.remember_last_selected_value) {
				vmraid.boot.user.last_selected_values[me.df.options] = item.value;
			}

			me.parse_validate_and_set_in_model(item.value);
		});

		this.$input.on("awesomplete-selectcomplete", function(e) {
			var o = e.originalEvent;
			if(o.text.value.indexOf("__link_option") !== -1) {
				me.$input.val("");
			}
		});
	}

	merge_duplicates(results) {
		// in case of result like this
		// [{value: 'Manufacturer 1', 'description': 'mobile part 1'},
		// 	{value: 'Manufacturer 1', 'description': 'mobile part 2'}]
		// suggestion list has two items with same value (docname) & description
		return results.reduce((newArr, currElem) => {
			if (newArr.length === 0) return [currElem];
			let element_with_same_value = newArr.find(e => e.value === currElem.value);
			if (element_with_same_value) {
				element_with_same_value.description += `, ${currElem.description}`;
				return [...newArr];
			}
			return [...newArr, currElem];
		}, []);
		// returns [{value: 'Manufacturer 1', 'description': 'mobile part 1, mobile part 2'}]
	}

	toggle_href(doctype) {
		if (vmraid.model.can_select(doctype) && !vmraid.model.can_read(doctype)) {
			// remove href from link field as user has only select perm
			this.$input_area.find(".link-btn").addClass('hide');
		} else {
			this.$input_area.find(".link-btn").removeClass('hide');
		}
	}

	get_filter_description(filters) {
		let doctype = this.get_options();
		let filter_array = [];
		let meta = null;

		vmraid.model.with_doctype(doctype, () => {
			meta = vmraid.get_meta(doctype);
		});

		// convert object style to array
		if (!Array.isArray(filters)) {
			for (let fieldname in filters) {
				let value = filters[fieldname];
				if (!Array.isArray(value)) {
					value = ['=', value];
				}
				filter_array.push([fieldname, ...value]); // fieldname, operator, value
			}
		} else {
			filter_array = filters;
		}

		// add doctype if missing
		filter_array = filter_array.map(filter => {
			if (filter.length === 3) {
				return [doctype, ...filter]; // doctype, fieldname, operator, value
			}
			return filter;
		});

		function get_filter_description(filter) {
			let doctype = filter[0];
			let fieldname = filter[1];
			let docfield = vmraid.meta.get_docfield(doctype, fieldname);
			let label = docfield ? docfield.label : vmraid.model.unscrub(fieldname);

			if (docfield && docfield.fieldtype === 'Check') {
				filter[3] = filter[3] ? __('Yes'): __('No');
			}

			if (filter[3] && Array.isArray(filter[3]) && filter[3].length > 5) {
				filter[3] = filter[3].slice(0, 5);
				filter[3].push('...');
			}

			let value = filter[3] == null || filter[3] === ''
				? __('empty')
				: String(filter[3]);

			return [__(label).bold(), filter[2], value.bold()].join(' ');
		}

		let filter_string = filter_array
			.map(get_filter_description)
			.join(', ');

		return __('Filters applied for {0}', [filter_string]);
	}

	set_custom_query(args) {
		var set_nulls = function(obj) {
			$.each(obj, function(key, value) {
				if(value!==undefined) {
					obj[key] = value;
				}
			});
			return obj;
		};
		if(this.get_query || this.df.get_query) {
			var get_query = this.get_query || this.df.get_query;
			if($.isPlainObject(get_query)) {
				var filters = null;
				if(get_query.filters) {
					// passed as {'filters': {'key':'value'}}
					filters = get_query.filters;
				} else if(get_query.query) {

					// passed as {'query': 'path.to.method'}
					args.query = get_query;
				} else {

					// dict is filters
					filters = get_query;
				}

				if (filters) {
					filters = set_nulls(filters);

					// extend args for custom functions
					$.extend(args, filters);

					// add "filters" for standard query (search.py)
					args.filters = filters;
				}
			} else if(typeof(get_query)==="string") {
				args.query = get_query;
			} else {
				// get_query by function
				var q = (get_query)(this.frm && this.frm.doc || this.doc, this.doctype, this.docname);

				if (typeof(q)==="string") {
					// returns a string
					args.query = q;
				} else if($.isPlainObject(q)) {
					// returns a plain object with filters
					if(q.filters) {
						set_nulls(q.filters);
					}

					// turn off value translation
					if(q.translate_values !== undefined) {
						this.translate_values = q.translate_values;
					}

					// extend args for custom functions
					$.extend(args, q);

					// add "filters" for standard query (search.py)
					args.filters = q.filters;
				}
			}
		}
		if(this.df.filters) {
			set_nulls(this.df.filters);
			if(!args.filters) args.filters = {};
			$.extend(args.filters, this.df.filters);
		}
	}
	validate(value) {
		// validate the value just entered
		if(this.df.options=="[Select]" || this.df.ignore_link_validation) {
			return value;
		}

		return this.validate_link_and_fetch(this.df, this.get_options(),
			this.docname, value);
	}
	validate_link_and_fetch(df, doctype, docname, value) {
		if(value) {
			return new Promise((resolve) => {
				var fetch = '';
				if(this.frm && this.frm.fetch_dict[df.fieldname]) {
					fetch = this.frm.fetch_dict[df.fieldname].columns.join(', ');
				}
				// if default and no fetch, no need to validate
				if (!fetch && df.__default_value && df.__default_value===value) {
					resolve(value);
				}

				this.fetch_and_validate_link(resolve, df, doctype, docname, value, fetch);
			});
		}
	}

	fetch_and_validate_link(resolve, df, doctype, docname, value, fetch) {
		vmraid.call({
			method: 'vmraid.desk.form.utils.validate_link',
			type: "GET",
			args: {
				'value': value,
				'options': doctype,
				'fetch': fetch
			},
			no_spinner: true,
			callback: (r) => {
				if (r.message=='Ok') {
					if (r.fetch_values && docname) {
						this.set_fetch_values(df, docname, r.fetch_values);
					}
					resolve(r.valid_value);
				} else {
					resolve("");
				}
			}
		});
	}

	set_fetch_values(df, docname, fetch_values) {
		var fl = this.frm.fetch_dict[df.fieldname].fields;
		for(var i=0; i < fl.length; i++) {
			vmraid.model.set_value(df.parent, docname, fl[i], fetch_values[i], df.fieldtype);
		}
	}
};

if (Awesomplete) {
	Awesomplete.prototype.get_item = function(value) {
		return this._list.find(function(item) {
			return item.value === value;
		});
	};
}

