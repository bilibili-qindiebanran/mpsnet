<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">模型训练</h2>
        <p class="page-desc">
          MPSNet 掌静脉模型训练 · Softmax 预热 + AdaCos 微调两阶段交叉验证
        </p>
      </div>
      <div class="row-gap">
        <el-button :loading="listLoading" @click="loadJobs">
          <el-icon><Refresh /></el-icon>
          <span style="margin-left: 4px">刷新</span>
        </el-button>
        <el-button type="primary" @click="drawerVisible = true">
          <el-icon><Plus /></el-icon>
          <span style="margin-left: 4px">新建训练任务</span>
        </el-button>
      </div>
    </div>

    <el-card shadow="never">
      <el-table :data="jobs" v-loading="listLoading">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="任务名" min-width="180" show-overflow-tooltip />
        <el-table-column prop="model_name" label="模型" width="130">
          <template #default="{ row }">
            <el-tag size="small" :type="row.model_name === 'mpsnet' ? 'primary' : 'info'" effect="plain">
              {{ row.model_name }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="dataset_name" label="数据集" width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.dataset_name || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><JobStatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="进度" width="180">
          <template #default="{ row }">
            <el-progress
              v-if="row.status === 'running'"
              :percentage="progressPercent(row)"
              :stroke-width="10"
              striped
              striped-flow
            />
            <span v-else class="text-secondary" style="font-size: 12px">
              {{ row.n_folds_done || 0 }} 折已完成
            </span>
          </template>
        </el-table-column>
        <el-table-column label="Best EER" width="105">
          <template #default="{ row }">{{ formatMetricPercent(row.best_eer) }}</template>
        </el-table-column>
        <el-table-column label="Avg EER" width="105">
          <template #default="{ row }">{{ formatMetricPercent(row.avg_eer) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="165">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/training/${row.id}`)">详情</el-button>
            <el-button
              v-if="['running', 'pending'].includes(row.status)"
              link
              type="warning"
              @click="stopJob(row)"
            >
              停止
            </el-button>
            <el-button link type="danger" @click="removeJob(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="还没有训练任务，点击右上角新建一个吧" :image-size="80" />
        </template>
      </el-table>
    </el-card>

    <!-- 新建任务抽屉 -->
    <el-drawer v-model="drawerVisible" title="新建训练任务" size="720px" :close-on-click-modal="false">
      <el-form :model="form" label-width="120px" v-loading="optionsLoading">
        <el-divider content-position="left">基础配置</el-divider>

        <el-form-item label="任务名称">
          <el-input v-model="form.name" placeholder="留空自动生成" />
        </el-form-item>

        <el-form-item label="数据集" required>
          <el-select v-model="form.dataset_id" placeholder="选择数据集" style="width: 100%" filterable>
            <el-option
              v-for="item in datasets"
              :key="item.id"
              :label="`${item.name}（${item.n_classes} 类 / ${item.n_images} 张）`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="模型" required>
          <el-radio-group v-model="form.model_name">
            <el-radio-button v-for="model in models" :key="model" :value="model">
              {{ model }}
            </el-radio-button>
          </el-radio-group>
          <div class="text-secondary mt-8" style="font-size: 12px">
            MPSNet 为论文主模型（多尺度掌脉特征提取网络），其余为对比基线模型
          </div>
        </el-form-item>

        <el-form-item label="测试会话数">
          <el-radio-group v-model="form.n_sessions">
            <el-radio-button :value="1">1（闭集）</el-radio-button>
            <el-radio-button :value="2">2（开集）</el-radio-button>
          </el-radio-group>
          <div class="text-secondary mt-8" style="font-size: 12px">
            1 = 测试集包含在训练集中；2 = 每类一半样本作测试集
          </div>
        </el-form-item>

        <el-divider content-position="left">训练开关</el-divider>
        <el-form-item label="阶段开关">
          <div class="switch-group">
            <span class="switch-item">
              <el-switch v-model="form.retrain_softmax" />
              <span>重训 Softmax 预热阶段</span>
            </span>
            <span class="switch-item">
              <el-switch v-model="form.retrain_fine_tune" />
              <span>重训 AdaCos 微调阶段</span>
            </span>
            <span class="switch-item">
              <el-switch v-model="form.convert_to_tflite" />
              <span>转换 TFLite 模型</span>
            </span>
          </div>
        </el-form-item>

        <el-divider content-position="left">超参数</el-divider>

        <el-form-item label="快捷预设">
          <el-button size="small" plain @click="applyQuick">快速验证</el-button>
          <el-button size="small" plain @click="applyDefault">论文默认</el-button>
          <el-select
            v-model="selectedPreset"
            size="small"
            placeholder="选择已保存预设"
            style="width: 200px; margin-left: 8px"
            @change="applyPreset"
          >
            <el-option v-for="item in presets" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
          <el-button size="small" text type="primary" @click="saveDialog = true">另存为预设</el-button>
          <el-button
            v-if="selectedPreset"
            size="small"
            text
            type="danger"
            @click="deletePreset"
          >
            删除预设
          </el-button>
        </el-form-item>

        <template v-for="group in optionGroups" :key="group.name">
          <el-divider content-position="left">{{ group.name }}</el-divider>
          <el-row :gutter="16">
            <el-col v-for="item in group.items" :key="item.name" :xs="24" :md="12">
              <el-form-item>
                <template #label>
                  <span class="param-label">
                    {{ item.label }}
                    <el-tooltip v-if="item.help" :content="item.help" placement="top">
                      <el-icon class="help-icon"><QuestionFilled /></el-icon>
                    </el-tooltip>
                  </span>
                </template>

                <el-select
                  v-if="item.choices"
                  v-model="form.params[item.name]"
                  style="width: 100%"
                >
                  <el-option v-for="choice in item.choices" :key="choice" :label="choice" :value="choice" />
                </el-select>

                <el-input-number
                  v-else-if="item.type === 'int'"
                  v-model="form.params[item.name]"
                  :min="item.min"
                  :max="item.max"
                  :step="1"
                  style="width: 100%"
                />

                <el-input-number
                  v-else-if="item.type === 'float'"
                  v-model="form.params[item.name]"
                  :min="item.min"
                  :max="item.max"
                  :step="0.0001"
                  :precision="4"
                  style="width: 100%"
                />

                <el-input v-else v-model="form.params[item.name]" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
        </template>
      </el-form>

      <template #footer>
        <el-button @click="drawerVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">
          <el-icon><VideoPlay /></el-icon>
          <span style="margin-left: 4px">创建并启动训练</span>
        </el-button>
      </template>
    </el-drawer>

    <!-- 另存预设 -->
    <el-dialog v-model="saveDialog" title="另存为超参数预设" width="480px">
      <el-form label-width="90px">
        <el-form-item label="预设名称" required>
          <el-input v-model="presetForm.name" placeholder="例如 快速验证-2折" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="presetForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="saveDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingPreset" @click="savePreset">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSystemStore } from '@/stores/system'
import { trainApi, presetApi, datasetApi, formatMetricPercent, formatTime } from '@/api'
import JobStatusTag from '@/components/JobStatusTag.vue'

const router = useRouter()
const store = useSystemStore()
const { optionSpec, defaultParams, models } = storeToRefs(store)

const jobs = ref([])
const listLoading = ref(false)
const datasets = ref([])
const presets = ref([])
const optionsLoading = ref(false)
const submitting = ref(false)
const drawerVisible = ref(false)
let timer = null

const form = reactive({
  name: '',
  dataset_id: null,
  n_sessions: 1,
  model_name: 'mpsnet',
  params: {},
  retrain_softmax: true,
  retrain_fine_tune: true,
  convert_to_tflite: true
})

const selectedPreset = ref(null)
const saveDialog = ref(false)
const savingPreset = ref(false)
const presetForm = reactive({ name: '', description: '' })

const optionGroups = computed(() => store.optionGroups)

function initParams() {
  const base = { ...(defaultParams.value || {}) }
  form.params = base
}

function progressPercent(row) {
  const progress = row.progress || {}
  const totalEpochs = progress.total_epochs || (row.params?.warmup_epochs || 0) + (row.params?.fine_tune_epochs || 0)
  const nFolds = progress.n_folds || row.params?.n_folds || 1
  const currentFold = progress.fold || 1
  const epoch = progress.epoch || 0
  if (!totalEpochs || !nFolds) return 0
  const done = (currentFold - 1) * totalEpochs + Math.min(epoch, totalEpochs)
  return Math.min(99, Math.round((done / (totalEpochs * nFolds)) * 100))
}

async function loadJobs() {
  listLoading.value = true
  try {
    const data = await trainApi.jobs({ limit: 50 })
    jobs.value = data.items || []
  } finally {
    listLoading.value = false
  }
}

async function loadDatasets() {
  const data = await datasetApi.list()
  datasets.value = data.items || []
}

async function loadPresets() {
  const data = await presetApi.list()
  presets.value = data.items || []
}

function applyQuick() {
  Object.assign(form.params, {
    warmup_epochs: 3,
    fine_tune_epochs: 3,
    n_folds: 2,
    warmup_batch_size: 8,
    fine_tune_batch_size: 8
  })
  selectedPreset.value = null
  ElMessage.success('已应用「快速验证」参数')
}

function applyDefault() {
  form.params = { ...(defaultParams.value || {}) }
  selectedPreset.value = null
  ElMessage.success('已应用「论文默认」参数')
}

function applyPreset(id) {
  const preset = presets.value.find((item) => item.id === id)
  if (!preset) return
  form.params = { ...(defaultParams.value || {}), ...(preset.params || {}) }
  ElMessage.success(`已应用预设「${preset.name}」`)
}

async function savePreset() {
  if (!presetForm.name.trim()) {
    ElMessage.warning('请填写预设名称')
    return
  }
  savingPreset.value = true
  try {
    await presetApi.create({
      name: presetForm.name.trim(),
      description: presetForm.description,
      params: form.params
    })
    ElMessage.success('预设已保存')
    saveDialog.value = false
    presetForm.name = ''
    presetForm.description = ''
    loadPresets()
  } finally {
    savingPreset.value = false
  }
}

async function deletePreset() {
  try {
    await ElMessageBox.confirm('确定删除该预设？', '删除确认', { type: 'warning' })
  } catch (err) {
    return
  }
  await presetApi.remove(selectedPreset.value)
  ElMessage.success('已删除')
  selectedPreset.value = null
  loadPresets()
}

async function submit() {
  if (!form.dataset_id) {
    ElMessage.warning('请选择数据集')
    return
  }
  submitting.value = true
  try {
    const job = await trainApi.run({
      name: form.name.trim(),
      dataset_id: form.dataset_id,
      n_sessions: form.n_sessions,
      model_name: form.model_name,
      params: { ...form.params },
      retrain_softmax: form.retrain_softmax,
      retrain_fine_tune: form.retrain_fine_tune,
      convert_to_tflite: form.convert_to_tflite
    })
    ElMessage.success(`任务 #${job.id} 已启动`)
    drawerVisible.value = false
    router.push(`/training/${job.id}`)
  } finally {
    submitting.value = false
  }
}

async function stopJob(row) {
  try {
    await ElMessageBox.confirm(`确定停止任务 #${row.id}？`, '停止确认', { type: 'warning' })
  } catch (err) {
    return
  }
  await trainApi.stop(row.id)
  ElMessage.success('已发送停止指令')
  loadJobs()
}

async function removeJob(row) {
  let removeFiles = false
  try {
    await ElMessageBox.confirm(`确定删除任务 #${row.id}（${row.name}）？`, '删除确认', {
      type: 'warning',
      distinguishCancelAndClose: true,
      confirmButtonText: '删除记录',
      cancelButtonText: '同时删除文件'
    })
  } catch (action) {
    if (action === 'cancel') removeFiles = true
    else return
  }
  await trainApi.remove(row.id, removeFiles)
  ElMessage.success('已删除')
  loadJobs()
}

async function bootstrap() {
  optionsLoading.value = true
  try {
    await store.loadAll()
    initParams()
    await Promise.all([loadJobs(), loadDatasets(), loadPresets()])
  } finally {
    optionsLoading.value = false
  }
}

onMounted(() => {
  bootstrap()
  timer = setInterval(() => {
    if (jobs.value.some((row) => ['running', 'pending'].includes(row.status))) loadJobs()
  }, 3000)
})

onUnmounted(() => {
  clearInterval(timer)
})
</script>

<style scoped>
.row-gap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.param-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.help-icon {
  color: #c0c4cc;
  cursor: help;
}

.switch-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.switch-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #606266;
}
</style>
