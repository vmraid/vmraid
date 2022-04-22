import { Chart } from "frappe-charts/dist/frappe-charts.esm";

vmraid.provide("vmraid.ui");
vmraid.Chart = Chart;

vmraid.ui.RealtimeChart = class RealtimeChart extends vmraid.Chart {
	constructor(element, socketEvent, maxLabelPoints = 8, data) {
		super(element, data);
		if (data.data.datasets[0].values.length > maxLabelPoints) {
			vmraid.throw(
				__(
					"Length of passed data array is greater than value of maximum allowed label points!"
				)
			);
		}
		this.currentSize = data.data.datasets[0].values.length;
		this.socketEvent = socketEvent;
		this.maxLabelPoints = maxLabelPoints;

		this.start_updating = function() {
			vmraid.realtime.on(this.socketEvent, data => {
				this.update_chart(data.label, data.points);
			});
		};

		this.stop_updating = function() {
			vmraid.realtime.off(this.socketEvent);
		};

		this.update_chart = function(label, data) {
			if (this.currentSize >= this.maxLabelPoints) {
				this.removeDataPoint(0);
			} else {
				this.currentSize++;
			}
			this.addDataPoint(label, data);
		};
	}
};
