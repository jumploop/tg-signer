<template>
  <router-view />
</template>

<style>
#app {
  height: 100%;
}
.hint {
  font-size: 13px;
  line-height: 1.6;
  color: var(--ts-muted);
}
.mono {
  font-family: var(--el-font-family-mono);
  font-size: 12px;
  line-height: 1.65;
}
.logbox textarea {
  background: #101827;
  color: #D7E2F0;
  line-height: 1.65;
  padding: 18px;
}
.rec {
  font-size: 12px;
  line-height: 1.6;
}

.el-card__body {
  padding: 24px;
}

.el-table {
  font-size: 13px;
}

@media (max-width: 720px) {
  .el-card__body {
    padding: 16px;
  }

  .el-table {
    font-size: 12px;
  }
}
</style>
