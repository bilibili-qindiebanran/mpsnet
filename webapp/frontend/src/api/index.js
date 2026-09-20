import axios from 'axios'
import { ElMessage } from 'element-plus'

const http = axios.create({
  baseURL: '/api',
  timeout: 120000
})

http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    let message = '请求失败，请稍后重试'
    const detail = error?.response?.data?.detail
    if (typeof detail === 'string') {
      message = detail
    } else if (Array.isArray(detail)) {
      message = detail.map((item) => item?.msg || JSON.stringify(item)).join('；')
    } else if (error?.message) {
      message = error.message
    }
    if (error?.response?.status === 403) {
      message = `无权限访问：${message}`
    }
    ElMessage.error(message)
    return Promise.reject(new Error(message))
  }
)

export default http

/* ------------------------------------------------------------------ 工具 */
export function fileUrl(path) {
  if (!path) return ''
  return `/api/system/file?path=${encodeURIComponent(path)}`
}

export function downloadUrl(path) {
  if (!path) return '#'
  return `/api/system/download?path=${encodeURIComponent(path)}`
}

export function formatBytes(size) {
  if (size === null || size === undefined || Number.isNaN(Number(size))) return '-'
  const value = Number(size)
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(2)} MB`
  return `${(value / 1024 / 1024 / 1024).toFixed(2)} GB`
}

export function formatTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

/** 把 0~1 的小数格式化成百分比（用于 Keras 的 accuracy 等）。 */
export function formatPercent(value, digits = 2) {
  if (value === null || value === undefined || value === '') return '-'
  const num = Number(value)
  if (Number.isNaN(num)) return '-'
  return `${(num * 100).toFixed(digits)}%`
}

/**
 * 格式化「本身已经是百分数」的指标（EER / FAR / FRR）。
 * 原项目 train.py 里 far/frr/eer 已经乘以 100，例如 42.936 表示 42.936%。
 */
export function formatMetricPercent(value, digits = 3) {
  if (value === null || value === undefined || value === '') return '-'
  const num = Number(value)
  if (Number.isNaN(num)) return '-'
  return `${num.toFixed(digits)}%`
}

export function formatDecimal(value, digits = 4) {
  if (value === null || value === undefined || value === '') return '-'
  const num = Number(value)
  if (Number.isNaN(num)) return '-'
  return num.toFixed(digits)
}

/**
 * 订阅 SSE。返回一个带 close() 的句柄，务必在 onUnmounted 中调用。
 */
export function openEventStream(url, { onMessage, onEnd, onError } = {}) {
  let source = null
  try {
    source = new EventSource(url)
  } catch (err) {
    onError?.(err)
    return { close: () => {} }
  }

  let closed = false
  let ended = false

  function finish() {
    if (ended) return
    ended = true
    onEnd?.()
  }

  source.onmessage = (event) => {
    if (!event.data) return
    try {
      onMessage?.(JSON.parse(event.data))
    } catch (err) {
      /* 忽略非 JSON 的心跳消息 */
    }
  }

  source.addEventListener('end', () => {
    finish()
    close()
  })

  source.addEventListener('error', (event) => {
    if (event?.data) {
      try {
        onError?.(JSON.parse(event.data))
      } catch (err) {
        onError?.(event)
      }
    }
    // 服务端主动结束或网络中断时，EventSource 会进入 CLOSED，此时静默收尾
    if (source.readyState === EventSource.CLOSED) {
      finish()
    }
  })

  function close() {
    if (closed) return
    closed = true
    source?.close()
  }

  return { close }
}

/* ---------------------------------------------------------------- 系统 */
export const systemApi = {
  health: () => http.get('/health'),
  info: () => http.get('/system/info'),
  stats: () => http.get('/system/stats'),
  browse: (path = '') => http.get('/system/browse', { params: { path } }),
  fileUrl,
  downloadUrl
}

/* ------------------------------------------------------------ ROI 提取 */
export const roiApi = {
  status: () => http.get('/roi/status'),
  build: () => http.post('/roi/build'),
  extract: (payload) => http.post('/roi/extract', payload),
  upload: (payload) => {
    const form = new FormData()
    payload.files.forEach((file) => form.append('files', file))
    form.append('name', payload.name || '上传图片提取')
    form.append('roi_size', String(payload.roi_size ?? 128))
    form.append('save_debug', payload.save_debug ? 'true' : 'false')
    form.append('relative_paths', JSON.stringify(payload.relative_paths || []))
    return http.post('/roi/upload', form)
  },
  jobs: (params = {}) => http.get('/roi/jobs', { params }),
  job: (id) => http.get(`/roi/jobs/${id}`),
  remove: (id) => http.delete(`/roi/jobs/${id}`)
}

/* -------------------------------------------------------------- 数据集 */
export const datasetApi = {
  list: () => http.get('/datasets'),
  suggestions: () => http.get('/datasets/suggestions'),
  scan: (path, imageExtension = '.png') =>
    http.get('/datasets/scan', { params: { path, image_extension: imageExtension } }),
  discover: (path = '') => http.get('/datasets/discover', { params: { path } }),
  create: (payload) => http.post('/datasets', payload),
  detail: (id) => http.get(`/datasets/${id}`),
  update: (id, payload) => http.patch(`/datasets/${id}`, payload),
  refresh: (id) => http.post(`/datasets/${id}/refresh`),
  classes: (id, sampleLimit = 6) =>
    http.get(`/datasets/${id}/classes`, { params: { sample_limit: sampleLimit } }),
  remove: (id) => http.delete(`/datasets/${id}`)
}

/* ---------------------------------------------------------------- 训练 */
export const trainApi = {
  options: () => http.get('/train/options'),
  create: (payload) => http.post('/train/jobs', payload),
  run: (payload) => http.post('/train/run', payload),
  start: (id) => http.post(`/train/jobs/${id}/start`),
  stop: (id) => http.post(`/train/jobs/${id}/stop`),
  jobs: (params = {}) => http.get('/train/jobs', { params }),
  job: (id) => http.get(`/train/jobs/${id}`),
  log: (id) => http.get(`/train/jobs/${id}/log`),
  folds: (id) => http.get(`/train/jobs/${id}/folds`),
  artifacts: (id) => http.get(`/train/jobs/${id}/artifacts`),
  remove: (id, removeFiles = false) =>
    http.delete(`/train/jobs/${id}`, { params: { remove_files: removeFiles } }),
  eventsUrl: (id) => `/api/train/jobs/${id}/events`
}

/* ------------------------------------------------------------ 超参数预设 */
export const presetApi = {
  list: () => http.get('/presets'),
  create: (payload) => http.post('/presets', payload),
  update: (id, payload) => http.put(`/presets/${id}`, payload),
  remove: (id) => http.delete(`/presets/${id}`)
}

/* ----------------------------------------------------------- 识别 / 验证 */
export const recognitionApi = {
  candidates: () => http.get('/recognition/candidates'),
  galleries: () => http.get('/recognition/galleries'),
  createGallery: (payload) => http.post('/recognition/galleries', payload),
  runGallery: (payload) => http.post('/recognition/galleries/run', payload),
  startGallery: (id) => http.post(`/recognition/galleries/${id}/start`),
  gallery: (id) => http.get(`/recognition/galleries/${id}`),
  identities: (id, limit = 200) =>
    http.get(`/recognition/galleries/${id}/identities`, { params: { limit } }),
  identify: (id, file, topk = 5, roiSize = 128) => {
    const form = new FormData()
    form.append('file', file)
    form.append('topk', String(topk))
    form.append('roi_size', String(roiSize))
    return http.post(`/recognition/galleries/${id}/identify`, form)
  },
  verify: (id, file, claim, threshold = null, roiSize = 128) => {
    const form = new FormData()
    form.append('file', file)
    form.append('claim', claim)
    if (threshold !== null && threshold !== undefined && threshold !== '') {
      form.append('threshold', String(threshold))
    }
    form.append('roi_size', String(roiSize))
    return http.post(`/recognition/galleries/${id}/verify`, form)
  },
  removeGallery: (id) => http.delete(`/recognition/galleries/${id}`),
  logs: (params = {}) => http.get('/recognition/logs', { params }),
  eventsUrl: (id) => `/api/recognition/galleries/${id}/events`
}
