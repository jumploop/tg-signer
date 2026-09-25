<template>
  <el-card shadow="never">
    <div class="row">
      <el-input
        v-model="filterText"
        placeholder="按任务名过滤"
        style="width: 240px"
        clearable
      />
      <el-button @click="refresh">刷新</el-button>
    </div>
    <el-table :data="filtered">
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
    </el-table>
  </el-card>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'

const records = ref([])
const filterText = ref('')
const filtered = computed(() =>
  records.value.filter((record) => !filterText.value || record.task.includes(filterText.value))
)

async function refresh() {
  const { data } = await api.get('/api/records')
  records.value = data
}

onMounted(refresh)
</script>

