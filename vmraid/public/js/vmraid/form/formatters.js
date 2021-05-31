// Copyright (c) 2015, VMRaid Technologies Pvt. Ltd. and Contributors
// MIT License. See license.txt

// for license information please see license.txt

vmraid.provide("vmraid.form.formatters");

vmraid.form.link_formatters = {};

vmraid.form.formatters = {
	_right: function(value, options) {
		if(options && (options.inline || options.only_value)) {
			return value;
		} else {
			return "<div style='text-align: right'>" + value + "</div>";
		}
	},
	Data: function(value, df) {
		if (df && df.options == "URL") {
			return `<a href="${value}" title="Open Link" target="_blank">${value}</a>`;
		}
		return value==null ? "" : value;
	},
	Select: function(value) {
		return __(vmraid.form.formatters["Data"](value));
	},
	Float: function(value, docfield, options, doc) {
		// don't allow 0 precision for Floats, hence or'ing with null
		var precision = docfield.precision
			|| cint(vmraid.boot.sysdefaults && vmraid.boot.sysdefaults.float_precision)
			|| null;
		if (docfield.options && docfield.options.trim()) {
			// options points to a currency field, but expects precision of float!
			docfield.precision = precision;
			return vmraid.form.formatters.Currency(value, docfield, options, doc);

		} else {
			// show 1.000000 as 1
			if (!(options || {}).always_show_decimals && !is_null(value)) {
				var temp = cstr(value).split(".");
				if (temp[1]==undefined || cint(temp[1])===0) {
					precision = 0;
				}
			}

			return vmraid.form.formatters._right(
				((value==null || value==="")
					? ""
					: format_number(value, null, precision)), options);
		}
	},
	Int: function(value, docfield, options) {
		return vmraid.form.formatters._right(value==null ? "" : cint(value), options)
	},
	Percent: function(value, docfield, options) {
		const precision = (
			docfield.precision
			|| cint(
				vmraid.boot.sysdefaults
				&& vmraid.boot.sysdefaults.float_precision
			)
			|| 2
		);
		return vmraid.form.formatters._right(flt(value, precision) + "%", options);
	},
	Rating: function(value) {
		const rating_html =	`${[1, 2, 3, 4, 5].map(i =>
			`<svg class="icon icon-md ${i <= (value || 0) ? "star-click": "" }" data-idx="${i}">
				<use href="#icon-star"></use>
			</svg>`
		).join('')}`;
		return `<div class="rating">
			${rating_html}
		</div>`;
	},
	Currency: function (value, docfield, options, doc) {
		var currency  = vmraid.meta.get_field_currency(docfield, doc);
		var precision = docfield.precision || cint(vmraid.boot.sysdefaults.currency_precision) || 2;

		// If you change anything below, it's going to hurt a company in UAE, a bit.
		if (precision > 2) {
			var parts	 = cstr(value).split("."); // should be minimum 2, comes from the DB
			var decimals = parts.length > 1 ? parts[1] : ""; // parts.length == 2 ???

			if ( decimals.length < 3 || decimals.length < precision ) {
				const fraction = vmraid.model.get_value(":Currency", currency, "fraction_units") || 100; // if not set, minimum 2.

				if (decimals.length < cstr(fraction).length) {
					precision = cstr(fraction).length - 1;
				}
			}
		}

		value = (value == null || value === "") ? "" : format_currency(value, currency, precision);

		if ( options && options.only_value ) {
			return value;
		} else {
			return vmraid.form.formatters._right(value, options);
		}
	},
	Check: function(value) {
		return `<input type="checkbox" disabled
			class="disabled-${value ? "selected" : "deselected"}">`;
	},
	Link: function(value, docfield, options, doc) {
		var doctype = docfield._options || docfield.options;
		var original_value = value;
		if(value && value.match && value.match(/^['"].*['"]$/)) {
			value.replace(/^.(.*).$/, "$1");
		}

		if(options && (options.for_print || options.only_value)) {
			return value;
		}

		if(vmraid.form.link_formatters[doctype]) {
			// don't apply formatters in case of composite (parent field of same type)
			if (doc && doctype !== doc.doctype) {
				value = vmraid.form.link_formatters[doctype](value, doc, docfield);
			}
		}

		if(!value) {
			return "";
		}
		if(value[0] == "'" && value[value.length -1] == "'") {
			return value.substring(1, value.length - 1);
		}
		if(docfield && docfield.link_onclick) {
			return repl('<a onclick="%(onclick)s">%(value)s</a>',
				{onclick: docfield.link_onclick.replace(/"/g, '&quot;'), value:value});
		} else if(docfield && doctype) {
			if (vmraid.model.can_read(doctype)) {
				return `<a
					href="/app/${encodeURIComponent(vmraid.router.slug(doctype))}/${encodeURIComponent(original_value)}"
					data-doctype="${doctype}"
					data-name="${original_value}">
					${__(options && options.label || value)}</a>`;
			} else {
				return value;
			}
		} else {
			return value;
		}
	},
	Date: function(value) {
		if (!vmraid.datetime.str_to_user) {
			return value;
		}
		if (value) {
			value = vmraid.datetime.str_to_user(value);
			// handle invalid date
			if (value==="Invalid date") {
				value = null;
			}
		}

		return value || "";
	},
	DateRange: function(value) {
		if (Array.isArray(value)) {
			return __("{0} to {1}", [vmraid.datetime.str_to_user(value[0]), vmraid.datetime.str_to_user(value[1])]);
		} else {
			return value || "";
		}
	},
	Datetime: function(value) {
		if(value) {
			var m = moment(vmraid.datetime.convert_to_user_tz(value));
			if(vmraid.boot.sysdefaults.time_zone) {
				m = m.tz(vmraid.boot.sysdefaults.time_zone);
			}
			return m.format(vmraid.boot.sysdefaults.date_format.toUpperCase()
				+  ' ' + vmraid.boot.sysdefaults.time_format);
		} else {
			return "";
		}
	},
	Text: function(value) {
		if(value) {
			var tags = ["<p", "<div", "<br", "<table"];
			var match = false;

			for(var i=0; i<tags.length; i++) {
				if(value.match(tags[i])) {
					match = true;
					break;
				}
			}

			if(!match) {
				value = vmraid.utils.replace_newlines(value);
			}
		}

		return vmraid.form.formatters.Data(value);
	},
	Time: function(value) {
		if (value) {
			value = vmraid.datetime.str_to_user(value, true);
		}

		return value || "";
	},
	Duration: function(value, docfield) {
		if (value) {
			let duration_options = vmraid.utils.get_duration_options(docfield);
			value = vmraid.utils.get_formatted_duration(value, duration_options);
		}

		return value || "";
	},
	LikedBy: function(value) {
		var html = "";
		$.each(JSON.parse(value || "[]"), function(i, v) {
			if(v) html+= vmraid.avatar(v);
		});
		return html;
	},
	Tag: function(value) {
		var html = "";
		$.each((value || "").split(","), function(i, v) {
			if(v) html+= '<span class="label label-info" \
				style="margin-right: 7px; cursor: pointer;"\
				data-field="_user_tags" data-label="'+v+'">'+v +'</span>';
		});
		return html;
	},
	Comment: function(value) {
		return value;
	},
	Assign: function(value) {
		var html = "";
		$.each(JSON.parse(value || "[]"), function(i, v) {
			if(v) html+= '<span class="label label-warning" \
				style="margin-right: 7px;"\
				data-field="_assign">'+v+'</span>';
		});
		return html;
	},
	SmallText: function(value) {
		return vmraid.form.formatters.Text(value);
	},
	TextEditor: function(value) {
		let formatted_value = vmraid.form.formatters.Text(value);
		// to use ql-editor styles
		try {
			if (!$(formatted_value).find('.ql-editor').length) {
				formatted_value = `<div class="ql-editor read-mode">${formatted_value}</div>`;
			}
		} catch(e) {
			formatted_value = `<div class="ql-editor read-mode">${formatted_value}</div>`;
		}

		return formatted_value;
	},
	Code: function(value) {
		return "<pre>" + (value==null ? "" : $("<div>").text(value).html()) + "</pre>"
	},
	WorkflowState: function(value) {
		var workflow_state = vmraid.get_doc("Workflow State", value);
		if(workflow_state) {
			return repl("<span class='label label-%(style)s' \
				data-workflow-state='%(value)s'\
				style='padding-bottom: 4px; cursor: pointer;'>\
				<i class='fa fa-small fa-white fa-%(icon)s'></i> %(value)s</span>", {
					value: value,
					style: workflow_state.style.toLowerCase(),
					icon: workflow_state.icon
				});
		} else {
			return "<span class='label'>" + value + "</span>";
		}
	},
	Email: function(value) {
		return $("<div></div>").text(value).html();
	},
	FileSize: function(value) {
		if(value > 1048576) {
			value = flt(flt(value) / 1048576, 1) + "M";
		} else if (value > 1024) {
			value = flt(flt(value) / 1024, 1) + "K";
		}
		return value;
	},
	TableMultiSelect: function(rows, df, options) {
		rows = rows || [];
		const meta = vmraid.get_meta(df.options);
		const link_field = meta.fields.find(df => df.fieldtype === 'Link');
		const formatted_values = rows.map(row => {
			const value = row[link_field.fieldname];
			return vmraid.format(value, link_field, options, row);
		});
		return formatted_values.join(', ');
	},
	Color: (value) => {
		return value ? `<div>
			<div class="selected-color" style="background-color: ${value}"></div>
			<span class="color-value">${value}</span>
		</div>` : '';
	}
};

vmraid.form.get_formatter = function(fieldtype) {
	if(!fieldtype)
		fieldtype = "Data";
	return vmraid.form.formatters[fieldtype.replace(/ /g, "")] || vmraid.form.formatters.Data;
}

vmraid.format = function(value, df, options, doc) {
	if(!df) df = {"fieldtype":"Data"};
	var fieldtype = df.fieldtype || "Data";

	// format Dynamic Link as a Link
	if(fieldtype==="Dynamic Link") {
		fieldtype = "Link";
		df._options = doc ? doc[df.options] : null;
	}

	var formatter = df.formatter || vmraid.form.get_formatter(fieldtype);

	var formatted = formatter(value, df, options, doc);

	if (typeof formatted == "string")
		formatted = vmraid.dom.remove_script_and_style(formatted);

	return formatted;
};

vmraid.get_format_helper = function(doc) {
	var helper = {
		get_formatted: function(fieldname) {
			var df = vmraid.meta.get_docfield(doc.doctype, fieldname);
			if(!df) { console.log("fieldname not found: " + fieldname); }
			return vmraid.format(doc[fieldname], df, {inline:1}, doc);
		}
	};
	$.extend(helper, doc);
	return helper;
};

vmraid.form.link_formatters['User'] = function(value, doc, docfield) {
	let full_name = doc && (doc.full_name || (docfield && doc[`${docfield.fieldname}_full_name`]));
	return full_name || value;
};
