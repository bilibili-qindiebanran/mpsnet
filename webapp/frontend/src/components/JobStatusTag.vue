<template>
  <el-tag :type="meta.type" effect="light" size="small" round>
    <el-icon v-if="status === 'running'" class="is-loading spin"><Loading /></el-icon>
    {{ meta.label }}
  </el-tag>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: 'pending' }
})

const MAP = {
  success: { type: 'success', label: '成功' },
  running: { type: 'primary', label: '运行中' },
  pending: { type: 'info', label: '等待中' },
  failed: { type: 'danger', label: '失败' },
  stopped: { type: 'warning', label: '已停止' },
  ready: { type: 'success', label: '就绪' }
}

const meta = computed(() => MAP[props.status] || { type: 'info', label: props.status || '未知' })
</script>

<style scoped>
.spin {
  margin-right: 3px;
  vertical-align: -1px;
}
</style>
