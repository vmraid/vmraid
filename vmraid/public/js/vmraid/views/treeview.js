// Copyright (c) 2015, VMRaid Technologies Pvt. Ltd. and Contributors
// MIT License. See license.txt

vmraid.provide("vmraid.treeview_settings");
vmraid.provide('vmraid.views.trees');
window.cur_tree = null;

vmraid.views.TreeFactory = class TreeFactory extends vmraid.views.Factory {
	make(route) {
		vmraid.model.with_doctype(route[1], function() {
			var options = {
				doctype: route[1],
				meta: vmraid.get_meta(route[1])
			};

			if (!vmraid.treeview_settings[route[1]] && !vmraid.meta.get_docfield(route[1], "is_group")) {
				vmraid.msgprint(__("Tree view is not available for {0}", [route[1]] ));
				return false;
			}
			$.extend(options, vmraid.treeview_settings[route[1]] || {});
			vmraid.views.trees[options.doctype] = new vmraid.views.TreeView(options);
		});
	}
}

vmraid.views.TreeView = class TreeView {
	constructor(opts) {
		var me = this;

		this.opts = {};
		this.opts.get_tree_root = true;
		this.opts.show_expand_all = true;
		$.extend(this.opts, opts);
		this.doctype = opts.doctype;
		this.args = {doctype: me.doctype};
		this.page_name = vmraid.get_route_str();
		this.get_tree_nodes =  me.opts.get_tree_nodes || "vmraid.desk.treeview.get_children";

		this.get_permissions();
		this.make_page();
		this.make_filters();
		this.root_value = null;

		if (me.opts.get_tree_root) {
			this.get_root();
		}

		this.onload();
		this.set_menu_item();
		this.set_primary_action();
	}
	get_permissions(){
		this.can_read = vmraid.model.can_read(this.doctype);
		this.can_create = vmraid.boot.user.can_create.indexOf(this.doctype) !== -1 ||
					vmraid.boot.user.in_create.indexOf(this.doctype) !== -1;
		this.can_write = vmraid.model.can_write(this.doctype);
		this.can_delete = vmraid.model.can_delete(this.doctype);
	}
	make_page() {
		var me = this;
		this.parent = vmraid.container.add_page(this.page_name);
		vmraid.ui.make_app_page({parent:this.parent, single_column:true});

		this.page = this.parent.page;
		vmraid.container.change_to(this.page_name);
		vmraid.breadcrumbs.add(me.opts.breadcrumb || locals.DocType[me.doctype].module, me.doctype);

		this.set_title();

		this.page.main.css({
			"min-height": "300px",
		});

		this.page.main.addClass('vmraid-card');

		if(this.opts.show_expand_all) {
			this.page.add_inner_button(__('Expand All'), function() {
				me.tree.load_children(me.tree.root_node, true);
			});
		}

		if(this.opts.view_template) {
			var row = $('<div class="row"><div>').appendTo(this.page.main);
			this.body = $('<div class="col-sm-6 col-xs-12"></div>').appendTo(row);
			this.node_view = $('<div class="col-sm-6 hidden-xs"></div>').appendTo(row);
		} else {
			this.body = this.page.main;
		}
	}
	set_title() {
		this.page.set_title(this.opts.title || __('{0} Tree', [__(this.doctype)]));
	}
	onload() {
		var me = this;
		this.opts.onload && this.opts.onload(me);
	}
	make_filters() {
		var me = this;
		vmraid.treeview_settings.filters = []
		$.each(this.opts.filters || [], function(i, filter) {
			if (vmraid.route_options && vmraid.route_options[filter.fieldname]) {
				filter.default = vmraid.route_options[filter.fieldname];
			}

			if (!filter.disable_onchange) {
				filter.change = function() {
					filter.onchange && filter.onchange();
					var val = this.get_value();
					me.args[filter.fieldname] = val;
					if (val) {
						me.root_label = val;
					} else {
						me.root_label = me.opts.root_label;
					}
					me.set_title();
					me.make_tree();
				};
			}

			me.page.add_field(filter);

			if (filter.default) {
				$("[data-fieldname='"+filter.fieldname+"']").trigger("change");
			}
		});
	}
	get_root() {
		var me = this;
		vmraid.call({
			method: me.get_tree_nodes,
			args: me.args,
			callback: function(r) {
				if (r.message) {
					if (r.message.length > 1) {
						me.root_label = me.doctype;
						me.root_value = "";
					} else {
						me.root_label = r.message[0]["value"];
						me.root_value = me.root_label;
					}
					me.make_tree();
				}
			}
		})
	}
	make_tree() {
		$(this.parent).find(".tree").remove();

		var use_label = this.args[this.opts.root_label] || this.root_label || this.opts.root_label;
		var use_value = this.root_value;
		if (use_value == null) {
			use_value = use_label;
		}
		this.tree = new vmraid.ui.Tree({
			parent: this.body,
			label: use_label,
			root_value: use_value,
			expandable: true,

			args: this.args,
			method: this.get_tree_nodes,

			// array of button props: {label, condition, click, btnClass}
			toolbar: this.get_toolbar(),

			get_label: this.opts.get_label,
			on_render: this.opts.onrender,
			on_click: (node) => { this.select_node(node); },
		});

		cur_tree = this.tree;
		this.post_render();
	}

	rebuild_tree() {
		let me = this;

		vmraid.call({
			"method": "vmraid.utils.nestedset.rebuild_tree",
			"args": {
				'doctype': me.doctype,
				'parent_field': "parent_"+me.doctype.toLowerCase().replace(/ /g, '_'),
			},
			"callback": function(r) {
				if (!r.exc) {
					me.make_tree();
				}
			}
		});
	}

	post_render() {
		var me = this;
		me.opts.post_render && me.opts.post_render(me);
	}

	select_node(node) {
		var me = this;
		if(this.opts.click) {
			this.opts.click(node);
		}
		if(this.opts.view_template) {
			this.node_view.empty();
			$(vmraid.render_template(me.opts.view_template,
				{data:node.data, doctype:me.doctype})).appendTo(this.node_view);
		}
	}
	get_toolbar() {
		var me = this;

		var toolbar = [
			{
				label:__(me.can_write? "Edit": "Details"),
				condition: function(node) {
					return !node.is_root && me.can_read;
				},
				click: function(node) {
					vmraid.set_route("Form", me.doctype, node.label);
				}
			},
			{
				label:__("Add Child"),
				condition: function(node) {
					return me.can_create && node.expandable && !node.hide_add;
				},
				click: function(node) {
					me.new_node();
				},
				btnClass: "hidden-xs"
			},
			{
				label:__("Rename"),
				condition: function(node) {
					let allow_rename = true;
					if (me.doctype && vmraid.get_meta(me.doctype)) {
						if(!vmraid.get_meta(me.doctype).allow_rename) allow_rename = false;
					}
					return !node.is_root && me.can_write && allow_rename;
				},
				click: function(node) {
					vmraid.model.rename_doc(me.doctype, node.label, function(new_name) {
						node.$tree_link.find('a').text(new_name);
						node.label = new_name;
					});
				},
				btnClass: "hidden-xs"
			},
			{
				label:__("Delete"),
				condition: function(node) { return !node.is_root && me.can_delete; },
				click: function(node) {
					vmraid.model.delete_doc(me.doctype, node.label, function() {
						node.parent.remove();
					});
				},
				btnClass: "hidden-xs"
			}
		]

		if(this.opts.toolbar && this.opts.extend_toolbar) {
			toolbar = toolbar.filter(btn => {
				return !me.opts.toolbar.find(d => d["label"]==btn["label"]);
			});
			return toolbar.concat(this.opts.toolbar)
		} else if (this.opts.toolbar && !this.opts.extend_toolbar) {
			return this.opts.toolbar
		} else {
			return toolbar
		}
	}
	new_node() {
		var me = this;
		var node = me.tree.get_selected_node();

		if(!(node && node.expandable)) {
			vmraid.msgprint(__("Select a group node first."));
			return;
		}

		this.prepare_fields();

		// the dialog
		var d = new vmraid.ui.Dialog({
			title: __('New {0}',[__(me.doctype)]),
			fields: me.fields
		});

		var args = $.extend({}, me.args);
		args["parent_"+me.doctype.toLowerCase().replace(/ /g,'_')] = me.args["parent"];

		d.set_value("is_group", 0);
		d.set_values(args);

		// create
		d.set_primary_action(__("Create New"), function() {
			var btn = this;
			var v = d.get_values();
			if(!v) return;

			v.parent = node.label;
			v.doctype = me.doctype;

			if(node.is_root){
				v['is_root'] = node.is_root;
			}
			else{
				v['is_root'] = false;
			}

			d.hide();
			vmraid.dom.freeze(__('Creating {0}', [me.doctype]));

			$.extend(args, v)
			return vmraid.call({
				method: me.opts.add_tree_node || "vmraid.desk.treeview.add_node",
				args: args,
				callback: function(r) {
					if(!r.exc) {
						if(node.expanded) {
							me.tree.toggle_node(node);
						}
						me.tree.load_children(node, true);
					}
				},
				always: function() {
					vmraid.dom.unfreeze();
				},
			});
		});
		d.show();
	}
	prepare_fields(){
		var me = this;

		this.fields = [
			{fieldtype:'Check', fieldname:'is_group', label:__('Group Node'),
				description: __("Further nodes can be only created under 'Group' type nodes")}
		]

		if (this.opts.fields) {
			this.fields = this.opts.fields;
		}

		this.ignore_fields = this.opts.ignore_fields || [];

		var mandatory_fields = $.map(me.opts.meta.fields, function(d) {
			return (d.reqd || d.bold && !d.read_only) ? d : null });

		var opts_field_names = this.fields.map(function(d) {
			return d.fieldname
		})

		mandatory_fields.map(function(d) {
			if($.inArray(d.fieldname, me.ignore_fields) === -1 && $.inArray(d.fieldname, opts_field_names) === -1) {
				me.fields.push(d)
			}
		})
	}
	print_tree() {
		if(!vmraid.model.can_print(this.doctype)) {
			vmraid.msgprint(__("You are not allowed to print this report"));
			return false;
		}
		var tree = $(".tree:visible").html();
		var me = this;
		vmraid.ui.get_print_settings(false, function(print_settings) {
			var title =  __(me.docname || me.doctype);
			vmraid.render_tree({title: title, tree: tree, print_settings:print_settings});
			vmraid.call({
				method: "vmraid.core.doctype.access_log.access_log.make_access_log",
				args: {
					doctype: me.doctype,
					report_name: me.page_name,
					page: tree,
					method: 'Print'
				}
			});
		});
	}
	set_primary_action() {
		var me = this;
		if (!this.opts.disable_add_node && this.can_create) {
			me.page.set_primary_action(__("New"), function() {
				me.new_node();
			}, "add");
		}
	}
	set_menu_item() {
		var me = this;

		this.menu_items = [
			{
				label: __('View List'),
				action: function() {
					vmraid.set_route('List', me.doctype);
				}
			},
			{
				label: __('Print'),
				action: function() {
					me.print_tree();
				}

			},
			{
				label: __('Refresh'),
				action: function() {
					me.make_tree();
				}
			},
		];

		if (vmraid.user.has_role('System Manager')) {
			this.menu_items.push(
				{
					label: __('Rebuild Tree'),
					action: function() {
						me.rebuild_tree();
					}
				}
			);
		}

		if (me.opts.menu_items) {
			me.menu_items.push.apply(me.menu_items, me.opts.menu_items)
		}

		$.each(me.menu_items, function(i, menu_item){
			var has_perm = true;
			if(menu_item["condition"]) {
				has_perm = eval(menu_item["condition"]);
			}

			if (has_perm) {
				me.page.add_menu_item(menu_item["label"], menu_item["action"]);
			}
		});
	}
};








