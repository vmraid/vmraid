vmraid.ui.form.ControlDatetime = class ControlDatetime extends vmraid.ui.form.ControlDate {
	set_date_options() {
		super.set_date_options();
		this.today_text = __("Now");
		let sysdefaults = vmraid.boot.sysdefaults;
		this.date_format = vmraid.defaultDatetimeFormat;
		let time_format = sysdefaults && sysdefaults.time_format
			? sysdefaults.time_format : 'HH:mm:ss';
		$.extend(this.datepicker_options, {
			timepicker: true,
			timeFormat: time_format.toLowerCase().replace("mm", "ii")
		});
	}
	get_now_date() {
		return vmraid.datetime.now_datetime(true);
	}
	set_description() {
		const { description } = this.df;
		const { time_zone } = vmraid.sys_defaults;
		if (!this.df.hide_timezone && !vmraid.datetime.is_timezone_same()) {
			if (!description) {
				this.df.description = time_zone;
			} else if (!description.includes(time_zone)) {
				this.df.description += '<br>' + time_zone;
			}
		}
		super.set_description();
	}
	set_datepicker() {
		super.set_datepicker();
		if (this.datepicker.opts.timeFormat.indexOf('s') == -1) {
			// No seconds in time format
			const $tp = this.datepicker.timepicker;
			$tp.$seconds.parent().css('display', 'none');
			$tp.$secondsText.css('display', 'none');
			$tp.$secondsText.prev().css('display', 'none');
		}
	}
};
