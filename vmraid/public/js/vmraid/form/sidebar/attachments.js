// Copyright (c) 2015, VMRaid Technologies Pvt. Ltd. and Contributors
// MIT License. See license.txt

vmraid.ui.form.Attachments = class Attachments {
	constructor(opts) {
		$.extend(this, opts);
		this.make();
	}
	make() {
		var me = this;
		this.parent.find(".add-attachment-btn").click(function() {
			me.new_attachment();
		});
		this.add_attachment_wrapper = this.parent.find(".add_attachment").parent();
		this.attachments_label = this.parent.find(".attachments-label");
	}
	max_reached(raise_exception=false) {
		const attachment_count = Object.keys(this.get_attachments()).length;
		const attachment_limit = this.frm.meta.max_attachments;
		if (attachment_limit && attachment_count >= attachment_limit) {
			if (raise_exception) {
				vmraid.throw({
					title: __("Attachment Limit Reached"),
					message: __("Maximum attachment limit of {0} has been reached.", [cstr(attachment_limit).bold()]),
				});
			}
			return true;
		}
		return false;
	}
	refresh() {
		var me = this;

		if(this.frm.doc.__islocal) {
			this.parent.toggle(false);
			return;
		}
		this.parent.toggle(true);
		this.parent.find(".attachment-row").remove();

		var max_reached = this.max_reached();
		this.add_attachment_wrapper.toggleClass("hide", !max_reached);

		// add attachment objects
		var attachments = this.get_attachments();
		if(attachments.length) {
			attachments.forEach(function(attachment) {
				me.add_attachment(attachment)
			});
		} else {
			this.attachments_label.removeClass("has-attachments");
		}

	}
	get_attachments() {
		return this.frm.get_docinfo().attachments;
	}
	add_attachment(attachment) {
		var file_name = attachment.file_name;
		var file_url = this.get_file_url(attachment);
		var fileid = attachment.name;
		if (!file_name) {
			file_name = file_url;
		}

		var me = this;

		let file_label = `
			<a href="${file_url}" target="_blank" title="${file_name}" class="ellipsis" style="max-width: calc(100% - 43px);">
				<span>${file_name}</span>
			</a>`;

		let remove_action = null;
		if (vmraid.model.can_write(this.frm.doctype, this.frm.name)) {
			remove_action = function(target_id) {
				vmraid.confirm(__("Are you sure you want to delete the attachment?"),
					function() {
						me.remove_attachment(target_id);
					}
				);
				return false;
			};
		}

		const icon = `<a href="/app/file/${fileid}">
				${vmraid.utils.icon(attachment.is_private ? 'lock' : 'unlock', 'sm ml-0')}
			</a>`;

		$(`<li class="attachment-row">`)
			.append(vmraid.get_data_pill(
				file_label,
				fileid,
				remove_action,
				icon
			))
			.insertAfter(this.attachments_label.addClass("has-attachments"));

	}
	get_file_url(attachment) {
		var file_url = attachment.file_url;
		if (!file_url) {
			if (attachment.file_name.indexOf('files/') === 0) {
				file_url = '/' + attachment.file_name;
			}
			else {
				file_url = '/files/' + attachment.file_name;
			}
		}
		// hash is not escaped, https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/encodeURI
		return encodeURI(file_url).replace(/#/g, '%23');
	}
	get_file_id_from_file_url(file_url) {
		var fid;
		$.each(this.get_attachments(), function(i, attachment) {
			if (attachment.file_url === file_url) {
				fid = attachment.name;
				return false;
			}
		});
		return fid;
	}
	remove_attachment_by_filename(filename, callback) {
		this.remove_attachment(this.get_file_id_from_file_url(filename), callback);
	}
	remove_attachment(fileid, callback) {
		if (!fileid) {
			if (callback) callback();
			return;
		}

		var me = this;
		return vmraid.call({
			method: 'vmraid.desk.form.utils.remove_attach',
			args: {
				fid: fileid,
				dt: me.frm.doctype,
				dn: me.frm.docname
			},
			callback: function(r,rt) {
				if(r.exc) {
					if(!r._server_messages)
						vmraid.msgprint(__("There were errors"));
					return;
				}
				me.remove_fileid(fileid);
				me.frm.sidebar.reload_docinfo();
				if (callback) callback();
			}
		});
	}
	new_attachment(fieldname) {
		if (this.dialog) {
			// remove upload dialog
			this.dialog.$wrapper.remove();
		}

		new vmraid.ui.FileUploader({
			doctype: this.frm.doctype,
			docname: this.frm.docname,
			frm: this.frm,
			folder: 'Home/Attachments',
			on_success: (file_doc) => {
				this.attachment_uploaded(file_doc);
			}
		});
	}
	get_args() {
		return {
			from_form: 1,
			doctype: this.frm.doctype,
			docname: this.frm.docname,
		}
	}
	attachment_uploaded(attachment) {
		this.dialog && this.dialog.hide();
		this.update_attachment(attachment);
		this.frm.sidebar.reload_docinfo();

		if(this.fieldname) {
			this.frm.set_value(this.fieldname, attachment.file_url);
		}
	}
	update_attachment(attachment) {
		if(attachment.name) {
			this.add_to_attachments(attachment);
			this.refresh();
		}
	}
	add_to_attachments (attachment) {
		var form_attachments = this.get_attachments();
		for(var i in form_attachments) {
			// prevent duplicate
			if(form_attachments[i]["name"] === attachment.name) return;
		}
		form_attachments.push(attachment);
	}
	remove_fileid(fileid) {
		var attachments = this.get_attachments();
		var new_attachments = [];
		$.each(attachments, function(i, attachment) {
			if(attachment.name!=fileid) {
				new_attachments.push(attachment);
			}
		});
		this.frm.get_docinfo().attachments = new_attachments;
		this.refresh();
	}
};
