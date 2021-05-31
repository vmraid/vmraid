vmraid.ui.form.ControlTime = class ControlTime extends vmraid.ui.form.ControlDate {
	set_formatted_input(value) {
		super.set_formatted_input(value);
	}
	make_input() {
		this.timepicker_only = true;
		super.make_input();
	}
	make_picker() {
		this.set_time_options();
		this.set_datepicker();
		this.refresh();
	}
	set_time_options() {
		let sysdefaults = vmraid.boot.sysdefaults;

		let time_format = sysdefaults && sysdefaults.time_format
			? sysdefaults.time_format : 'HH:mm:ss';

		this.time_format = vmraid.defaultTimeFormat;
		this.datepicker_options = {
			language: "en",
			timepicker: true,
			onlyTimepicker: true,
			timeFormat: time_format.toLowerCase().replace("mm", "ii"),
			startDate: vmraid.datetime.now_time(true),
			onSelect: () => {
				// ignore micro seconds
				if (moment(this.get_value(), time_format).format('HH:mm:ss') != moment(this.value, time_format).format('HH:mm:ss')) {
					this.$input.trigger('change');
				}
			},
			onShow: () => {
				$('.datepicker--button:visible').text(__('Now'));

				this.update_datepicker_position();
			},
			keyboardNav: false,
			todayButton: true
		};
	}
	set_input(value) {
		super.set_input(value);
		if (value
			&& ((this.last_value && this.last_value !== this.value)
				|| (!this.datepicker.selectedDates.length))) {

			let time_format = vmraid.sys_defaults.time_format || 'HH:mm:ss';
			var date_obj = vmraid.datetime.moment_to_date_obj(moment(value, time_format));
			this.datepicker.selectDate(date_obj);
		}
	}
	set_datepicker() {
		this.$input.datepicker(this.datepicker_options);
		this.datepicker = this.$input.data('datepicker');

		this.datepicker.$datepicker
			.find('[data-action="today"]')
			.click(() => {
				this.datepicker.selectDate(vmraid.datetime.now_time(true));
				this.datepicker.hide();
			});
		if (this.datepicker.opts.timeFormat.indexOf('s') == -1) {
			// No seconds in time format
			const $tp = this.datepicker.timepicker;
			$tp.$seconds.parent().css('display', 'none');
			$tp.$secondsText.css('display', 'none');
			$tp.$secondsText.prev().css('display', 'none');
		}
	}
	set_description() {
		const { description } = this.df;
		const { time_zone } = vmraid.sys_defaults;
		if (!vmraid.datetime.is_timezone_same()) {
			if (!description) {
				this.df.description = time_zone;
			} else if (!description.includes(time_zone)) {
				this.df.description += '<br>' + time_zone;
			}
		}
		super.set_description();
	}
	parse(value) {
		if (value) {
			return vmraid.datetime.user_to_str(value, true);
		}
	}
	format_for_input(value) {
		if (value) {
			return vmraid.datetime.str_to_user(value, true);
		}
		return "";
	}
	validate(value) {
		if (value && !vmraid.datetime.validate(value)) {
			let sysdefaults = vmraid.sys_defaults;
			let time_format = sysdefaults && sysdefaults.time_format
				? sysdefaults.time_format : 'HH:mm:ss';
			vmraid.msgprint(__("Time {0} must be in format: {1}", [value, time_format]));
			return '';
		}
		return value;
	}
};
