<template>
  <div class="page" v-loading="loading">
    <div class="page-head">
      <div>
        <h2 class="page-title">系统设置</h2>
        <p class="page-desc">运行环境、依赖版本、ROI 模块状态与超参数默认值</p>
      </div>
      <el-button :loading="loading" @click="load">
        <el-icon><Refresh /></el-icon>
        <span style="margin-left: 4px">刷新</span>
      </el-button>
    </div>

    <div class="card-grid grid-2">
      <el-card shadow="never">
        <h3 class="section-title"><el-icon><Monitor /></el-icon> 运行环境</h3>
        <dl class="kv-list">
          <dt>项目根目录</dt>
          <dd class="mono">{{ info.project_root || '-' }}</dd>
          <dt>工作区目录</dt>
          <dd class="mono">{{ info.workspace || '-' }}</dd>
          <dt>Keras 代码目录</dt>
          <dd class="mono">{{ info.keras_code_dir || '-' }}</dd>
          <dt>Python 解释器</dt>
          <dd class="mono">{{ info.python_bin || '-' }}</dd>
          <dt>Python 版本</dt>
          <dd>{{ info.python_version || '-' }}</dd>
          <dt>平台</dt>
          <dd>{{ info.platform || '-' }}</dd>
        </dl>
        <el-divider />
        <dl class="kv-list">
          <dt>工作区占用</dt>
          <dd>{{ formatBytes(info.workspace_size) }}</dd>
          <dt>磁盘可用空间</dt>
          <dd>{{ formatBytes(info.disk_free) }}</dd>
          <dt>支持的图片后缀</dt>
          <dd>
            <el-tag
              v-for="ext in info.image_extensions || []"
              :key="ext"
              size="small"
              effect="plain"
              style="margin-right: 6px"
            >
              {{ ext }}
            </el-tag>
          </dd>
        </dl>
      </el-card>

      <div>
        <el-card shadow="never">
          <h3 class="section-title"><el-icon><Box /></el-icon> ROI 提取模块 (palmlib)</h3>
          <dl class="kv-list">
            <dt>可执行文件</dt>
            <dd class="mono">{{ info.palmlib?.path || '-' }}</dd>
            <dt>状态</dt>
            <dd>
              <el-tag :type="palmlibReady ? 'success' : 'warning'" effect="light">
                {{ palmlibReady ? '已就绪' : '未编译' }}
              </el-tag>
            </dd>
          </dl>
          <div class="mt-12">
            <el-button
              type="primary"
              :loading="store.building"
              :disabled="palmlibReady"
              @click="buildModule"
            >
              <el-icon><Tools /></el-icon>
              <span style="margin-left: 4px">{{ palmlibReady ? '无需编译' : '编译模块' }}</span>
            </el-button>
            <span class="text-secondary" style="margin-left: 10px; font-size: 12px">
              执行 ROI_Extraction_Code/build.sh 生成 palmlib
            </span>
          </div>
        </el-card>

        <el-card class="mt-16" shadow="never">
          <h3 class="section-title"><el-icon><Connection /></el-icon> 依赖版本</h3>
          <el-table :data="packageRows" size="small">
            <el-table-column prop="name" label="依赖" />
            <el-table-column prop="version" label="版本">
              <template #default="{ row }">
                <el-tag v-if="row.version" size="small" effect="plain" type="success">
                  {{ row.version }}
                </el-tag>
                <el-tag v-else size="small" effect="plain" type="danger">未安装</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </div>
    </div>

    <el-card class="mt-16" shadow="never">
      <h3 class="section-title"><el-icon><Setting /></el-icon> 支持的模型</h3>
      <div>
        <el-tag
          v-for="model in info.models || []"
          :key="model"
          :type="model === 'mpsnet' ? 'primary' : 'info'"
          effect="plain"
          style="margin: 0 8px 8px 0"
        >
          {{ model }}{{ model === 'mpsnet' ? '（论文主模型）' : '' }}
        </el-tag>
      </div>
    </el-card>

    <el-card class="mt-16" shadow="never">
      <h3 class="section-title"><el-icon><Tickets /></el-icon> 超参数默认值</h3>
      <el-table :data="optionSpec" size="small" border>
        <el-table-column prop="group" label="分组" width="110" />
        <el-table-column prop="name" label="参数名" width="200">
          <template #default="{ row }"><span class="mono">{{ row.name }}</span></template>
        </el-table-column>
        <el-table-column prop="label" label="说明" min-width="180" />
        <el-table-column prop="type" label="类型" width="90" />
        <el-table-column label="默认值" width="130">
          <template #default="{ row }"><span class="mono">{{ row.default }}</span></template>
        </el-table-column>
        <el-table-column label="取值范围 / 可选项" min-width="220">
          <template #default="{ row }">
            <span v-if="row.choices">{{ row.choices.join(' / ') }}</span>
            <span v-else-if="row.min !== undefined || row.max !== undefined">
              {{ row.min ?? '-∞' }} ~ {{ row.max ?? '+∞' }}
            </span>
            <span v-else class="text-secondary">-</span>
          </template>
        </el-table-column>
        <el-table-column label="帮助" min-width="200">
          <template #default="{ row }">
            <span :class="{ 'text-secondary': !row.help }">{{ row.help || '-' }}</span>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="未获取到超参数定义" :image-size="70" />
        </template>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useSystemStore } from '@/stores/system'
import { formatBytes } from '@/api'

const store = useSystemStore()
const info = reactive({})
const loading = ref(false)

const palmlibReady = computed(() => Boolean(info.palmlib?.ready))
const optionSpec = computed(() => info.option_spec || [])
const packageRows = computed(() => {
  const packages = info.packages || {}
  return Object.entries(packages).map(([name, version]) => ({ name, version }))
})

async function load() {
  loading.value = true
  try {
    await store.loadAll(true)
    Object.assign(info, store.info || {})
  } finally {
    loading.value = false
  }
}

async function buildModule() {
  try {
    const result = await store.buildPalmlib()
    ElMessage.success(result.message || '编译成功')
    await store.loadAll(true)
    Object.assign(info, store.info || {})
  } catch (err) {
    /* 错误已由拦截器提示 */
  }
}

onMounted(load)
</script>
