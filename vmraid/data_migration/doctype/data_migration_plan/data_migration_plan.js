// Copyright (c) 2017, VMRaid Technologies and contributors
// For license information, please see license.txt

vmraid.ui.form.on('Data Migration Plan', {
	onload(frm) {
		frm.add_custom_button(__('Run'), () => vmraid.new_doc('Data Migration Run', {
			data_migration_plan: frm.doc.name
		}));
	}
});
