import { _ as _export_sfc, o as onMounted, n as createBlock, w as withCtx, W as useList, r as resolveComponent, N as resolveDirective, h as openBlock, b as createBaseVNode, d as createVNode, i as unref, f as createTextVNode, V as info_filled_default, J as toDisplayString, O as withDirectives, g as ref, L as computed } from './index-DAjis5_u.js';

const _hoisted_1 = { class: "ts-intro" };
const _hoisted_2 = { class: "ts-callout users-note" };
const _hoisted_3 = { class: "ts-table-heading" };
const _hoisted_4 = { class: "ts-table-heading__meta" };
const _hoisted_5 = { class: "user-cell" };
const _hoisted_6 = { class: "user-avatar" };


const _sfc_main = {
  __name: 'Users',
  setup(__props) {

const {
  list: users,
  loading,
  refresh,
} = useList('/api/users', '用户信息加载失败');
const dialogVisible = ref(false);
const currentUser = ref(null);
const currentChats = computed(() => currentUser.value?.latest_chats || []);

onMounted(refresh);

function showChats(row) {
  currentUser.value = row;
  dialogVisible.value = true;
}

function userInitial(row) {
  const name = row.data.first_name || row.data.username || String(row.user_id);
  return name.slice(0, 1).toUpperCase()
}

return (_ctx, _cache) => {
  const _component_el_button = resolveComponent("el-button");
  const _component_el_icon = resolveComponent("el-icon");
  const _component_el_table_column = resolveComponent("el-table-column");
  const _component_el_tag = resolveComponent("el-tag");
  const _component_el_empty = resolveComponent("el-empty");
  const _component_el_table = resolveComponent("el-table");
  const _component_el_dialog = resolveComponent("el-dialog");
  const _component_el_card = resolveComponent("el-card");
  const _directive_loading = resolveDirective("loading");

  return (openBlock(), createBlock(_component_el_card, { shadow: "never" }, {
    default: withCtx(() => [
      createBaseVNode("div", _hoisted_1, [
        _cache[2] || (_cache[2] = createBaseVNode("div", null, [
          createBaseVNode("span", { class: "ts-section-label" }, "用户信息"),
          createBaseVNode("p", { class: "ts-section-caption" }, "查看本地缓存的账户资料与最近对话，不触发 Telegram 网络请求。")
        ], -1)),
        createVNode(_component_el_button, {
          loading: unref(loading),
          onClick: unref(refresh)
        }, {
          default: withCtx(() => [...(_cache[1] || (_cache[1] = [
            createTextVNode("刷新", -1)
          ]))]),
          _: 1
        }, 8, ["loading", "onClick"])
      ]),
      createBaseVNode("div", _hoisted_2, [
        createVNode(_component_el_icon, null, {
          default: withCtx(() => [
            createVNode(unref(info_filled_default))
          ]),
          _: 1
        }),
        _cache[3] || (_cache[3] = createBaseVNode("span", null, [
          createTextVNode("数据来源：当前工作目录下的 "),
          createBaseVNode("code", null, "users/*/me.json"),
          createTextVNode(" 与最近对话缓存。")
        ], -1))
      ]),
      createBaseVNode("div", _hoisted_3, [
        _cache[4] || (_cache[4] = createBaseVNode("span", null, "已缓存账户", -1)),
        createBaseVNode("span", _hoisted_4, toDisplayString(unref(users).length) + " 个账户", 1)
      ]),
      withDirectives((openBlock(), createBlock(_component_el_table, { data: unref(users) }, {
        empty: withCtx(() => [
          createVNode(_component_el_empty, {
            description: "暂无用户信息（读取 users/*/me.json）",
            "image-size": 60
          })
        ]),
        default: withCtx(() => [
          createVNode(_component_el_table_column, {
            prop: "user_id",
            label: "User ID",
            width: "140"
          }),
          createVNode(_component_el_table_column, { label: "名称" }, {
            default: withCtx(({ row }) => [
              createBaseVNode("div", _hoisted_5, [
                createBaseVNode("span", _hoisted_6, toDisplayString(userInitial(row)), 1),
                createBaseVNode("span", null, toDisplayString(row.data.first_name || row.data.username || '-'), 1)
              ])
            ]),
            _: 1
          }),
          createVNode(_component_el_table_column, {
            label: "最新对话数",
            width: "120"
          }, {
            default: withCtx(({ row }) => [
              createVNode(_component_el_tag, {
                size: "small",
                effect: "plain"
              }, {
                default: withCtx(() => [
                  createTextVNode(toDisplayString(row.latest_chats.length) + " 个", 1)
                ]),
                _: 2
              }, 1024)
            ]),
            _: 1
          }),
          createVNode(_component_el_table_column, {
            label: "操作",
            width: "120"
          }, {
            default: withCtx(({ row }) => [
              createVNode(_component_el_button, {
                size: "small",
                onClick: $event => (showChats(row))
              }, {
                default: withCtx(() => [...(_cache[5] || (_cache[5] = [
                  createTextVNode("查看对话", -1)
                ]))]),
                _: 1
              }, 8, ["onClick"])
            ]),
            _: 1
          })
        ]),
        _: 1
      }, 8, ["data"])), [
        [_directive_loading, unref(loading)]
      ]),
      createVNode(_component_el_dialog, {
        modelValue: dialogVisible.value,
        "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((dialogVisible).value = $event)),
        title: '对话列表 - ' + (currentUser.value?.data.first_name || currentUser.value?.user_id),
        width: "640px"
      }, {
        default: withCtx(() => [
          createVNode(_component_el_table, {
            data: currentChats.value,
            "max-height": "400"
          }, {
            default: withCtx(() => [
              createVNode(_component_el_table_column, {
                prop: "id",
                label: "ID",
                width: "140"
              }),
              createVNode(_component_el_table_column, {
                prop: "title",
                label: "标题"
              }),
              createVNode(_component_el_table_column, {
                prop: "type",
                label: "类型",
                width: "120"
              }),
              createVNode(_component_el_table_column, {
                prop: "username",
                label: "用户名"
              })
            ]),
            _: 1
          }, 8, ["data"])
        ]),
        _: 1
      }, 8, ["modelValue", "title"])
    ]),
    _: 1
  }))
}
}

};
const Users = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-763cb295"]]);

export { Users as default };
