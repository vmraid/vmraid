// Copyright (c) 2015, VMRaid and Contributors
// MIT License. See license.txt

// route urls to their virtual pages

// re-route map (for rename)
vmraid.provide('vmraid.views');
vmraid.re_route = {"#login": ""};
vmraid.route_titles = {};
vmraid.route_flags = {};
vmraid.route_history = [];
vmraid.view_factory = {};
vmraid.view_factories = [];
vmraid.route_options = null;
vmraid.route_hooks = {};

$(window).on('hashchange', function(e) {
	// v1 style routing, route is in hash
	if (window.location.hash && !vmraid.router.is_app_route(e.currentTarget.pathname)) {
		let sub_path = vmraid.router.get_sub_path(window.location.hash);
		vmraid.router.push_state(sub_path);
		return false;
	}
});

window.addEventListener('popstate', (e) => {
	// forward-back button, just re-render based on current route
	vmraid.router.route();
	e.preventDefault();
	return false;
});

// routing v2, capture all clicks so that the target is managed with push-state
$('body').on('click', 'a', function(e) {
	let override = (route) => {
		e.preventDefault();
		vmraid.set_route(route);
		return false;
	};

	const href = e.currentTarget.getAttribute('href');

	// click handled, but not by href
	if (e.currentTarget.getAttribute('onclick') // has a handler
		|| (e.ctrlKey || e.metaKey) // open in a new tab
		|| href==='#') { // hash is home
		return;
	}

	if (href === '') {
		return override('/app');
	}

	if (href && href.startsWith('#')) {
		// target startswith "#", this is a v1 style route, so remake it.
		return override(e.currentTarget.hash);
	}

	if (vmraid.router.is_app_route(e.currentTarget.pathname)) {
		// target has "/app, this is a v2 style route.

		vmraid.route_options = {};
		let params = new URLSearchParams(e.currentTarget.search);
		for (const [key, value] of params) {
			vmraid.route_options[key] = value;
		}
		return override(e.currentTarget.pathname + e.currentTarget.hash);
	}

});

vmraid.router = {
	current_route: null,
	routes: {},
	factory_views: ['form', 'list', 'report', 'tree', 'print', 'dashboard'],
	list_views: ['list', 'kanban', 'report', 'calendar', 'tree', 'gantt', 'dashboard', 'image', 'inbox'],
	layout_mapped: {},

	is_app_route(path) {
		// desk paths must begin with /app or doctype route
		if (path.substr(0, 1) === '/') path = path.substr(1);
		path = path.split('/');
		if (path[0]) {
			return path[0]==='app';
		}
	},

	setup() {
		// setup the route names by forming slugs of the given doctypes
		for (let doctype of vmraid.boot.user.can_read) {
			this.routes[this.slug(doctype)] = {doctype: doctype};
		}
		if (vmraid.boot.doctype_layouts) {
			for (let doctype_layout of vmraid.boot.doctype_layouts) {
				this.routes[this.slug(doctype_layout.name)] = {doctype: doctype_layout.document_type, doctype_layout: doctype_layout.name };
			}
		}
	},

	route() {
		// resolve the route from the URL or hash
		// translate it so the objects are well defined
		// and render the page as required

		if (!vmraid.app) return;

		let sub_path = this.get_sub_path();
		if (this.re_route(sub_path)) return;

		this.current_sub_path = sub_path;
		this.current_route = this.parse();
		this.set_history(sub_path);
		this.render();
		this.set_title(sub_path);
		this.trigger('change');
	},

	parse(route) {
		route = this.get_sub_path_string(route).split('/');
		if (!route) return [];
		route = $.map(route, this.decode_component);
		this.set_route_options_from_url(route);
		return this.convert_to_standard_route(route);
	},

	convert_to_standard_route(route) {
		// /app/settings = ["Workspaces", "Settings"]
		// /app/private/settings = ["Workspaces", "private", "Settings"]
		// /app/user = ["List", "User"]
		// /app/user/view/report = ["List", "User", "Report"]
		// /app/user/view/tree = ["Tree", "User"]
		// /app/user/user-001 = ["Form", "User", "user-001"]
		// /app/user/user-001 = ["Form", "User", "user-001"]
		// /app/event/view/calendar/default = ["List", "Event", "Calendar", "Default"]

		let private_workspace = route[1] && `${route[1]}-${vmraid.user.name.toLowerCase()}`;

		if (vmraid.workspaces[route[0]]) {
			// public workspace
			route = ['Workspaces', vmraid.workspaces[route[0]].title];
		} else if (route[0] == 'private' && vmraid.workspaces[private_workspace]) {
			// private workspace
			route = ['Workspaces', 'private', vmraid.workspaces[private_workspace].title];
		} else if (this.routes[route[0]]) {
			// route
			route = this.set_doctype_route(route);
		}

		return route;
	},

	doctype_route_exist(route) {
		route = this.get_sub_path_string(route).split('/');
		return this.routes[route[0]];
	},

	set_doctype_route(route) {
		let doctype_route = this.routes[route[0]];
		// doctype route
		if (route[1]) {
			if (route[2] && route[1]==='view') {
				route = this.get_standard_route_for_list(route, doctype_route);
			} else {
				let docname = route[1];
				if (route.length > 2) {
					docname = route.slice(1).join('/');
				}
				route = ['Form', doctype_route.doctype, docname];
			}
		} else if (vmraid.model.is_single(doctype_route.doctype)) {
			route = ['Form', doctype_route.doctype, doctype_route.doctype];
		} else {
			route = ['List', doctype_route.doctype, 'List'];
		}

		if (doctype_route.doctype_layout) {
			// set the layout
			this.doctype_layout = doctype_route.doctype_layout;
		}

		return route;
	},

	get_standard_route_for_list(route, doctype_route) {
		let standard_route;
		if (route[2].toLowerCase()==='tree') {
			standard_route = ['Tree', doctype_route.doctype];
		} else {
			standard_route = ['List', doctype_route.doctype, vmraid.utils.to_title_case(route[2])];
			// calendar / kanban / dashboard / folder
			if (route[3]) standard_route.push(...route.slice(3, route.length));
		}
		return standard_route;
	},

	set_history() {
		vmraid.route_history.push(this.current_route);
		vmraid.ui.hide_open_dialog();
	},

	render() {
		if (this.current_route[0]) {
			this.render_page();
		} else {
			// Show home
			vmraid.views.pageview.show('');
		}
	},

	render_page() {
		// create the page generator (factory) object and call `show`
		// if there is no generator, render the `Page` object

		const route = this.current_route;
		const factory = vmraid.utils.to_title_case(route[0]);

		if (route[1] && vmraid.views[factory + "Factory"]) {
			route[0] = factory;
			// has a view generator, generate!
			if (!vmraid.view_factory[factory]) {
				vmraid.view_factory[factory] = new vmraid.views[factory + "Factory"]();
			}

			vmraid.view_factory[factory].show();
		} else {
			// show page
			const route_name = vmraid.utils.xss_sanitise(route[0]);
			if (vmraid.views.pageview) {
				vmraid.views.pageview.show(route_name);
			}
		}
	},

	re_route(sub_path) {
		if (vmraid.re_route[sub_path] !== undefined) {
			// after saving a doc, for example,
			// "new-doctype-1" and the renamed "TestDocType", both exist in history
			// now if we try to go back,
			// it doesn't allow us to go back to the one prior to "new-doctype-1"
			// Hence if this check is true, instead of changing location hash,
			// we just do a back to go to the doc previous to the "new-doctype-1"
			const re_route_val = this.get_sub_path(vmraid.re_route[sub_path]);
			if (re_route_val === this.current_sub_path) {
				window.history.back();
			} else {
				vmraid.set_route(re_route_val);
			}

			return true;
		}
	},

	set_title(sub_path) {
		if (vmraid.route_titles[sub_path]) {
			vmraid.utils.set_title(vmraid.route_titles[sub_path]);
		}
	},

	set_route() {
		// set the route (push state) with given arguments
		// example 1: vmraid.set_route('a', 'b', 'c');
		// example 2: vmraid.set_route(['a', 'b', 'c']);
		// example 3: vmraid.set_route('a/b/c');
		let route = Array.from(arguments);

		return new Promise(resolve => {
			route = this.get_route_from_arguments(route);
			route = this.convert_from_standard_route(route);
			let sub_path = this.make_url(route);
			// replace each # occurrences in the URL with encoded character except for last
			// sub_path = sub_path.replace(/[#](?=.*[#])/g, "%23");
			this.push_state(sub_path);

			setTimeout(() => {
				vmraid.after_ajax && vmraid.after_ajax(() => {
					resolve();
				});
			}, 100);
		}).finally(() => vmraid.route_flags = {});
	},

	get_route_from_arguments(route) {
		if (route.length===1 && $.isArray(route[0])) {
			// called as vmraid.set_route(['a', 'b', 'c']);
			route = route[0];
		}

		if (route.length===1 && route[0] && route[0].includes('/')) {
			// called as vmraid.set_route('a/b/c')
			route = $.map(route[0].split('/'), this.decode_component);
		}

		if (route && route[0] == '') {
			route.shift();
		}

		if (route && ['desk', 'app'].includes(route[0])) {
			// we only need subpath, remove "app" (or "desk")
			route.shift();
		}

		return route;

	},

	convert_from_standard_route(route) {
		// ["List", "Sales Order"] => /sales-order
		// ["Form", "Sales Order", "SO-0001"] => /sales-order/SO-0001
		// ["Tree", "Account"] = /account/view/tree

		const view = route[0] ? route[0].toLowerCase() : '';
		let new_route = route;
		if (view === 'list') {
			if (route[2] && route[2] !== 'list' && !$.isPlainObject(route[2])) {
				new_route = [this.slug(route[1]), 'view', route[2].toLowerCase()];

				// calendar / inbox / file folder
				if (route[3]) new_route.push(...route.slice(3, route.length));
			} else {
				if ($.isPlainObject(route[2])) {
					vmraid.route_options = route[2];
				}
				new_route = [this.slug(route[1])];
			}
		} else if (view === 'form') {
			new_route = [this.slug(route[1])];
			if (route[2]) {
				// if not single
				new_route.push(route[2]);
			}
		} else if (view === 'tree') {
			new_route = [this.slug(route[1]), 'view', 'tree'];
		}
		return new_route;
	},

	slug_parts(route) {
		// slug doctype

		// if app is part of the route, then first 2 elements are "" and "app"
		if (route[0] && this.factory_views.includes(route[0].toLowerCase())) {
			route[0] = route[0].toLowerCase();
			route[1] = this.slug(route[1]);
		}
		return route;
	},

	make_url(params) {
		let path_string = $.map(params, function(a) {
			if ($.isPlainObject(a)) {
				vmraid.route_options = a;
				return null;
			} else {
				a = String(a);
				if (a && a.match(/[%'"#\s\t]/)) {
					// if special chars, then encode
					a = encodeURIComponent(a);
				}
				return a;
			}
		}).join('/');
		let private_home = vmraid.workspaces[`home-${vmraid.user.name.toLowerCase()}`];
		let default_page = private_home ? 'private/home' : vmraid.workspaces['home'] ? 'home' : Object.keys(vmraid.workspaces)[0];
		return '/app/' + (path_string || default_page);
	},

	push_state(url) {
		// change the URL and call the router
		if (window.location.pathname !== url) {

			// push/replace state so the browser looks fine
			const method = vmraid.route_flags.replace_route ? "replaceState" : "pushState";
			history[method](null, null, url);

			// now process the route
			this.route();
		}
	},

	get_sub_path_string(route) {
		// return clean sub_path from hash or url
		// supports both v1 and v2 routing
		if (!route) {
			route = window.location.pathname;
			if (route.includes('app#')) {
				// to support v1
				route = window.location.hash;
			}
		}

		return this.strip_prefix(route);
	},

	strip_prefix(route) {
		if (route.substr(0, 1)=='/') route = route.substr(1); // for /app/sub
		if (route.startsWith('app/')) route = route.substr(4); // for desk/sub
		if (route == 'app') route = route.substr(4); // for /app
		if (route.substr(0, 1)=='/') route = route.substr(1);
		if (route.substr(0, 1)=='#') route = route.substr(1);
		if (route.substr(0, 1)=='!') route = route.substr(1);
		return route;
	},

	get_sub_path(route) {
		var sub_path = this.get_sub_path_string(route);
		route = $.map(sub_path.split('/'), this.decode_component).join('/');

		return route;
	},

	set_route_options_from_url(route) {
		// set query parameters as vmraid.route_options
		var last_part = route[route.length - 1];
		if (last_part.indexOf("?") < last_part.indexOf("=")) {
			// has ? followed by =
			let parts = last_part.split("?");

			// route should not contain string after ?
			route[route.length - 1] = parts[0];

			let query_params = vmraid.utils.get_query_params(parts[1]);
			vmraid.route_options = $.extend(vmraid.route_options || {}, query_params);
		}
	},

	decode_component(r) {
		try {
			return decodeURIComponent(r);
		} catch (e) {
			if (e instanceof URIError) {
				// legacy: not sure why URIError is ignored.
				return r;
			} else {
				throw e;
			}
		}
	},

	slug(name) {
		return name.toLowerCase().replace(/ /g, '-');
	}
};

// global functions for backward compatibility
vmraid.get_route = () => vmraid.router.current_route;
vmraid.get_route_str = () => vmraid.router.current_route.join('/');
vmraid.set_route = function() {
	return vmraid.router.set_route.apply(vmraid.router, arguments);
};

vmraid.get_prev_route = function() {
	if (vmraid.route_history && vmraid.route_history.length > 1) {
		return vmraid.route_history[vmraid.route_history.length - 2];
	} else {
		return [];
	}
};

vmraid.set_re_route = function() {
	var tmp = vmraid.router.get_sub_path();
	vmraid.set_route.apply(null, arguments);
	vmraid.re_route[tmp] = vmraid.router.get_sub_path();
};

vmraid.has_route_options = function() {
	return Boolean(Object.keys(vmraid.route_options || {}).length);
};

vmraid.utils.make_event_emitter(vmraid.router);
