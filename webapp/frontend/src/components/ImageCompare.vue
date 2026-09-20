<template>
  <div class="image-compare" :style="{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }">
    <div v-for="item in normalized" :key="item.key" class="compare-item">
      <div class="compare-label">{{ item.label }}</div>
      <el-image
        v-if="item.path"
        class="compare-img"
        :src="fileUrl(item.path)"
        :preview-src-list="previewList"
        :initial-index="previewList.indexOf(fileUrl(item.path))"
        fit="contain"
        preview-teleported
        hide-on-click-modal
      >
        <template #error>
          <div class="compare-placeholder">
            <el-icon><Picture /></el-icon>
            <span>加载失败</span>
          </div>
        </template>
      </el-image>
      <div v-else class="compare-img compare-placeholder">
        <el-icon><Picture /></el-icon>
        <span>无该调试图</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { fileUrl } from '@/api'

const props = defineProps({
  items: { type: Array, default: () => [] },
  columns: { type: Number, default: 4 }
})

const normalized = computed(() => {
  const list = props.items || []
  return list.map((item, index) => ({
    key: item.key || item.label || index,
    label: item.label || `图 ${index + 1}`,
    path: item.path || ''
  }))
})

const previewList = computed(() =>
  normalized.value.filter((item) => item.path).map((item) => fileUrl(item.path))
)
</script>

<style scoped>
.image-compare {
  display: grid;
  gap: 12px;
}

.compare-item {
  min-width: 0;
}

.compare-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
  text-align: center;
}

.compare-img {
  width: 100%;
  aspect-ratio: 1 / 1;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #fafafa;
  display: block;
}

.compare-placeholder {
  width: 100%;
  aspect-ratio: 1 / 1;
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
  background: #fafafa;
  color: #c0c4cc;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 12px;
}
</style>
