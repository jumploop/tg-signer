<template>
  <router-view />
</template>

<style>
html, body, #app {
  margin: 0;
  height: 100%;
}
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',
    'Microsoft YaHei', sans-serif;
  background: #f5f7fa;
}
.row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.hint {
  font-size: 12px;
  color: #888;
}
.mono {
  font-family: 'SFMono-Regular', Consolas, 'Courier New', monospace;
  font-size: 12px;
}
.logbox textarea {
  background: #1e1e1e;
  color: #d4d4d4;
}
.rec {
  font-size: 12px;
  line-height: 1.6;
}
</style>
