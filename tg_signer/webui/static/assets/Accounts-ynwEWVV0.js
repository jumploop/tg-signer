import { _ as _export_sfc, m as watch, o as onMounted, k as onUnmounted, n as createBlock, w as withCtx, W as useList, r as resolveComponent, N as resolveDirective, h as openBlock, b as createBaseVNode, d as createVNode, f as createTextVNode, J as toDisplayString, i as unref, O as withDirectives, a as createElementBlock, P as Fragment, Q as renderList, G as createCommentVNode, V as info_filled_default, e as withKeys, L as computed, q as api, E as ElMessage, S as ElMessageBox, j as errMsg, g as ref, X as nextTick } from './index-BOwYlRhP.js';

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
  key: 0,
  class: "hint",
  style: {"margin-left":"8px"}
};
const _hoisted_12 = {
  class: "hint",
  style: {"margin-left":"8px"}
};
const _hoisted_13 = { class: "ts-callout dialog-callout" };
const _hoisted_14 = {
  class: "hint",
  style: {"margin-left":"8px"}
};
const _hoisted_15 = {
  key: 0,
  class: "qr-box"
};
const _hoisted_16 = ["innerHTML"];
const _hoisted_17 = { class: "qr-meta" };
const _hoisted_18 = { class: "hint" };
const _hoisted_19 = {
  key: 1,
  class: "hint qr-fallback"
};


const _sfc_main = {
  __name: 'Accounts',
  setup(__props) {

const {
  list: accounts,
  loading,
  refresh,
} = useList('/api/accounts', '账号列表加载失败');
const sessionCount = computed(() =>
  accounts.value.filter((account) => account.kind && account.kind.length).length
);
const loginVisible = ref(false);
const loginMode = ref('code');
const loginAccount = ref('');
const phone = ref('');
const code = ref('');
const password = ref('');
const loginStatus = ref('');
const sending = ref(false);
const resending = ref(false);
const completing = ref(false);
const codeSent = ref(false);
const loginStep = ref(0);
const codeInput = ref(null);
const resendIn = ref(0);
const deliveryLabel = ref('');
const qrStarting = ref(false);
const qrSubmitting = ref(false);
const qrState = ref('idle');
const qrSvg = ref('');
const qrUrl = ref('');
const qrMessage = ref('');
const qrExpires = ref(0);
const qrHint = ref('生成后用手机 Telegram 扫码');
let resendTimer = null;
let qrTimer = null;

function stopResendTimer() {
  if (resendTimer) {
    clearInterval(resendTimer);
    resendTimer = null;
  }
}

function startResendCountdown(seconds) {
  stopResendTimer();
  resendIn.value = Math.max(0, Number(seconds) || 0);
  if (!resendIn.value) return
  resendTimer = setInterval(() => {
    resendIn.value -= 1;
    if (resendIn.value <= 0) {
      resendIn.value = 0;
      stopResendTimer();
    }
  }, 1000);
}

function openLogin() {
  loginAccount.value = '';
  phone.value = '';
  code.value = '';
  password.value = '';
  loginStatus.value = '';
  codeSent.value = false;
  loginStep.value = 0;
  resendIn.value = 0;
  deliveryLabel.value = '';
  loginMode.value = 'code';
  resetQr();
  stopResendTimer();
  loginVisible.value = true;
}

function resetQr() {
  stopQrPoll();
  qrState.value = 'idle';
  qrSvg.value = '';
  qrUrl.value = '';
  qrMessage.value = '';
  qrExpires.value = 0;
  qrHint.value = '生成后用手机 Telegram 扫码';
}

function stopQrPoll() {
  if (qrTimer) {
    clearInterval(qrTimer);
    qrTimer = null;
  }
}

function startQrPoll() {
  stopQrPoll();
  qrTimer = setInterval(pollQr, 2000);
}

function applyQr(data) {
  qrState.value = data.state || 'idle';
  qrSvg.value = data.svg || '';
  qrUrl.value = data.url || '';
  qrMessage.value = data.message || '';
  qrExpires.value = Number(data.expires_in) || 0;
  if (qrState.value === 'ok') {
    stopQrPoll();
    ElMessage.success(qrMessage.value || '登录成功');
    loginVisible.value = false;
    refresh();
  } else if (qrState.value === 'error') {
    stopQrPoll();
    qrHint.value = '生成失败';
    ElMessage.error(qrMessage.value || '二维码登录失败');
  } else if (qrState.value === 'idle') {
    stopQrPoll();
    qrHint.value = '登录会话已失效，请重新生成';
  }
}

async function pollQr() {
  const accountName = loginAccount.value.trim();
  if (!accountName) {
    stopQrPoll();
    return
  }
  try {
    const { data } = await api.get('/api/accounts/qr-status', {
      params: { account: accountName },
    });
    applyQr(data);
  } catch (error) {
    stopQrPoll();
    ElMessage.error(errMsg(error));
  }
}

async function startQr() {
  if (!loginAccount.value.trim()) {
    ElMessage.warning('请填写账号名');
    return
  }
  qrStarting.value = true;
  qrHint.value = '正在生成二维码…';
  try {
    const { data } = await api.post('/api/accounts/qr-start', {
      account: loginAccount.value.trim(),
    });
    if (data.result === 'ok') {
      qrHint.value = '等待扫码';
      applyQr(data);
      startQrPoll();
    } else {
      qrHint.value = '未生成二维码';
      ElMessage.warning(data.message);
    }
  } catch (error) {
    qrHint.value = '生成失败';
    ElMessage.error(errMsg(error));
  } finally {
    qrStarting.value = false;
  }
}

async function submitQrPassword() {
  if (!password.value.trim()) {
    ElMessage.warning('请填写两步验证密码');
    return
  }
  qrSubmitting.value = true;
  try {
    const { data } = await api.post('/api/accounts/qr-password', {
      account: loginAccount.value.trim(),
      password: password.value.trim(),
    });
    if (data.result === 'ok') {
      stopQrPoll();
      ElMessage.success(data.message || '登录成功');
      loginVisible.value = false;
      refresh();
    } else {
      ElMessage.error(data.message);
    }
  } catch (error) {
    ElMessage.error(errMsg(error));
  } finally {
    qrSubmitting.value = false;
  }
}

function onModeChange() {
  if (loginMode.value !== 'qr') {
    resetQr();
  }
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
    deliveryLabel.value = data.delivery_label || '';
    if (data.result === 'ok') {
      ElMessage.success(data.message);
      codeSent.value = true;
      loginStep.value = 1;
      startResendCountdown(data.resend_after);
      nextTick(() => {
        codeInput.value && codeInput.value.focus();
      });
    } else if (data.result === 'already') {
      codeSent.value = false;
      loginStep.value = 0;
      ElMessage.warning(data.message);
    } else {
      codeSent.value = false;
      loginStep.value = 0;
      ElMessage.error(data.message);
    }
  } catch (error) {
    ElMessage.error(errMsg(error));
  } finally {
    sending.value = false;
  }
}

async function resendCode() {
  if (resending.value || resendIn.value > 0) return
  resending.value = true;
  try {
    const { data } = await api.post('/api/accounts/resend-code', {
      account: loginAccount.value.trim(),
    });
    loginStatus.value = data.message;
    deliveryLabel.value = data.delivery_label || '';
    startResendCountdown(data.resend_after);
    if (data.result === 'ok') {
      ElMessage.success(data.message);
      codeSent.value = true;
      nextTick(() => {
        codeInput.value && codeInput.value.focus();
      });
    } else {
      ElMessage.error(data.message);
    }
  } catch (error) {
    ElMessage.error(errMsg(error));
  } finally {
    resending.value = false;
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

watch(loginVisible, (visible) => {
  if (!visible) {
    stopResendTimer();
    stopQrPoll();
  }
});

onMounted(refresh);
onUnmounted(() => {
  stopResendTimer();
  stopQrPoll();
});

return (_ctx, _cache) => {
  const _component_el_button = resolveComponent("el-button");
  const _component_el_table_column = resolveComponent("el-table-column");
  const _component_el_tag = resolveComponent("el-tag");
  const _component_el_empty = resolveComponent("el-empty");
  const _component_el_table = resolveComponent("el-table");
  const _component_el_radio_button = resolveComponent("el-radio-button");
  const _component_el_radio_group = resolveComponent("el-radio-group");
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
        _cache[9] || (_cache[9] = createBaseVNode("div", null, [
          createBaseVNode("span", { class: "ts-section-label" }, "账号会话"),
          createBaseVNode("p", { class: "ts-section-caption" }, "管理已登录的 Telegram 会话，检查授权状态或添加新账号。")
        ], -1)),
        createVNode(_component_el_button, {
          type: "primary",
          onClick: openLogin
        }, {
          default: withCtx(() => [...(_cache[8] || (_cache[8] = [
            createTextVNode("登录新账号", -1)
          ]))]),
          _: 1
        })
      ]),
      createBaseVNode("div", _hoisted_2, [
        createBaseVNode("div", _hoisted_3, [
          createBaseVNode("span", _hoisted_4, toDisplayString(unref(accounts).length), 1),
          _cache[10] || (_cache[10] = createBaseVNode("span", { class: "ts-metric-label" }, "已发现账号", -1))
        ]),
        createBaseVNode("div", _hoisted_5, [
          createBaseVNode("span", _hoisted_6, toDisplayString(sessionCount.value), 1),
          _cache[11] || (_cache[11] = createBaseVNode("span", { class: "ts-metric-label" }, "可用会话", -1))
        ]),
        _cache[12] || (_cache[12] = createBaseVNode("div", { class: "account-metric" }, [
          createBaseVNode("span", { class: "ts-metric-value ts-metric-value--muted" }, "本地"),
          createBaseVNode("span", { class: "ts-metric-label" }, "凭据存储")
        ], -1))
      ]),
      withDirectives((openBlock(), createBlock(_component_el_table, { data: unref(accounts) }, {
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
                default: withCtx(() => [...(_cache[13] || (_cache[13] = [
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
                default: withCtx(() => [...(_cache[14] || (_cache[14] = [
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
        [_directive_loading, unref(loading)]
      ]),
      createVNode(_component_el_dialog, {
        modelValue: loginVisible.value,
        "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((loginVisible).value = $event)),
        title: "登录 Telegram 账号",
        width: "480px",
        "close-on-click-modal": false
      }, {
        default: withCtx(() => [
          createVNode(_component_el_radio_group, {
            modelValue: loginMode.value,
            "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((loginMode).value = $event)),
            class: "login-mode",
            onChange: onModeChange
          }, {
            default: withCtx(() => [
              createVNode(_component_el_radio_button, { value: "code" }, {
                default: withCtx(() => [...(_cache[15] || (_cache[15] = [
                  createTextVNode("验证码登录", -1)
                ]))]),
                _: 1
              }),
              createVNode(_component_el_radio_button, { value: "qr" }, {
                default: withCtx(() => [...(_cache[16] || (_cache[16] = [
                  createTextVNode("二维码登录", -1)
                ]))]),
                _: 1
              })
            ]),
            _: 1
          }, 8, ["modelValue"]),
          (loginMode.value === 'code')
            ? (openBlock(), createElementBlock(Fragment, { key: 0 }, [
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
                  _cache[17] || (_cache[17] = createBaseVNode("span", null, " 验证码可能发送到已登录设备的 Telegram、短信或电话；未收到可点「重新发送」。 ", -1))
                ]),
                createVNode(_component_el_form, { "label-width": "90px" }, {
                  default: withCtx(() => [
                    createVNode(_component_el_form_item, { label: "账号名" }, {
                      default: withCtx(() => [
                        createVNode(_component_el_input, {
                          modelValue: loginAccount.value,
                          "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((loginAccount).value = $event)),
                          placeholder: "例如 my_account，对应 session 文件名"
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    }),
                    createVNode(_component_el_form_item, { label: "手机号" }, {
                      default: withCtx(() => [
                        createVNode(_component_el_input, {
                          modelValue: phone.value,
                          "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((phone).value = $event)),
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
                          default: withCtx(() => [...(_cache[18] || (_cache[18] = [
                            createTextVNode("发送验证码", -1)
                          ]))]),
                          _: 1
                        }, 8, ["loading"]),
                        createBaseVNode("span", _hoisted_10, toDisplayString(codeSent.value ? '验证码已发送，请按提示查收' : '发送成功后输入验证码并完成登录'), 1)
                      ]),
                      _: 1
                    }),
                    createVNode(_component_el_form_item, { label: "验证码" }, {
                      default: withCtx(() => [
                        createVNode(_component_el_input, {
                          ref_key: "codeInput",
                          ref: codeInput,
                          modelValue: code.value,
                          "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((code).value = $event)),
                          disabled: !codeSent.value,
                          placeholder: "Telegram 下发的登录验证码",
                          onKeyup: withKeys(complete, ["enter"])
                        }, null, 8, ["modelValue", "disabled"])
                      ]),
                      _: 1
                    }),
                    (codeSent.value)
                      ? (openBlock(), createBlock(_component_el_form_item, { key: 0 }, {
                          default: withCtx(() => [
                            createVNode(_component_el_button, {
                              text: "",
                              type: "primary",
                              loading: resending.value,
                              disabled: resendIn.value > 0,
                              onClick: resendCode
                            }, {
                              default: withCtx(() => [
                                createTextVNode(toDisplayString(resendIn.value > 0 ? `重新发送（${resendIn.value}s）` : '没收到？重新发送'), 1)
                              ]),
                              _: 1
                            }, 8, ["loading", "disabled"]),
                            (deliveryLabel.value)
                              ? (openBlock(), createElementBlock("span", _hoisted_11, " 本次通过" + toDisplayString(deliveryLabel.value) + "发送 ", 1))
                              : createCommentVNode("", true)
                          ]),
                          _: 1
                        }))
                      : createCommentVNode("", true),
                    createVNode(_component_el_form_item, { label: "两步密码" }, {
                      default: withCtx(() => [
                        createVNode(_component_el_input, {
                          modelValue: password.value,
                          "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((password).value = $event)),
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
                          default: withCtx(() => [...(_cache[19] || (_cache[19] = [
                            createTextVNode("完成登录", -1)
                          ]))]),
                          _: 1
                        }, 8, ["loading", "disabled"]),
                        createBaseVNode("span", _hoisted_12, toDisplayString(loginStatus.value), 1)
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                })
              ], 64))
            : (openBlock(), createElementBlock(Fragment, { key: 1 }, [
                createBaseVNode("div", _hoisted_13, [
                  createVNode(_component_el_icon, null, {
                    default: withCtx(() => [
                      createVNode(unref(info_filled_default))
                    ]),
                    _: 1
                  }),
                  _cache[20] || (_cache[20] = createBaseVNode("span", null, [
                    createTextVNode(" 用"),
                    createBaseVNode("strong", null, "已登录该账号"),
                    createTextVNode("的 Telegram 扫码即可登录，不需要短信或验证码。 手机端路径：设置 → 隐私和安全 → 设备 → 扫描二维码。 ")
                  ], -1))
                ]),
                createVNode(_component_el_form, { "label-width": "90px" }, {
                  default: withCtx(() => [
                    createVNode(_component_el_form_item, { label: "账号名" }, {
                      default: withCtx(() => [
                        createVNode(_component_el_input, {
                          modelValue: loginAccount.value,
                          "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((loginAccount).value = $event)),
                          placeholder: "例如 my_account，对应 session 文件名",
                          onKeyup: withKeys(startQr, ["enter"])
                        }, null, 8, ["modelValue"])
                      ]),
                      _: 1
                    }),
                    createVNode(_component_el_form_item, null, {
                      default: withCtx(() => [
                        createVNode(_component_el_button, {
                          type: "primary",
                          loading: qrStarting.value,
                          onClick: startQr
                        }, {
                          default: withCtx(() => [...(_cache[21] || (_cache[21] = [
                            createTextVNode(" 生成二维码 ", -1)
                          ]))]),
                          _: 1
                        }, 8, ["loading"]),
                        createBaseVNode("span", _hoisted_14, toDisplayString(qrHint.value), 1)
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                }),
                (qrSvg.value)
                  ? (openBlock(), createElementBlock("div", _hoisted_15, [
                      createBaseVNode("div", {
                        class: "qr-image",
                        innerHTML: qrSvg.value
                      }, null, 8, _hoisted_16),
                      createBaseVNode("div", _hoisted_17, [
                        createBaseVNode("p", null, toDisplayString(qrMessage.value), 1),
                        createBaseVNode("p", _hoisted_18, "二维码 " + toDisplayString(qrExpires.value) + " 秒后自动刷新，请尽快扫描", 1)
                      ])
                    ]))
                  : (qrUrl.value)
                    ? (openBlock(), createElementBlock("div", _hoisted_19, [
                        _cache[22] || (_cache[22] = createTextVNode(" 二维码渲染不可用，可在 Telegram 内打开： ", -1)),
                        createBaseVNode("code", null, toDisplayString(qrUrl.value), 1)
                      ]))
                    : createCommentVNode("", true),
                (qrState.value === 'password_needed')
                  ? (openBlock(), createBlock(_component_el_form, {
                      key: 2,
                      "label-width": "90px"
                    }, {
                      default: withCtx(() => [
                        createVNode(_component_el_form_item, { label: "两步密码" }, {
                          default: withCtx(() => [
                            createVNode(_component_el_input, {
                              modelValue: password.value,
                              "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((password).value = $event)),
                              type: "password",
                              "show-password": "",
                              placeholder: "该账号启用了两步验证",
                              onKeyup: withKeys(submitQrPassword, ["enter"])
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }),
                        createVNode(_component_el_form_item, null, {
                          default: withCtx(() => [
                            createVNode(_component_el_button, {
                              type: "primary",
                              loading: qrSubmitting.value,
                              onClick: submitQrPassword
                            }, {
                              default: withCtx(() => [...(_cache[23] || (_cache[23] = [
                                createTextVNode("完成登录", -1)
                              ]))]),
                              _: 1
                            }, 8, ["loading"])
                          ]),
                          _: 1
                        })
                      ]),
                      _: 1
                    }))
                  : createCommentVNode("", true)
              ], 64))
        ]),
        _: 1
      }, 8, ["modelValue"])
    ]),
    _: 1
  }))
}
}

};
const Accounts = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-cc5a66e6"]]);

export { Accounts as default };
