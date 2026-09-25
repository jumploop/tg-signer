<template>
  <el-card shadow="never" class="records-card">
    <div class="records-intro">
      <div>
        <span class="section-label">签到历史</span>
        <p class="section-caption">按任务查看签到日期、执行时间和历史记录数量。</p>
      </div>
      <el-button :loading="loading" @click="refresh">刷新</el-button>
    </div>
    <div class="record-metrics">
      <div class="record-metric">
        <span class="metric-value">{{ records.length }}</span>
        <span class="metric-label">任务数</span>
      </div>
      <div class="record-metric">
        <span class="metric-value">{{ totalRecords }}</span>
        <span class="metric-label">签到记录</span>
      </div>
      <div class="record-filter">
      <el-input
        v-model="filterText"
        placeholder="按任务名过滤"
        clearable
      />
      </div>
    </div>
    <div class="table-heading">
      <span>任务记录</span>
      <span class="table-heading__meta">当前显示 {{ filtered.length }} 个任务</span>
    </div>
    <el-table v-loading="loading" :data="filtered" class="records-table">
      <el-table-column prop="task" label="任务" />
      <el-table-column prop="user_id" label="User ID" width="140" />
      <el-table-column label="记录数" width="100">
        <template #default="{ row }">{{ row.records.length }}</template>
      </el-table-column>
      <el-table-column label="最近签到" width="200">
        <template #default="{ row }">
          <template v-if="row.records.length">
            {{ row.records[row.records.length - 1].sign_date }}
            {{ row.records[row.records.length - 1].signed_at }}
          </template>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="记录" min-width="280">
        <template #default="{ row }">
          <div v-for="record in row.records" :key="record.sign_date" class="rec">
            <code>{{ record.sign_date }}</code> → {{ record.signed_at }}
          </div>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无签到记录，运行签到任务后在此查看" :image-size="60" />
      </template>
    </el-table>
  </el-card>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api, { asArray } from '../api'

const records = ref([])
const filterText = ref('')
const loading = ref(false)
const filtered = computed(() =>
  records.value.filter((record) => !filterText.value || record.task.includes(filterText.value))
)
const totalRecords = computed(() =>
  records.value.reduce((sum, record) => sum + record.records.length, 0)
)

async function refresh() {
  loading.value = true
  try {
    const { data } = await api.get('/api/records')
    records.value = asArray(data)
  } catch (error) {
    ElMessage.error('签到记录加载失败: ' + errMsg(error))
  } finally {
    loading.value = false
  }
}

function errMsg(error) {
  return (
    (error.response && error.response.data && error.response.data.detail) ||
    error.message
  )
}

onMounted(refresh)
</script>

<style scoped>
.records-intro,
.table-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}
.records-intro {
  margin-bottom: 20px;
}
.section-label {
  display: block;
  margin-bottom: 5px;
  color: var(--ts-ink);
  font-size: 16px;
  font-weight: 700;
}
.section-caption {
  margin: 0;
  color: var(--ts-muted);
  font-size: 13px;
}
.record-metrics {
  display: grid;
  grid-template-columns: 150px 150px minmax(220px, 1fr);
  gap: 12px;
  margin-bottom: 24px;
}
.record-metric,
.record-filter {
  min-height: 68px;
  padding: 13px 15px;
  border: 1px solid var(--ts-line);
  border-radius: 12px;
  background: #FAFCFF;
}
.record-metric {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
}
.metric-value {
  color: var(--ts-ink);
  font-size: 22px;
  font-weight: 750;
  line-height: 1;
}
.metric-label {
  color: var(--ts-muted);
  font-size: 12px;
}
.record-filter {
  display: flex;
  align-items: center;
}
.record-filter :deep(.el-input) {
  width: 100%;
}
.table-heading {
  margin-bottom: 12px;
  color: var(--ts-ink);
  font-size: 14px;
  font-weight: 700;
}
.table-heading__meta {
  color: var(--ts-muted);
  font-size: 12px;
  font-weight: 400;
}

@media (max-width: 700px) {
  .record-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .record-filter {
    grid-column: 1 / -1;
  }
}

@media (max-width: 600px) {
  .records-intro,
  .table-heading {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
