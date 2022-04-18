// Copyright (c) 2015, VMRaid and Contributors
// MIT License. See license.txt

// page container
vmraid.provide('vmraid.pages');
vmraid.provide('vmraid.views');

window.cur_page = null;
vmraid.views.Container = class Container {
	// Container contains pages inside `#container` and manages page creation, switching
	constructor() {
		this.container = $('#body').get(0);
		this.page = null; // current page
		this.pagewidth = $(this.container).width();
		this.pagemargin = 50;

		var me = this;

		$(document).on("page-change", function() {
			// set data-route in body
			var route_str = vmraid.get_route_str();
			$("body").attr("data-route", route_str);
			$("body").attr("data-sidebar", me.has_sidebar() ? 1 : 0);
		});

		$(document).bind('rename', function(event, dt, old_name, new_name) {
			vmraid.breadcrumbs.rename(dt, old_name, new_name);
		});
	}
	add_page(label) {
		var page = $('<div class="content page-container"></div>')
			.attr('id', "page-" + label)
			.attr("data-page-route", label)
			.hide()
			.appendTo(this.container).get(0);
		page.label = label;
		vmraid.pages[label] = page;

		return page;
	}
	change_to(label) {
		cur_page = this;
		if(label.tagName) {
			// if sent the div, get the table
			var page = label;
		} else {
			var page = vmraid.pages[label];
		}
		if(!page) {
			console.log(__('Page not found')+ ': ' + label);
			return;
		}

		// hide dialog
		if(window.cur_dialog && cur_dialog.display && !cur_dialog.keep_open) {
			if (!cur_dialog.minimizable) {
				cur_dialog.hide();
			} else if (!cur_dialog.is_minimized) {
				cur_dialog.toggle_minimize();
			}
		}

		// hide current
		if(this.page && this.page != page) {
			$(this.page).hide();
			$(this.page).trigger('hide');
		}

		// show new
		if(!this.page || this.page != page) {
			this.page = page;
			// $(this.page).fadeIn(300);
			$(this.page).show();
		}

		$(document).trigger("page-change");

		this.page._route = vmraid.router.get_sub_path();
		$(this.page).trigger('show');
		!this.page.disable_scroll_to_top && vmraid.utils.scroll_to(0);
		vmraid.breadcrumbs.update();

		return this.page;
	}
	has_sidebar() {
		var flag = 0;
		var route_str = vmraid.get_route_str();
		// check in vmraid.ui.pages
		flag = vmraid.ui.pages[route_str] && !vmraid.ui.pages[route_str].single_column;

		// sometimes vmraid.ui.pages is updated later,
		// so check the dom directly
		if(!flag) {
			var page_route = route_str.split('/').slice(0, 2).join('/');
			flag = $(`.page-container[data-page-route="${page_route}"] .layout-side-section`).length ? 1 : 0;
		}

		return flag;
	}
};


