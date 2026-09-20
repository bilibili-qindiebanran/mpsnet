<template>
  <div>
    <div class="gallery-toolbar">
      <el-radio-group v-model="field" size="small">
        <el-radio-button value="roi">ROI</el-radio-button>
        <el-radio-button value="original">原图</el-radio-button>
        <el-radio-button value="binary">二值掩膜</el-radio-button>
        <el-radio-button value="crop">裁剪手部</el-radio-button>
      </el-radio-group>
      <el-input
        v-model="keyword"
        size="small"
        placeholder="按 Palm_ID 过滤"
        clearable
        style="width: 200px"
        :prefix-icon="Search"
      />
      <span class="text-secondary" style="font-size: 12px">
        共 {{ filtered.length }} 张 · {{ groups.length }} 个类别
      </span>
      <el-button size="small" text type="primary" @click="expandAll = !expandAll">
        {{ expandAll ? '全部折叠' : '全部展开' }}
      </el-button>
    </div>

    <el-empty
      v-if="!filtered.length"
      description="暂无结果，任务可能仍在运行或未产生有效 ROI"
    />

    <el-collapse v-else v-model="activeNames">
      <el-collapse-item v-for="group in groups" :key="group.label" :name="group.label">
        <template #title>
          <span class="group-title">
            <el-tag size="small" effect="plain">{{ group.label }}</el-tag>
            <span class="text-secondary">{{ group.items.length }} 张</span>
          </span>
        </template>
        <div class="gallery-grid">
          <div v-for="item in group.items" :key="item.stem + item.label" class="gallery-cell">
            <el-image
              class="thumb"
              :src="fileUrl(item[field])"
              :preview-src-list="group.srcList"
              :initial-index="group.srcList.indexOf(fileUrl(item[field]))"
              fit="cover"
              preview-teleported
              lazy
              hide-on-click-modal
            >
              <template #error>
                <div class="cell-empty">无图</div>
              </template>
            </el-image>
            <div class="cell-name" :title="item.stem">{{ item.stem }}</div>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { fileUrl } from '@/api'

const props = defineProps({
  results: { type: Array, default: () => [] },
  defaultField: { type: String, default: 'roi' }
})

const field = ref(props.defaultField)
const keyword = ref('')
const activeNames = ref([])
const expandAll = ref(true)

const filtered = computed(() => {
  const key = keyword.value.trim().toLowerCase()
  const list = props.results || []
  if (!key) return list
  return list.filter((item) => String(item.label || '').toLowerCase().includes(key))
})

const groups = computed(() => {
  const map = new Map()
  filtered.value.forEach((item) => {
    const label = item.label || '未分组'
    if (!map.has(label)) map.set(label, [])
    map.get(label).push(item)
  })
  return Array.from(map.entries()).map(([label, items]) => {
    const srcList = []
    items.forEach((item) => {
      ;['original', 'roi', 'binary', 'crop'].forEach((key) => {
        if (item[key]) srcList.push(fileUrl(item[key]))
      })
    })
    return { label, items, srcList }
  })
})

async function loadPreviews() {
  activeNames.value = expandedNames()
}

let timer = null

function expandedNames() {
  if (expandAll.value) return groups.value.map((group) => group.label)
  return activeNames.value.filter((name) => groups.value.some((group) => group.label === name))
}

watch(groups, () => {
  clearTimeout(timer)
  timer = setTimeout(loadPreviews, 0)
})

watch(expandAll, () => {
  activeNames.value = expandedNames()
})

loadPreviews()
</script>

<style scoped>
.gallery-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.group-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gallery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
}

.gallery-cell {
  min-width: 0;
}

.gallery-cell :deep(.el-image) {
  display: block;
}

.cell-empty {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
  font-size: 12px;
  background: #fafafa;
}

.cell-name {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
