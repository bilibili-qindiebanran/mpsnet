<template>
  <el-card shadow="never" class="stat-card" :class="{ clickable: clickable }" @click="onClick">
    <div class="stat-body">
      <div class="stat-icon" :style="{ background: color + '1a', color }">
        <el-icon :size="20"><component :is="icon" /></el-icon>
      </div>
      <div class="stat-main">
        <div class="stat-label">{{ label }}</div>
        <div class="stat-value" :style="{ color: valueColor || undefined }">{{ value }}</div>
        <div v-if="suffix || hint" class="stat-hint">
          <span v-if="suffix">{{ suffix }}</span>
          <span v-if="hint" class="stat-hint-text">{{ hint }}</span>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup>
const props = defineProps({
  label: { type: String, default: '' },
  value: { type: [String, Number], default: '-' },
  suffix: { type: String, default: '' },
  hint: { type: String, default: '' },
  icon: { type: String, default: 'DataLine' },
  color: { type: String, default: '#409eff' },
  valueColor: { type: String, default: '' },
  clickable: { type: Boolean, default: false }
})

const emit = defineEmits(['click'])

function onClick() {
  if (props.clickable) emit('click')
}
</script>

<style scoped>
.stat-card {
  height: 100%;
}

.stat-card.clickable {
  cursor: pointer;
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}

.stat-card.clickable:hover {
  box-shadow: 0 6px 18px rgba(64, 158, 255, 0.15);
  transform: translateY(-1px);
}

.stat-body {
  display: flex;
  align-items: center;
  gap: 14px;
}

.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-main {
  min-width: 0;
}

.stat-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 2px;
}

.stat-value {
  font-size: 22px;
  font-weight: 600;
  line-height: 1.2;
}

.stat-hint {
  margin-top: 2px;
  font-size: 12px;
  color: #909399;
  display: flex;
  gap: 6px;
}

.stat-hint-text {
  color: #c0c4cc;
}
</style>
