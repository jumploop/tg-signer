<template>
  <el-card shadow="never">
    <div class="row">
      <span class="hint">已登录账户信息（读取 users/*/me.json）</span>
      <span style="flex: 1"></span>
      <el-button @click="refresh">刷新</el-button>
    </div>
    <el-table :data="users">
      <el-table-column prop="user_id" label="User ID" width="140" />
      <el-table-column label="名称">
        <template #default="{ row }">
          {{ row.data.first_name || row.data.username || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="最新对话数" width="120">
        <template #default="{ row }">{{ row.latest_chats.length }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button size="small" @click="showChats(row)">查看对话</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="dialogVisible"
      :title="'对话列表 - ' + (currentUser?.data.first_name || currentUser?.user_id)"
      width="640px"
    >
      <el-table :data="currentChats" max-height="400">
        <el-table-column prop="id" label="ID" width="140" />
        <el-table-column prop="title" label="标题" />
        <el-table-column prop="type" label="类型" width="120" />
        <el-table-column prop="username" label="用户名" />
      </el-table>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'

const users = ref([])
const dialogVisible = ref(false)
const currentUser = ref(null)
const currentChats = computed(() => currentUser.value?.latest_chats || [])

async function refresh() {
  const { data } = await api.get('/api/users')
  users.value = data
}

function showChats(row) {
  currentUser.value = row
  dialogVisible.value = true
}

onMounted(refresh)
</script>

