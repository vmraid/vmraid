// Copyright (c) 2015, VMRaid and Contributors
// MIT License. See license.txt
import FormTimeline from "./form_timeline";
vmraid.ui.form.Footer = class FormFooter {
	constructor(opts) {
		$.extend(this, opts);
		this.make();
		this.make_comment_box();
		this.make_timeline();
		// render-complete
		$(this.frm.wrapper).on("render_complete", () => {
			this.refresh();
		});
	}
	make() {
		this.wrapper = $(vmraid.render_template("form_footer", {}))
			.appendTo(this.parent);
		this.wrapper.find(".btn-save").click(() => {
			this.frm.save('Save', null, this);
		});
	}
	make_comment_box() {
		this.frm.comment_box = vmraid.ui.form.make_control({
			parent: this.wrapper.find(".comment-box"),
			render_input: true,
			only_input: true,
			enable_mentions: true,
			df: {
				fieldtype: 'Comment',
				fieldname: 'comment'
			},
			on_submit: (comment) => {
				if (strip_html(comment).trim() != "" || comment.includes('img')) {
					this.frm.comment_box.disable();
					vmraid.xcall("vmraid.desk.form.utils.add_comment", {
						reference_doctype: this.frm.doctype,
						reference_name: this.frm.docname,
						content: comment,
						comment_email: vmraid.session.user,
						comment_by: vmraid.session.user_fullname
					}).then((comment) => {
						let comment_item = this.frm.timeline.get_comment_timeline_item(comment);
						this.frm.comment_box.set_value('');
						vmraid.utils.play_sound("click");
						this.frm.timeline.add_timeline_item(comment_item);
						this.frm.sidebar.refresh_comments_count && this.frm.sidebar.refresh_comments_count();
					}).finally(() => {
						this.frm.comment_box.enable();
					});
				}
			}
		});
	}
	make_timeline() {
		this.frm.timeline = new FormTimeline({
			parent: this.wrapper.find(".timeline"),
			frm: this.frm
		});
	}
	refresh() {
		if (this.frm.doc.__islocal) {
			this.parent.addClass("hide");
		} else {
			this.parent.removeClass("hide");
			this.frm.timeline.refresh();
		}
	}
};
