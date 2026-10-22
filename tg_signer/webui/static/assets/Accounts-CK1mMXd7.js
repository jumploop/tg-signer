import { _ as _export_sfc, o as onMounted, n as createBlock, w as withCtx, q as api, R as asArray, E as ElMessage, j as errMsg, r as resolveComponent, g as ref, N as resolveDirective, h as openBlock, b as createBaseVNode, d as createVNode, f as createTextVNode, J as toDisplayString, O as withDirectives, a as createElementBlock, P as Fragment, Q as renderList, G as createCommentVNode, i as unref, V as info_filled_default, e as withKeys, L as computed, S as ElMessageBox, W as nextTick } from './index-COQHa1_g.js';

const _hoisted_1 = { class: "ts-intro" };
const _hoisted_2 = { class: "account-metrics" };
const _hoisted_3 = { class: "account-metric" };
const _hoisted_4 = { class: "ts-metric-value" };
const _hoisted_5 = { class: "account-metric" };
const _hoisted_6 = { class: "ts-metric-value" };
const _hoisted_7 = {
  key: 0,
  class: "hint"
};
const _hoisted_8 = { class: "session-file" };
const _hoisted_9 = { class: "ts-callout dialog-callout" };
const _hoisted_10 = {
  class: "hint",
  style: {"margin-left":"8px"}
};
const _hoisted_11 = {
  class: "hint",
  style: {"margin-left":"8px"}
};


const _sfc_main = {
  __name: 'Accounts',
  setup(__props) {

const accounts = ref([]);
const loading = ref(false);
const sessionCount = computed(() =>
  accounts.value.filter((account) => account.kind && account.kind.length).length
);
const loginVisible = ref(false);
const loginAccount = ref('');
const phone = ref('');
const code = ref('');
const password = ref('');
const loginStatus = ref('');
const sending = ref(false);
const completing = ref(false);
const codeSent = ref(false);
const loginStep = ref(0);
const codeInput = ref(null);

async function refresh() {
  loading.value = true;
  try {
    const { data } = await api.get('/api/accounts');
    accounts.value = asArray(data);
  } catch (error) {
    ElMessage.error('账号列表加载失败: ' + errMsg(error));
  } finally {
    loading.value = false;
  }
}

function openLogin() {
  loginAccount.value = '';
  phone.value = '';
  code.value = '';
  password.value = '';
  loginStatus.value = '';
  codeSent.value = false;
  loginStep.value = 0;
  loginVisible.value = true;
}

async function sendCode() {
  if (!loginAccount.value.trim() || !phone.value.trim()) {
    ElMessage.warning('请填写账号名与手机号');
    return
  }
  sending.value = true;
  try {
    const { data } = await api.post('/api/accounts/send-code', {
      account: loginAccount.value.trim(),
      phone: phone.value.trim(),
    });
    loginStatus.value = data.message;
    if (data.result === 'error') {
      ElMessage.error(data.message);
    } else {
      ElMessage.success(data.message);
      codeSent.value = true;
      loginStep.value = 1;
      nextTick(() => {
        codeInput.value && codeInput.value.focus();
      });
    }
  } catch (error) {
    ElMessage.error(errMsg(error));
  } finally {
    sending.value = false;
  }
}

async function complete() {
  if (!code.value.trim()) {
    ElMessage.warning('请填写验证码');
    return
  }
  completing.value = true;
  try {
    const { data } = await api.post('/api/accounts/complete-login', {
      account: loginAccount.value.trim(),
      code: code.value.trim(),
      password: password.value.trim() || null,
    });
    loginStatus.value = data.message;
    if (data.result === 'password_needed') {
      ElMessage.info('需要两步验证密码，请填写后再次点击完成登录');
    } else if (data.result === 'ok') {
      ElMessage.success('登录成功');
      loginVisible.value = false;
      refresh();
    } else {
      ElMessage.error(data.message);
    }
  } catch (error) {
    ElMessage.error(errMsg(error));
  } finally {
    completing.value = false;
  }
}

async function check(accountName) {
  const { data } = await api.get(
    `/api/accounts/${encodeURIComponent(accountName)}/authorized`
  );
  ElMessage[data.ok ? 'success' : 'warning'](data.message);
}

async function doLogout(accountName) {
  try {
    await ElMessageBox.confirm(
      `确认登出并删除 ${accountName} 的 Session 文件？`,
      '提示',
      { type: 'warning' }
    );
  } catch (error) {
    return
  }
  try {
    const { data } = await api.post('/api/accounts/logout', {
      account: accountName,
    });
    ElMessage.success(data.message);
    refresh();
  } catch (error) {
    ElMessage.error(errMsg(error));
  }
}

onMounted(refresh);

return (_ctx, _cache) => {
  const _component_el_button = resolveComponent("el-button");
  const _component_el_table_column = resolveComponent("el-table-column");
  const _component_el_tag = resolveComponent("el-tag");
  const _component_el_empty = resolveComponent("el-empty");
  const _component_el_table = resolveComponent("el-table");
  const _component_el_step = resolveComponent("el-step");
  const _component_el_steps = resolveComponent("el-steps");
  const _component_el_icon = resolveComponent("el-icon");
  const _component_el_input = resolveComponent("el-input");
  const _component_el_form_item = resolveComponent("el-form-item");
  const _component_el_form = resolveComponent("el-form");
  const _component_el_dialog = resolveComponent("el-dialog");
  const _component_el_card = resolveComponent("el-card");
  const _directive_loading = resolveDirective("loading");

  return (openBlock(), createBlock(_component_el_card, { shadow: "never" }, {
    default: withCtx(() => [
      createBaseVNode("div", _hoisted_1, [
        _cache[6] || (_cache[6] = createBaseVNode("div", null, [
          createBaseVNode("span", { class: "ts-section-label" }, "账号会话"),
          createBaseVNode("p", { class: "ts-section-caption" }, "管理已登录的 Telegram 会话，检查授权状态或添加新账号。")
        ], -1)),
        createVNode(_component_el_button, {
          type: "primary",
          onClick: openLogin
        }, {
          default: withCtx(() => [...(_cache[5] || (_cache[5] = [
            createTextVNode("登录新账号", -1)
          ]))]),
          _: 1
        })
      ]),
      createBaseVNode("div", _hoisted_2, [
        createBaseVNode("div", _hoisted_3, [
          createBaseVNode("span", _hoisted_4, toDisplayString(accounts.value.length), 1),
          _cache[7] || (_cache[7] = createBaseVNode("span", { class: "ts-metric-label" }, "已发现账号", -1))
        ]),
        createBaseVNode("div", _hoisted_5, [
          createBaseVNode("span", _hoisted_6, toDisplayString(sessionCount.value), 1),
          _cache[8] || (_cache[8] = createBaseVNode("span", { class: "ts-metric-label" }, "可用会话", -1))
        ]),
        _cache[9] || (_cache[9] = createBaseVNode("div", { class: "account-metric" }, [
          createBaseVNode("span", { class: "ts-metric-value ts-metric-value--muted" }, "本地"),
          createBaseVNode("span", { class: "ts-metric-label" }, "凭据存储")
        ], -1))
      ]),
      withDirectives((openBlock(), createBlock(_component_el_table, { data: accounts.value }, {
        empty: withCtx(() => [
          createVNode(_component_el_empty, {
            description: "暂无账号，点击「登录新账号」开始",
            "image-size": 60
          })
        ]),
        default: withCtx(() => [
          createVNode(_component_el_table_column, {
            prop: "account",
            label: "账号",
            "min-width": "140"
          }),
          createVNode(_component_el_table_column, {
            label: "会话类型",
            width: "240"
          }, {
            default: withCtx(({ row }) => [
              (openBlock(true), createElementBlock(Fragment, null, renderList(row.kind, (k) => {
                return (openBlock(), createBlock(_component_el_tag, {
                  key: k,
                  size: "small",
                  class: "kind-tag",
                  type: k === 'session' ? 'success' : 'warning'
                }, {
                  default: withCtx(() => [
                    createTextVNode(toDisplayString(k === 'session' ? 'Session 文件' : 'Session String'), 1)
                  ]),
                  _: 2
                }, 1032, ["type"]))
              }), 128)),
              (!row.kind || !row.kind.length)
                ? (openBlock(), createElementBlock("span", _hoisted_7, "未知"))
                : createCommentVNode("", true)
            ]),
            _: 1
          }),
          createVNode(_component_el_table_column, {
            label: "Session 文件",
            "min-width": "200",
            "show-overflow-tooltip": ""
          }, {
            default: withCtx(({ row }) => [
              createBaseVNode("span", _hoisted_8, toDisplayString(row.session_file ? row.session_file.split(/[\\/]/).pop() : '—'), 1)
            ]),
            _: 1
          }),
          createVNode(_component_el_table_column, {
            label: "操作",
            width: "220"
          }, {
            default: withCtx(({ row }) => [
              createVNode(_component_el_button, {
                size: "small",
                onClick: $event => (check(row.account))
              }, {
                default: withCtx(() => [...(_cache[10] || (_cache[10] = [
                  createTextVNode("检查", -1)
                ]))]),
                _: 1
              }, 8, ["onClick"]),
              createVNode(_component_el_button, {
                size: "small",
                type: "danger",
                plain: "",
                onClick: $event => (doLogout(row.account))
              }, {
                default: withCtx(() => [...(_cache[11] || (_cache[11] = [
                  createTextVNode(" 登出并删除 ", -1)
                ]))]),
                _: 1
              }, 8, ["onClick"])
            ]),
            _: 1
          })
        ]),
        _: 1
      }, 8, ["data"])), [
        [_directive_loading, loading.value]
      ]),
      createVNode(_component_el_dialog, {
        modelValue: loginVisible.value,
        "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((loginVisible).value = $event)),
        title: "登录 Telegram 账号",
        width: "480px",
        "close-on-click-modal": false
      }, {
        default: withCtx(() => [
          createVNode(_component_el_steps, {
            active: loginStep.value,
            "finish-status": "success",
            simple: "",
            style: {"margin-bottom":"16px"}
          }, {
            default: withCtx(() => [
              createVNode(_component_el_step, { title: "发送验证码" }),
              createVNode(_component_el_step, { title: "完成登录" })
            ]),
            _: 1
          }, 8, ["active"]),
          createBaseVNode("div", _hoisted_9, [
            createVNode(_component_el_icon, null, {
              default: withCtx(() => [
                createVNode(unref(info_filled_default))
              ]),
              _: 1
            }),
            _cache[12] || (_cache[12] = createBaseVNode("span", null, "验证码会发送到 Telegram 对话，请保持账号可接收消息。", -1))
          ]),
          createVNode(_component_el_form, { "label-width": "90px" }, {
            default: withCtx(() => [
              createVNode(_component_el_form_item, { label: "账号名" }, {
                default: withCtx(() => [
                  createVNode(_component_el_input, {
                    modelValue: loginAccount.value,
                    "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((loginAccount).value = $event)),
                    placeholder: "例如 my_account，对应 session 文件名"
                  }, null, 8, ["modelValue"])
                ]),
                _: 1
              }),
              createVNode(_component_el_form_item, { label: "手机号" }, {
                default: withCtx(() => [
                  createVNode(_component_el_input, {
                    modelValue: phone.value,
                    "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((phone).value = $event)),
                    placeholder: "+8613800138000",
                    onKeyup: withKeys(sendCode, ["enter"])
                  }, null, 8, ["modelValue"])
                ]),
                _: 1
              }),
              createVNode(_component_el_form_item, null, {
                default: withCtx(() => [
                  createVNode(_component_el_button, {
                    loading: sending.value,
                    onClick: sendCode
                  }, {
                    default: withCtx(() => [...(_cache[13] || (_cache[13] = [
                      createTextVNode("发送验证码", -1)
                    ]))]),
                    _: 1
                  }, 8, ["loading"]),
                  createBaseVNode("span", _hoisted_10, toDisplayString(codeSent.value ? '验证码已发送，请查收 Telegram' : '发送成功后输入验证码并完成登录'), 1)
                ]),
                _: 1
              }),
              createVNode(_component_el_form_item, { label: "验证码" }, {
                default: withCtx(() => [
                  createVNode(_component_el_input, {
                    ref_key: "codeInput",
                    ref: codeInput,
                    modelValue: code.value,
                    "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((code).value = $event)),
                    disabled: !codeSent.value,
                    placeholder: "Telegram 下发的登录验证码",
                    onKeyup: withKeys(complete, ["enter"])
                  }, null, 8, ["modelValue", "disabled"])
                ]),
                _: 1
              }),
              createVNode(_component_el_form_item, { label: "两步密码" }, {
                default: withCtx(() => [
                  createVNode(_component_el_input, {
                    modelValue: password.value,
                    "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((password).value = $event)),
                    type: "password",
                    "show-password": "",
                    placeholder: "如启用两步验证再填",
                    onKeyup: withKeys(complete, ["enter"])
                  }, null, 8, ["modelValue"])
                ]),
                _: 1
              }),
              createVNode(_component_el_form_item, null, {
                default: withCtx(() => [
                  createVNode(_component_el_button, {
                    type: "primary",
                    loading: completing.value,
                    disabled: !codeSent.value,
                    onClick: complete
                  }, {
                    default: withCtx(() => [...(_cache[14] || (_cache[14] = [
                      createTextVNode("完成登录", -1)
                    ]))]),
                    _: 1
                  }, 8, ["loading", "disabled"]),
                  createBaseVNode("span", _hoisted_11, toDisplayString(loginStatus.value), 1)
                ]),
                _: 1
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      }, 8, ["modelValue"])
    ]),
    _: 1
  }))
}
}

};
const Accounts = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-31c39390"]]);

export { Accounts as default };
