import { ax as buildProps, ay as definePropType, Y as defineComponent, az as useNamespace, h as openBlock, a as createElementBlock, am as renderSlot, d as createVNode, w as withCtx, ak as normalizeStyle, t as normalizeClass, i as unref, f as createTextVNode, I as toDisplayString, F as createCommentVNode, an as Transition, K as computed, aA as isNumber, aB as addUnit, aC as withInstall, aD as useEmptyValuesProps, aE as useSizeProp, aF as provideGlobalConfig, m as watch, aG as mutable, ao as isClient, aH as iconPropType, aI as shallowReactive, a5 as useGlobalComponentSettings, o as onMounted, aJ as useEventListener, aK as useResizeObserver, n as createBlock, N as withDirectives, b as createBaseVNode, a0 as ElIcon, al as resolveDynamicComponent, O as Fragment, aj as withModifiers, $ as TypeComponents, S as vShow, g as ref, ag as TypeComponentsMap, aL as useTimeoutFn, U as nextTick, W as getEventCode, X as EVENT_CODE, ad as isString, ap as isVNode, ac as isFunction, ar as hasOwn, aq as render, at as isElement, au as debugWarn, aM as isBoolean, aN as withInstallFunction } from './index-DpF7b0Gh.js';

//#region ../../packages/components/badge/src/badge.ts
/**
* @deprecated Removed after 3.0.0, Use `BadgeProps` instead.
*/
const badgeProps = buildProps({
	/**
	* @description display value.
	*/
	value: {
		type: [String, Number],
		default: ""
	},
	/**
	* @description maximum value, shows `{max}+` when exceeded. Only works if value is a number.
	*/
	max: {
		type: Number,
		default: 99
	},
	/**
	* @description if a little dot is displayed.
	*/
	isDot: Boolean,
	/**
	* @description hidden badge.
	*/
	hidden: Boolean,
	/**
	* @description badge type.
	*/
	type: {
		type: String,
		values: [
			"primary",
			"success",
			"warning",
			"info",
			"danger"
		],
		default: "danger"
	},
	/**
	* @description whether to show badge when value is zero.
	*/
	showZero: {
		type: Boolean,
		default: true
	},
	/**
	* @description customize dot background color
	*/
	color: String,
	/**
	* @description CSS style of badge
	*/
	badgeStyle: {
		type: definePropType([
			String,
			Object,
			Array,
			Boolean
		]),
		default: void 0
	},
	/**
	* @description set offset of the badge
	*/
	offset: {
		type: definePropType(Array),
		default: () => [0, 0]
	},
	/**
	* @description custom class name of badge
	*/
	badgeClass: {
		type: definePropType([
			String,
			Array,
			Object,
			Boolean
		]),
		default: void 0
	}
});

//#region ../../packages/components/badge/src/badge.vue?vue&type=script&setup=true&lang.ts
var badge_vue_vue_type_script_setup_true_lang_default = /*@__PURE__*/ defineComponent({
	name: "ElBadge",
	__name: "badge",
	props: badgeProps,
	setup(__props, { expose: __expose }) {
		const props = __props;
		const ns = useNamespace("badge");
		const content = computed(() => {
			if (props.isDot) return "";
			if (isNumber(props.value) && isNumber(props.max)) return props.max < props.value ? `${props.max}+` : `${props.value}`;
			return `${props.value}`;
		});
		const style = computed(() => {
			return [{
				backgroundColor: props.color,
				marginRight: addUnit(-props.offset[0]),
				marginTop: addUnit(props.offset[1])
			}, props.badgeStyle ?? {}];
		});
		__expose({ 
		/** @description badge content */
content });
		return (_ctx, _cache) => {
			return openBlock(), createElementBlock("div", { class: normalizeClass(unref(ns).b()) }, [renderSlot(_ctx.$slots, "default"), createVNode(Transition, { name: `${unref(ns).namespace.value}-zoom-in-center` }, {
				default: withCtx(() => [!__props.hidden && (content.value || __props.isDot || _ctx.$slots.content) ? (openBlock(), createElementBlock("sup", {
					key: 0,
					class: normalizeClass([
						unref(ns).e("content"),
						unref(ns).em("content", __props.type),
						unref(ns).is("fixed", !!_ctx.$slots.default),
						unref(ns).is("dot", __props.isDot),
						unref(ns).is("hide-zero", !__props.showZero && __props.value === 0),
						__props.badgeClass
					]),
					style: normalizeStyle(style.value)
				}, [renderSlot(_ctx.$slots, "content", { value: content.value }, () => [createTextVNode(toDisplayString(content.value), 1)])], 6)) : createCommentVNode("v-if", true)]),
				_: 3
			}, 8, ["name"])], 2);
		};
	}
});

//#region ../../packages/components/badge/src/badge.vue
var badge_default = badge_vue_vue_type_script_setup_true_lang_default;

//#region ../../packages/components/badge/index.ts
const ElBadge = withInstall(badge_default);

//#region ../../packages/components/config-provider/src/config-provider-props.ts
const configProviderProps = buildProps({
	/**
	* @description Controlling if the users want a11y features
	*/
	a11y: {
		type: Boolean,
		default: true
	},
	/**
	* @description Locale Object
	*/
	locale: { type: definePropType(Object) },
	/**
	* @description global component size
	*/
	size: useSizeProp,
	/**
	* @description button related configuration, [see the following table](https://element-plus.org/en-US/component/config-provider.html#button-attribute)
	*/
	button: { type: definePropType(Object) },
	/**
	* @description card related configuration, [see the following table](https://element-plus.org/en-US/component/config-provider.html#card-attribute)
	*/
	card: { type: definePropType(Object) },
	/**
	* @description dialog related configuration, [see the following table](https://element-plus.org/en-US/component/config-provider.html#dialog-attribute)
	*/
	dialog: { type: definePropType(Object) },
	/**
	* @description link related configuration, [see the following table](https://element-plus.org/en-US/component/config-provider.html#link-attribute)
	*/
	link: { type: definePropType(Object) },
	/**
	* @description features at experimental stage to be added, all features are default to be set to false, [see the following table](https://element-plus.org/en-US/component/config-provider.html#experimental-features)                                                                            | ^[object]
	*/
	experimentalFeatures: { type: definePropType(Object) },
	/**
	* @description Controls if we should handle keyboard navigation
	*/
	keyboardNavigation: {
		type: Boolean,
		default: true
	},
	/**
	* @description message related configuration, [see the following table](https://element-plus.org/en-US/component/config-provider.html#message-attribute)
	*/
	message: { type: definePropType(Object) },
	/**
	* @description global Initial zIndex
	*/
	zIndex: Number,
	/**
	* @description global component className prefix (cooperated with [$namespace](https://github.com/element-plus/element-plus/blob/dev/packages/theme-chalk/src/mixins/config.scss#L1)) | ^[string]
	*/
	namespace: {
		type: String,
		default: "el"
	},
	/**
	* @description table related configuration, [see the following table](https://element-plus.org/en-US/component/config-provider.html#table-attribute)
	*/
	table: { type: definePropType(Object) },
	...useEmptyValuesProps
});

//#region ../../packages/components/config-provider/src/config-provider.ts
const messageConfig = { placement: "top" };
const ConfigProvider = defineComponent({
	name: "ElConfigProvider",
	props: configProviderProps,
	setup(props, { slots }) {
		const config = provideGlobalConfig(props);
		watch(() => props.message, (val) => {
			Object.assign(messageConfig, config?.value?.message ?? {}, val ?? {});
		}, {
			immediate: true,
			deep: true
		});
		return () => renderSlot(slots, "default", { config: config?.value });
	}
});

//#region ../../packages/components/message/src/message.ts
const messageTypes = [
	"primary",
	"success",
	"info",
	"warning",
	"error"
];
const messagePlacement = [
	"top",
	"top-left",
	"top-right",
	"bottom",
	"bottom-left",
	"bottom-right"
];
const messageDefaults = mutable({
	customClass: "",
	dangerouslyUseHTMLString: false,
	duration: 3e3,
	icon: void 0,
	id: "",
	message: "",
	onClose: void 0,
	showClose: false,
	type: "info",
	plain: false,
	offset: 16,
	placement: void 0,
	zIndex: 0,
	grouping: false,
	repeatNum: 1,
	appendTo: isClient ? document.body : void 0
});
/**
* @deprecated Removed after 3.0.0, Use `MessageProps` instead.
*/
const messageProps = buildProps({
	/**
	* @description custom class name for Message
	*/
	customClass: {
		type: definePropType([
			String,
			Array,
			Object,
			Boolean
		]),
		default: messageDefaults.customClass
	},
	/**
	* @description whether `message` is treated as HTML string
	*/
	dangerouslyUseHTMLString: {
		type: Boolean,
		default: messageDefaults.dangerouslyUseHTMLString
	},
	/**
	* @description display duration, millisecond. If set to 0, it will not turn off automatically
	*/
	duration: {
		type: Number,
		default: messageDefaults.duration
	},
	/**
	* @description custom icon component, overrides `type`
	*/
	icon: {
		type: iconPropType,
		default: messageDefaults.icon
	},
	/**
	* @description message dom id
	*/
	id: {
		type: String,
		default: messageDefaults.id
	},
	/**
	* @description message text
	*/
	message: {
		type: definePropType([
			String,
			Object,
			Function
		]),
		default: messageDefaults.message
	},
	/**
	* @description callback function when closed with the message instance as the parameter
	*/
	onClose: {
		type: definePropType(Function),
		default: messageDefaults.onClose
	},
	/**
	* @description whether to show a close button
	*/
	showClose: {
		type: Boolean,
		default: messageDefaults.showClose
	},
	/**
	* @description message type
	*/
	type: {
		type: String,
		values: messageTypes,
		default: messageDefaults.type
	},
	/**
	* @description whether message is plain
	*/
	plain: {
		type: Boolean,
		default: messageDefaults.plain
	},
	/**
	* @description set the distance to the top of viewport
	*/
	offset: {
		type: Number,
		default: messageDefaults.offset
	},
	/**
	* @description message placement position
	*/
	placement: {
		type: String,
		values: messagePlacement,
		default: messageDefaults.placement
	},
	/**
	* @description message element zIndex value
	*/
	zIndex: {
		type: Number,
		default: messageDefaults.zIndex
	},
	/**
	* @description merge messages with the same content, type of VNode message is not supported
	*/
	grouping: {
		type: Boolean,
		default: messageDefaults.grouping
	},
	/**
	* @description The number of repetitions, similar to badge, is used as the initial number when used with `grouping`
	*/
	repeatNum: {
		type: Number,
		default: messageDefaults.repeatNum
	}
});
const messageEmits = { destroy: () => true };

//#region ../../packages/components/message/src/instance.ts
const placementInstances = shallowReactive({});
const getOrCreatePlacementInstances = (placement) => {
	if (!placementInstances[placement]) placementInstances[placement] = shallowReactive([]);
	return placementInstances[placement];
};
const getInstance = (id, placement) => {
	const instances = placementInstances[placement] || [];
	const idx = instances.findIndex((instance) => instance.id === id);
	const current = instances[idx];
	let prev;
	if (idx > 0) prev = instances[idx - 1];
	return {
		current,
		prev
	};
};
const getLastOffset = (id, placement) => {
	const { prev } = getInstance(id, placement);
	if (!prev) return 0;
	return prev.vm.exposed.bottom.value;
};
const getOffsetOrSpace = (id, offset, placement) => {
	return (placementInstances[placement] || []).findIndex((instance) => instance.id === id) > 0 ? 16 : offset;
};

//#region ../../packages/components/message/src/message.vue?vue&type=script&setup=true&lang.ts
const _hoisted_1 = ["id"];
const _hoisted_2 = ["innerHTML"];
var message_vue_vue_type_script_setup_true_lang_default = /*@__PURE__*/ defineComponent({
	name: "ElMessage",
	__name: "message",
	props: messageProps,
	emits: messageEmits,
	setup(__props, { expose: __expose, emit: __emit }) {
		const { Close } = TypeComponents;
		const props = __props;
		const emit = __emit;
		const isStartTransition = ref(false);
		const { ns, zIndex } = useGlobalComponentSettings("message");
		const { currentZIndex, nextZIndex } = zIndex;
		const messageRef = ref();
		const visible = ref(false);
		const height = ref(0);
		let stopTimer = void 0;
		const badgeType = computed(() => props.type ? props.type === "error" ? "danger" : props.type : "info");
		const typeClass = computed(() => {
			const type = props.type;
			return { [ns.bm("icon", type)]: type && TypeComponentsMap[type] };
		});
		const iconComponent = computed(() => props.icon || TypeComponentsMap[props.type] || "");
		const placement = computed(() => props.placement || "top");
		const lastOffset = computed(() => getLastOffset(props.id, placement.value));
		const offset = computed(() => {
			return Math.max(getOffsetOrSpace(props.id, props.offset, placement.value) + lastOffset.value, props.offset);
		});
		const bottom = computed(() => height.value + offset.value);
		const horizontalClass = computed(() => {
			if (placement.value.includes("left")) return ns.is("left");
			if (placement.value.includes("right")) return ns.is("right");
			return ns.is("center");
		});
		const verticalProperty = computed(() => placement.value.startsWith("top") ? "top" : "bottom");
		const customStyle = computed(() => ({
			[verticalProperty.value]: `${offset.value}px`,
			zIndex: currentZIndex.value
		}));
		function startTimer() {
			if (props.duration === 0) return;
			({stop: stopTimer} = useTimeoutFn(() => {
				close();
			}, props.duration));
		}
		function clearTimer() {
			stopTimer?.();
		}
		function close() {
			visible.value = false;
			nextTick(() => {
				if (!isStartTransition.value) {
					props.onClose?.();
					emit("destroy");
				}
			});
		}
		function keydown(event) {
			if (getEventCode(event) === EVENT_CODE.esc) close();
		}
		onMounted(() => {
			startTimer();
			nextZIndex();
			visible.value = true;
		});
		watch(() => props.repeatNum, () => {
			clearTimer();
			startTimer();
		});
		useEventListener(document, "keydown", keydown);
		useResizeObserver(messageRef, () => {
			height.value = messageRef.value.getBoundingClientRect().height;
		});
		__expose({
			visible,
			bottom,
			close
		});
		return (_ctx, _cache) => {
			return openBlock(), createBlock(Transition, {
				name: unref(ns).b("fade"),
				onBeforeEnter: _cache[0] || (_cache[0] = ($event) => isStartTransition.value = true),
				onBeforeLeave: __props.onClose,
				onAfterLeave: _cache[1] || (_cache[1] = ($event) => _ctx.$emit("destroy")),
				persisted: ""
			}, {
				default: withCtx(() => [withDirectives(createBaseVNode("div", {
					id: __props.id,
					ref_key: "messageRef",
					ref: messageRef,
					class: normalizeClass([
						unref(ns).b(),
						{ [unref(ns).m(__props.type)]: __props.type },
						unref(ns).is("closable", __props.showClose),
						unref(ns).is("plain", __props.plain),
						unref(ns).is("bottom", verticalProperty.value === "bottom"),
						horizontalClass.value,
						__props.customClass
					]),
					style: normalizeStyle(customStyle.value),
					role: "alert",
					onMouseenter: clearTimer,
					onMouseleave: startTimer
				}, [
					__props.repeatNum > 1 ? (openBlock(), createBlock(unref(ElBadge), {
						key: 0,
						value: __props.repeatNum,
						type: badgeType.value,
						class: normalizeClass(unref(ns).e("badge"))
					}, null, 8, [
						"value",
						"type",
						"class"
					])) : createCommentVNode("v-if", true),
					iconComponent.value ? (openBlock(), createBlock(unref(ElIcon), {
						key: 1,
						class: normalizeClass([unref(ns).e("icon"), typeClass.value])
					}, {
						default: withCtx(() => [(openBlock(), createBlock(resolveDynamicComponent(iconComponent.value)))]),
						_: 1
					}, 8, ["class"])) : createCommentVNode("v-if", true),
					!__props.dangerouslyUseHTMLString || _ctx.$slots.default ? (openBlock(), createElementBlock("p", {
						key: 2,
						class: normalizeClass(unref(ns).e("content"))
					}, [renderSlot(_ctx.$slots, "default", {}, () => [createTextVNode(toDisplayString(__props.message), 1)])], 2)) : (openBlock(), createElementBlock(Fragment, { key: 3 }, [createCommentVNode(" Caution here, message could've been compromised, never use user's input as message "), createBaseVNode("p", {
						class: normalizeClass(unref(ns).e("content")),
						innerHTML: __props.message
					}, null, 10, _hoisted_2)], 2112)),
					__props.showClose ? (openBlock(), createBlock(unref(ElIcon), {
						key: 4,
						class: normalizeClass(unref(ns).e("closeBtn")),
						onClick: withModifiers(close, ["stop"])
					}, {
						default: withCtx(() => [createVNode(unref(Close))]),
						_: 1
					}, 8, ["class"])) : createCommentVNode("v-if", true)
				], 46, _hoisted_1), [[vShow, visible.value]])]),
				_: 3
			}, 8, ["name", "onBeforeLeave"]);
		};
	}
});

//#region ../../packages/components/message/src/message.vue
var message_default = message_vue_vue_type_script_setup_true_lang_default;

//#region ../../packages/components/message/src/method.ts
let seed = 1;
const normalizeAppendTo = (normalized) => {
	if (!normalized.appendTo) normalized.appendTo = document.body;
	else if (isString(normalized.appendTo)) {
		let appendTo = document.querySelector(normalized.appendTo);
		if (!isElement(appendTo)) {
			debugWarn("ElMessage", "the appendTo option is not an HTMLElement. Falling back to document.body.");
			appendTo = document.body;
		}
		normalized.appendTo = appendTo;
	}
};
const normalizePlacement = (normalized) => {
	if (!normalized.placement && isString(messageConfig.placement) && messageConfig.placement) normalized.placement = messageConfig.placement;
	if (!normalized.placement) normalized.placement = "top";
	if (!messagePlacement.includes(normalized.placement)) {
		debugWarn("ElMessage", `Invalid placement: ${normalized.placement}. Falling back to 'top'.`);
		normalized.placement = "top";
	}
};
const normalizeOptions = (params) => {
	const options = !params || isString(params) || isVNode(params) || isFunction(params) ? { message: params } : params;
	const normalized = {
		...messageDefaults,
		...options
	};
	normalizeAppendTo(normalized);
	normalizePlacement(normalized);
	if (isBoolean(messageConfig.grouping) && !normalized.grouping) normalized.grouping = messageConfig.grouping;
	if (isNumber(messageConfig.duration) && normalized.duration === 3e3) normalized.duration = messageConfig.duration;
	if (isNumber(messageConfig.offset) && normalized.offset === 16) normalized.offset = messageConfig.offset;
	if (isBoolean(messageConfig.showClose) && !normalized.showClose) normalized.showClose = messageConfig.showClose;
	if (isBoolean(messageConfig.plain) && !normalized.plain) normalized.plain = messageConfig.plain;
	return normalized;
};
const closeMessage = (instance) => {
	const placement = instance.props.placement || "top";
	const instances = placementInstances[placement];
	const idx = instances.indexOf(instance);
	if (idx === -1) return;
	instances.splice(idx, 1);
	const { handler } = instance;
	handler.close();
};
const createMessage = ({ appendTo, ...options }, context) => {
	const id = `message_${seed++}`;
	const userOnClose = options.onClose;
	const container = document.createElement("div");
	const props = {
		...options,
		id,
		onClose: () => {
			userOnClose?.();
			closeMessage(instance);
		},
		onDestroy: () => {
			render(null, container);
		}
	};
	const vnode = createVNode(message_default, props, isFunction(props.message) || isVNode(props.message) ? { default: isFunction(props.message) ? props.message : () => props.message } : null);
	vnode.appContext = context || message._context;
	render(vnode, container);
	appendTo.appendChild(container.firstElementChild);
	const vm = vnode.component;
	const instance = {
		id,
		vnode,
		vm,
		handler: { close: () => {
			vm.exposed.close();
		} },
		props: vnode.component.props
	};
	return instance;
};
const message = (options = {}, context) => {
	if (!isClient) return { close: () => void 0 };
	const normalized = normalizeOptions(options);
	const instances = getOrCreatePlacementInstances(normalized.placement || "top");
	if (normalized.grouping && instances.length) {
		const instance = instances.find(({ vnode: vm }) => vm.props?.message === normalized.message);
		if (instance) {
			instance.props.repeatNum += 1;
			instance.props.type = normalized.type;
			return instance.handler;
		}
	}
	if (isNumber(messageConfig.max) && instances.length >= messageConfig.max) return { close: () => void 0 };
	const instance = createMessage(normalized, context);
	instances.push(instance);
	return instance.handler;
};
messageTypes.forEach((type) => {
	message[type] = (options = {}, appContext) => {
		const normalized = normalizeOptions(options);
		return message({
			...normalized,
			type
		}, appContext);
	};
});
function closeAll(type) {
	for (const placement in placementInstances) if (hasOwn(placementInstances, placement)) {
		const instances = [...placementInstances[placement]];
		for (const instance of instances) if (!type || type === instance.props.type) instance.handler.close();
	}
}
function closeAllByPlacement(placement) {
	if (!placementInstances[placement]) return;
	[...placementInstances[placement]].forEach((instance) => instance.handler.close());
}
message.closeAll = closeAll;
message.closeAllByPlacement = closeAllByPlacement;
message._context = null;

//#region ../../packages/components/message/index.ts
const ElMessage = withInstallFunction(message, "$message");

export { ElMessage as E };
