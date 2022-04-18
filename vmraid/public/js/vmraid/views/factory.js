// Copyright (c) 2015, VMRaid and Contributors
// MIT License. See license.txt

vmraid.provide('vmraid.pages');
vmraid.provide('vmraid.views');

vmraid.views.Factory = class Factory {
	constructor(opts) {
		$.extend(this, opts);
	}

	show() {
		this.route = vmraid.get_route();
		this.page_name = vmraid.get_route_str();

		if (this.before_show && this.before_show() === false) return;

		if (vmraid.pages[this.page_name]) {
			vmraid.container.change_to(this.page_name);
			if (this.on_show) {
				this.on_show();
			}
		} else {
			if (this.route[1]) {
				this.make(this.route);
			} else {
				vmraid.show_not_found(this.route);
			}
		}
	}

	make_page(double_column, page_name) {
		return vmraid.make_page(double_column, page_name);
	}
}

vmraid.make_page = function(double_column, page_name) {
	if (!page_name) {
		page_name = vmraid.get_route_str();
	}

	const page = vmraid.container.add_page(page_name);

	vmraid.ui.make_app_page({
		parent: page,
		single_column: !double_column
	});

	vmraid.container.change_to(page_name);
	return page;
}
