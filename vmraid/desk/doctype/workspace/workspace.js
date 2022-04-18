// Copyright (c) 2020, VMRaid Technologies and contributors
// For license information, please see license.txt

vmraid.ui.form.on('Workspace', {
	setup: function() {
		vmraid.meta.get_field('Workspace Link', 'only_for').no_default = true;
	},

	refresh: function(frm) {
		frm.enable_save();

		if (frm.doc.for_user || (frm.doc.public && !frm.has_perm('write') &&
			!vmraid.user.has_role('Workspace Manager'))) {
			frm.trigger('disable_form');
		}
	},

	disable_form: function(frm) {
		frm.fields
			.filter(field => field.has_input)
			.forEach(field => {
				frm.set_df_property(field.df.fieldname, "read_only", "1");
			});
		frm.disable_save();
	}
});