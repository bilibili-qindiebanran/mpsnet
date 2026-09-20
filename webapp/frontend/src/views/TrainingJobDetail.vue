<template>
  <div class="page" v-loading="loading">
    <div class="page-head">
      <div>
        <h2 class="page-title">
          训练详情
          <span v-if="job" class="text-secondary" style="font-size: 14px; font-weight: 400">
            #{{ job.id }} · {{ job.name }}
          </span>
        </h2>
        <p class="page-desc">
          <el-tag v-if="job" size="small" effect="plain" style="margin-right: 8px">
            {{ job.model_name }}
          </el-tag>
          <span v-if="job?.test_folder" class="mono">{{ job.test_folder }}</span>
          <span v-if="job"> · {{ job.n_sessions === 2 ? '开集（2 会话）' : '闭集（1 会话）' }}</span>
        </p>
      </div>
      <div class="row-gap">
        <JobStatusTag v-if="job" :status="job.status" />
        <el-button
          v-if="job && ['running', 'pending'].includes(job.status)"
          type="warning"
          @click="stopJob"
        >
          <el-icon><VideoPause /></el-icon>
          <span style="margin-left: 4px">停止</span>
        </el-button>
        <el-button @click="loadAll(true)"><el-icon><Refresh /></el-icon></el-button>
        <el-button @click="$router.push('/training')">返回列表</el-button>
      </div>
    </div>

    <el-alert
      v-if="job?.error"
      class="mb-16"
      type="error"
      show-icon
      :closable="false"
      :title="job.error"
    />

    <!-- 概览 -->
    <div class="card-grid grid-4 mb-16">
      <StatCard label="Best EER" :value="formatMetricPercent(job?.best_eer)" icon="TrendCharts" color="#409eff" />
      <StatCard label="Avg EER" :value="formatMetricPercent(job?.avg_eer)" icon="DataLine" color="#67c23a" />
      <StatCard
        label="已完成折数"
        :value="`${folds.filter((f) => f.eer !== null && f.eer !== undefined).length} / ${progress.n_folds || job?.params?.n_folds || '-'}`"
        icon="Grid"
        color="#e6a23c"
      />
      <StatCard
        label="训练数据"
        :value="trainDataText"
        icon="Coin"
        color="#909399"
      />
    </div>

    <!-- 实时进度 -->
    <el-card class="mb-16" shadow="never">
      <template #header>
        <div class="card-header-row">
          <span class="section-title" style="margin: 0">
            <el-icon><Odometer /></el-icon> 实时进度
            <el-tag v-if="connected" size="small" type="success" effect="light" style="margin-left: 8px">
              SSE 已连接
            </el-tag>
            <el-tag v-else size="small" type="info" effect="light" style="margin-left: 8px">
              {{ isTerminal ? '已结束' : '连接中…' }}
            </el-tag>
          </span>
          <span class="text-secondary" style="font-size: 12px">
            {{ job?.started_at ? `开始于 ${formatTime(job.started_at)}` : '' }}
          </span>
        </div>
      </template>

      <div class="progress-meta">
        <div class="meta-item">
          <div class="meta-label">阶段</div>
          <div class="meta-value">{{ progress.stage || '-' }}</div>
        </div>
        <div class="meta-item">
          <div class="meta-label">当前环节</div>
          <div class="meta-value">{{ phaseText }}</div>
        </div>
        <div class="meta-item">
          <div class="meta-label">折</div>
          <div class="meta-value">
            {{ progress.fold || '-' }} / {{ progress.n_folds || '-' }}
          </div>
        </div>
        <div class="meta-item">
          <div class="meta-label">Epoch</div>
          <div class="meta-value">
            {{ progress.epoch || 0 }} / {{ progress.total_epochs || '-' }}
          </div>
        </div>
      </div>

      <el-progress
        :percentage="epochPercent"
        :stroke-width="16"
        :status="job?.status === 'failed' ? 'exception' : undefined"
        striped
        :striped-flow="job?.status === 'running'"
      />

      <div class="metric-row mt-16">
        <div class="metric-box">
          <span class="metric-name">loss</span>
          <span class="metric-value">{{ formatDecimal(progress.loss, 4) }}</span>
        </div>
        <div class="metric-box">
          <span class="metric-name">accuracy</span>
          <span class="metric-value">{{ formatPercent(progress.accuracy, 2) }}</span>
        </div>
        <div class="metric-box">
          <span class="metric-name">val_loss</span>
          <span class="metric-value">{{ formatDecimal(progress.val_loss, 4) }}</span>
        </div>
        <div class="metric-box">
          <span class="metric-name">val_accuracy</span>
          <span class="metric-value">{{ formatPercent(progress.val_accuracy, 2) }}</span>
        </div>
      </div>

      <el-descriptions v-if="testDataText" :column="2" size="small" border class="mt-16">
        <el-descriptions-item label="测试集">{{ testDataText }}</el-descriptions-item>
        <el-descriptions-item label="输出目录">
          <span class="mono text-break">{{ job?.output_dir }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 训练曲线 -->
    <el-card class="mb-16" shadow="never">
      <template #header>
        <span class="section-title" style="margin: 0"><el-icon><TrendCharts /></el-icon> 训练曲线</span>
      </template>
      <EpochChart :history="history" :height="360" />
    </el-card>

    <div class="card-grid grid-2 mb-16">
      <!-- 各折结果 -->
      <el-card shadow="never">
        <template #header>
          <span class="section-title" style="margin: 0"><el-icon><Grid /></el-icon> 各折评估结果</span>
        </template>
        <FoldEerChart :folds="folds" :height="240" />
        <el-table :data="folds" size="small" class="mt-12">
          <el-table-column prop="fold" label="折" width="60" />
          <el-table-column label="EER" width="100">
            <template #default="{ row }">{{ formatMetricPercent(row.eer) }}</template>
          </el-table-column>
          <el-table-column label="阈值" width="90">
            <template #default="{ row }">{{ formatDecimal(row.threshold, 4) }}</template>
          </el-table-column>
          <el-table-column label="FRR" width="90">
            <template #default="{ row }">{{ formatMetricPercent(row.frr) }}</template>
          </el-table-column>
          <el-table-column label="FAR" width="90">
            <template #default="{ row }">{{ formatMetricPercent(row.far) }}</template>
          </el-table-column>
          <el-table-column prop="n_genuine" label="genuine" width="90" />
          <el-table-column prop="n_impostor" label="impostor" width="90" />
          <template #empty>
            <el-empty description="暂无评估结果" :image-size="60" />
          </template>
        </el-table>
      </el-card>

      <!-- 产物 -->
      <el-card shadow="never">
        <template #header>
          <div class="card-header-row">
            <span class="section-title" style="margin: 0">
              <el-icon><FolderOpened /></el-icon> 训练产物
            </span>
            <span class="text-secondary" style="font-size: 12px">共 {{ artifacts.length }} 个文件</span>
          </div>
        </template>

        <div v-for="group in artifactGroups" :key="group.kind" class="artifact-group">
          <div class="artifact-group-title">
            <el-tag size="small" effect="plain">{{ group.label }}</el-tag>
          </div>
          <div v-for="item in group.items" :key="item.id" class="artifact-row">
            <span class="artifact-name" :title="item.path">{{ item.name }}</span>
            <span class="artifact-size text-secondary">{{ formatBytes(item.size) }}</span>
            <el-button link type="primary" @click="downloadArtifact(item)">下载</el-button>
          </div>
        </div>

        <el-empty v-if="!artifacts.length" description="训练完成后产物会出现在这里" :image-size="70" />
      </el-card>
    </div>

    <!-- DET / MDD -->
    <el-card class="mb-16" shadow="never">
      <template #header>
        <span class="section-title" style="margin: 0">
          <el-icon><Picture /></el-icon> DET 曲线与匹配距离分布（MDD）
        </span>
      </template>

      <el-empty v-if="!foldsWithPlots.length" description="暂无 DET / MDD 图表" :image-size="70" />
      <div v-else class="plot-grid">
        <div v-for="fold in foldsWithPlots" :key="fold.id || fold.fold" class="plot-block">
          <div class="plot-title">第 {{ fold.fold }} 折</div>
          <div class="plot-images">
            <div class="plot-item">
              <div class="plot-label">DET</div>
              <el-image
                v-if="fold.det_path"
                class="plot-img"
                :src="fileUrl(fold.det_path)"
                :preview-src-list="[fileUrl(fold.det_path), fileUrl(fold.mdd_path)].filter(Boolean)"
                fit="contain"
                preview-teleported
                hide-on-click-modal
              />
              <div v-else class="plot-img plot-empty">无图</div>
            </div>
            <div class="plot-item">
              <div class="plot-label">MDD</div>
              <el-image
                v-if="fold.mdd_path"
                class="plot-img"
                :src="fileUrl(fold.mdd_path)"
                :preview-src-list="[fileUrl(fold.mdd_path), fileUrl(fold.det_path)].filter(Boolean)"
                fit="contain"
                preview-teleported
                hide-on-click-modal
              />
              <div v-else class="plot-img plot-empty">无图</div>
            </div>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 日志 -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header-row">
          <span class="section-title" style="margin: 0"><el-icon><Tickets /></el-icon> 运行日志</span>
          <div class="row-gap">
            <el-switch v-model="autoScroll" size="small" active-text="自动滚到底部" />
            <el-button size="small" @click="downloadLog">
              <el-icon><Download /></el-icon>
              <span style="margin-left: 4px">下载完整日志</span>
            </el-button>
          </div>
        </div>
      </template>
      <pre ref="logRef" class="log-view" style="max-height: 380px">{{ logText || '暂无日志' }}</pre>
    </el-card>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  trainApi,
  downloadUrl,
  fileUrl,
  formatBytes,
  formatDecimal,
  formatPercent,
  formatMetricPercent,
  formatTime,
  openEventStream
} from '@/api'
import StatCard from '@/components/StatCard.vue'
import JobStatusTag from '@/components/JobStatusTag.vue'
import EpochChart from '@/components/EpochChart.vue'
import FoldEerChart from '@/components/FoldEerChart.vue'

const route = useRoute()
const jobId = route.params.id

const job = ref(null)
const folds = ref([])
const artifacts = ref([])
const progress = ref({})
const logText = ref('')
const loading = ref(false)
const connected = ref(false)
const autoScroll = ref(true)
const logRef = ref(null)
let stream = null

const ARTIFACT_KIND_LABEL = {
  tflite: 'TFLite 模型',
  keras: 'Keras 模型',
  features: '特征文件 (hdf5)',
  history: '训练历史 (pkl)',
  plot: '图表',
  scores: '分数文件',
  other: '其他'
}

const isTerminal = computed(() => ['success', 'failed', 'stopped'].includes(job.value?.status))
const history = computed(() => progress.value?.history || [])
const epochPercent = computed(() => {
  const total = progress.value?.total_epochs || 0
  const epoch = progress.value?.epoch || 0
  if (!total) return 0
  return Math.min(100, Math.round((epoch / total) * 100))
})

const PHASE_LABEL = { softmax: 'Softmax 预热', adacos: 'AdaCos 微调' }
const phaseText = computed(() => {
  const phase = progress.value?.phase
  if (!phase) return '-'
  return PHASE_LABEL[phase] || phase
})

const trainDataText = computed(() => {
  const data = progress.value?.train_data
  if (!data) return job.value?.params ? '-' : '-'
  return `${data.n_classes ?? '-'} 类 / ${data.n_images ?? '-'} 张`
})

const testDataText = computed(() => {
  const data = progress.value?.test_data
  if (!data) return ''
  return `${data.test_folder || '-'} · ${data.n_samples ?? '-'} 个样本 / ${data.n_classes ?? '-'} 类 / ${
    data.n_sessions ?? '-'
  } 会话`
})

const artifactGroups = computed(() => {
  const map = new Map()
  artifacts.value.forEach((item) => {
    const kind = item.kind || 'other'
    if (!map.has(kind)) map.set(kind, [])
    map.get(kind).push(item)
  })
  const order = ['tflite', 'keras', 'features', 'history', 'plot', 'scores', 'other']
  return order
    .filter((kind) => map.has(kind))
    .map((kind) => ({ kind, label: ARTIFACT_KIND_LABEL[kind] || kind, items: map.get(kind) }))
})

const foldsWithPlots = computed(() =>
  folds.value.filter((fold) => fold.det_path || fold.mdd_path)
)

function applySnapshot(snapshot) {
  if (!snapshot) return
  if (snapshot.status) job.value = { ...(job.value || {}), ...snapshot }
  if (snapshot.progress) progress.value = snapshot.progress
  if (snapshot.best_eer !== undefined) job.value.best_eer = snapshot.best_eer
  if (snapshot.avg_eer !== undefined) job.value.avg_eer = snapshot.avg_eer
  if (snapshot.error !== undefined) job.value.error = snapshot.error
  if (snapshot.log !== undefined) logText.value = snapshot.log || ''
  if (snapshot.progress?.folds) applyProgressFolds(snapshot.progress.folds)
}

function applyProgressFolds(foldMap) {
  const entries = Object.entries(foldMap || {})
  if (!entries.length || folds.value.length) return
  folds.value = entries
    .map(([key, value]) => ({ fold: Number(key), ...value, id: `progress-${key}` }))
    .sort((a, b) => a.fold - b.fold)
}

async function loadAll(manual = false) {
  loading.value = true
  try {
    const detail = await trainApi.job(jobId)
    job.value = detail
    folds.value = detail.folds || []
    artifacts.value = detail.artifacts || []
    progress.value = detail.progress || {}
    if (!isTerminal.value) startStream()
    const logData = await trainApi.log(jobId)
    if (logData.log) logText.value = logData.log
    if (logData.status && job.value) job.value.status = logData.status
    if (manual) ElMessage.success('已刷新')
  } finally {
    loading.value = false
  }
}

function startStream() {
  closeStream()
  stream = openEventStream(trainApi.eventsUrl(jobId), {
    onMessage: (snapshot) => {
      connected.value = true
      applySnapshot(snapshot)
    },
    onError: () => {
      connected.value = false
    },
    onEnd: async () => {
      connected.value = false
      closeStream()
      const detail = await trainApi.job(jobId)
      job.value = detail
      folds.value = detail.folds || []
      artifacts.value = detail.artifacts || []
      progress.value = detail.progress || {}
    }
  })
  connected.value = true
}

function closeStream() {
  stream?.close()
  stream = null
}

async function stopJob() {
  try {
    await ElMessageBox.confirm('确定停止该训练任务？', '停止确认', { type: 'warning' })
  } catch (err) {
    return
  }
  await trainApi.stop(jobId)
  ElMessage.success('已发送停止指令')
  setTimeout(() => loadAll(), 1500)
}

function downloadArtifact(item) {
  window.open(downloadUrl(item.path), '_blank')
}

function downloadLog() {
  const blob = new Blob([logText.value || ''], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `train_job_${jobId}.log`
  link.click()
  URL.revokeObjectURL(url)
}

watch(
  [logText, autoScroll],
  async () => {
    if (!autoScroll.value) return
    await nextTick()
    if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight
  },
  { immediate: true }
)

onMounted(() => {
  loadAll()
})

onUnmounted(() => {
  closeStream()
})
</script>

<style scoped>
.row-gap {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.progress-meta {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.meta-item {
  background: #f7f9fc;
  border-radius: 8px;
  padding: 10px 12px;
}

.meta-label {
  font-size: 12px;
  color: #909399;
}

.meta-value {
  font-size: 15px;
  font-weight: 600;
  margin-top: 2px;
  word-break: break-all;
}

.metric-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.metric-box {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metric-name {
  font-size: 12px;
  color: #909399;
}

.metric-value {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.artifact-group {
  margin-bottom: 12px;
}

.artifact-group-title {
  margin-bottom: 6px;
}

.artifact-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 13px;
}

.artifact-row:hover {
  background: #f7f9fc;
}

.artifact-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.artifact-size {
  font-size: 12px;
  white-space: nowrap;
}

.plot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 16px;
}

.plot-block {
  border: 1px solid #e4e7ed;
  border-radius: 10px;
  padding: 12px;
}

.plot-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}

.plot-images {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.plot-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
  text-align: center;
}

.plot-img {
  width: 100%;
  aspect-ratio: 4 / 3;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #fafafa;
}

.plot-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
  font-size: 12px;
}

@media (max-width: 768px) {
  .progress-meta,
  .metric-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
