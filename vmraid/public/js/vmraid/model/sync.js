// Copyright (c) 2015, VMRaid and Contributors
// MIT License. See license.txt

Object.assign(vmraid.model, {
	docinfo: {},
	sync: function(r) {
		/* docs:
			extract docs, docinfo (attachments, comments, assignments)
			from incoming request and set in `locals` and `vmraid.model.docinfo`
		*/
		var isPlain;
		if(!r.docs && !r.docinfo) r = {docs:r};

		isPlain = $.isPlainObject(r.docs);
		if(isPlain) r.docs = [r.docs];

		if(r.docs) {

			for(var i=0, l=r.docs.length; i<l; i++) {
				var d = r.docs[i];

				if (locals[d.doctype] && locals[d.doctype][d.name]) {
					// update values
					vmraid.model.update_in_locals(d);
				} else {
					vmraid.model.add_to_locals(d);
				}

				d.__last_sync_on = new Date();

				if(d.doctype==="DocType") {
					vmraid.meta.sync(d);
				}

				if(d.localname) {
					vmraid.model.rename_after_save(d, i);
				}
			}
		}

		vmraid.model.sync_docinfo(r);
		return r.docs;
	},

	rename_after_save: (d, i) => {
		vmraid.model.new_names[d.localname] = d.name;
		$(document).trigger('rename', [d.doctype, d.localname, d.name]);
		delete locals[d.doctype][d.localname];

		// update docinfo to new dict keys
		if(i===0) {
			vmraid.model.docinfo[d.doctype][d.name] = vmraid.model.docinfo[d.doctype][d.localname];
			vmraid.model.docinfo[d.doctype][d.localname] = undefined;
		}
	},

	sync_docinfo: (r) => {
		// set docinfo (comments, assign, attachments)
		if(r.docinfo) {
			var doc;
			if(r.docs) {
				doc = r.docs[0];
			} else {
				if(cur_frm) doc = cur_frm.doc;
			}
			if(doc) {
				if(!vmraid.model.docinfo[doc.doctype])
					vmraid.model.docinfo[doc.doctype] = {};
				vmraid.model.docinfo[doc.doctype][doc.name] = r.docinfo;
			}

			// copy values to vmraid.boot.user_info
			Object.assign(vmraid.boot.user_info, r.docinfo.user_info);
		}

		return r.docs;
	},

	add_to_locals: function(doc) {
		if(!locals[doc.doctype])
			locals[doc.doctype] = {};

		if(!doc.name && doc.__islocal) { // get name (local if required)
			if(!doc.parentfield) vmraid.model.clear_doc(doc);

			doc.name = vmraid.model.get_new_name(doc.doctype);

			if(!doc.parentfield) vmraid.provide("vmraid.model.docinfo." + doc.doctype + "." + doc.name);
		}

		locals[doc.doctype][doc.name] = doc;

		let meta = vmraid.get_meta(doc.doctype);
		let is_table = meta ? meta.istable : doc.parentfield;
		// add child docs to locals
		if (!is_table) {
			for(var i in doc) {
				var value = doc[i];

				if($.isArray(value)) {
					for (var x=0, y=value.length; x < y; x++) {
						var d = value[x];

						if(typeof d=='object' && !d.parent)
							d.parent = doc.name;

						vmraid.model.add_to_locals(d);
					}
				}
			}
		}
	},

	update_in_locals: function(doc) {
		// update values in the existing local doc instead of replacing
		let local_doc = locals[doc.doctype][doc.name];
		let clear_keys = function(source, target) {
			Object.keys(target).map(key => {
				if (source[key] == undefined) delete target[key];
			});
		}

		for (let fieldname in doc) {
			let df = vmraid.meta.get_field(doc.doctype, fieldname);
			if (df && vmraid.model.table_fields.includes(df.fieldtype)) {
				// table
				if (!(doc[fieldname] instanceof Array)) {
					doc[fieldname] = [];
				}

				if (!(local_doc[fieldname] instanceof Array)) {
					local_doc[fieldname] = [];
				}

				// child table, override each row and append new rows if required
				for (let i=0; i < doc[fieldname].length; i++ ) {
					let d = doc[fieldname][i];
					let local_d = local_doc[fieldname][i];
					if (local_d) {
						// deleted and added again
						if (!locals[d.doctype]) locals[d.doctype] = {};

						if (!d.name) {
							// incoming row is new, find a new name
							d.name = vmraid.model.get_new_name(doc.doctype);
						}

						// if incoming row is not registered, register it
						if (!locals[d.doctype][d.name]) {
							// detach old key
							delete locals[d.doctype][local_d.name];

							// re-attach with new name
							locals[d.doctype][d.name] = local_d;
						}

						// row exists, just copy the values
						Object.assign(local_d, d);
						clear_keys(d, local_d);

					} else {
						local_doc[fieldname].push(d);
						if (!d.parent) d.parent = doc.name;
						vmraid.model.add_to_locals(d);
					}
				}

				// remove extra rows
				if (local_doc[fieldname].length > doc[fieldname].length) {
					for (let i = doc[fieldname].length; i < local_doc[fieldname].length; i++) {

						// clear from local
						let d = local_doc[fieldname][i];
						if (locals[d.doctype] && locals[d.doctype][d.name]) {
							delete locals[d.doctype][d.name];
						}
					}
					local_doc[fieldname].length = doc[fieldname].length;

				}
			} else {
				// literal
				local_doc[fieldname] = doc[fieldname];
			}
		}

		// clear keys on parent
		clear_keys(doc, local_doc);
	}

});
