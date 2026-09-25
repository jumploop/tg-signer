<template>
  <router-view />
</template>

<style>
#app {
  height: 100%;
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
  color: var(--ts-muted);
}
.mono {
  font-family: var(--el-font-family-mono);
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
