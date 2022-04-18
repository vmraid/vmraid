import Vue from 'vue/dist/vue.js';
import VueRouter from 'vue-router/dist/vue-router.js';

import RecorderRoot from "./RecorderRoot.vue";

import RecorderDetail from "./RecorderDetail.vue";
import RequestDetail from "./RequestDetail.vue";

Vue.prototype.__ = window.__;
Vue.prototype.vmraid = window.vmraid;

Vue.use(VueRouter);
const routes = [
	{
		name: "recorder-detail",
		path: '/detail',
		component: RecorderDetail,
	},
	{
		name: "request-detail",
		path: '/request/:id',
		component: RequestDetail,
	},
	{
		path: '/',
		redirect: {
			name: "recorder-detail"
		}
	}
];

const router = new VueRouter({
	mode: 'history',
	base: "/app/recorder/",
	routes: routes,
});

vmraid.recorder.view = new Vue({
	el: ".recorder-container",
	router: router,
	data: {
		page: vmraid.pages["recorder"].page
	},
	template: "<recorder-root/>",
	components: {
		RecorderRoot,
	}
});
