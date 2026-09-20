<template>
  <div ref="chartRef" class="epoch-chart" :style="{ height: height + 'px' }" />
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  history: { type: Array, default: () => [] },
  height: { type: Number, default: 340 }
})

const chartRef = ref(null)
let chart = null
let observer = null

const PHASE_LABEL = { softmax: 'Softmax 预热', adacos: 'AdaCos 微调' }

function phaseName(phase) {
  return PHASE_LABEL[phase] || phase || ''
}

function buildOption() {
  const list = props.history || []
  const categories = list.map(
    (item) => `${phaseName(item.phase).replace(/\s+/g, '')} F${item.fold ?? '-'} E${item.epoch ?? '-'}`
  )

  const markAreas = []
  let start = 0
  for (let index = 1; index <= list.length; index += 1) {
    const changed = index === list.length || list[index].phase !== list[start].phase
    if (!changed) continue
    const phase = list[start].phase
    markAreas.push([
      {
        xAxis: categories[start],
        name: phaseName(phase),
        itemStyle: {
          color: phase === 'softmax' ? 'rgba(64,158,255,0.06)' : 'rgba(103,194,58,0.08)'
        }
      },
      { xAxis: categories[index - 1] }
    ])
    start = index
  }

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' }
    },
    legend: {
      data: ['loss', 'val_loss', 'accuracy', 'val_accuracy'],
      top: 0
    },
    grid: { left: 56, right: 56, top: 44, bottom: 56 },
    xAxis: {
      type: 'category',
      data: categories,
      boundaryGap: false,
      axisLabel: { hideOverlap: true, fontSize: 11, rotate: 0 },
      axisTick: { show: false }
    },
    yAxis: [
      {
        type: 'value',
        name: 'Loss',
        nameTextStyle: { color: '#909399' },
        axisLabel: { fontSize: 11 },
        splitLine: { lineStyle: { color: '#f0f2f5' } }
      },
      {
        type: 'value',
        name: 'Accuracy',
        nameTextStyle: { color: '#909399' },
        min: 0,
        max: 1,
        axisLabel: { fontSize: 11, formatter: (value) => value.toFixed(1) },
        splitLine: { show: false }
      }
    ],
    dataZoom: [
      { type: 'inside', throttle: 60 },
      { type: 'slider', height: 16, bottom: 8 }
    ],
    series: [
      {
        name: 'loss',
        type: 'line',
        smooth: true,
        showSymbol: false,
        yAxisIndex: 0,
        data: list.map((item) => item.loss ?? null),
        lineStyle: { width: 2, color: '#409eff' },
        itemStyle: { color: '#409eff' },
        markArea: markAreas.length ? { silent: true, data: markAreas } : undefined
      },
      {
        name: 'val_loss',
        type: 'line',
        smooth: true,
        showSymbol: false,
        yAxisIndex: 0,
        data: list.map((item) => item.val_loss ?? null),
        lineStyle: { width: 2, color: '#e6a23c', type: 'dashed' },
        itemStyle: { color: '#e6a23c' }
      },
      {
        name: 'accuracy',
        type: 'line',
        smooth: true,
        showSymbol: false,
        yAxisIndex: 1,
        data: list.map((item) => item.accuracy ?? null),
        lineStyle: { width: 2, color: '#67c23a' },
        itemStyle: { color: '#67c23a' }
      },
      {
        name: 'val_accuracy',
        type: 'line',
        smooth: true,
        showSymbol: false,
        yAxisIndex: 1,
        data: list.map((item) => item.val_accuracy ?? null),
        lineStyle: { width: 2, color: '#f56c6c', type: 'dashed' },
        itemStyle: { color: '#f56c6c' }
      }
    ]
  }
}

function render() {
  if (!chart) return
  if (!props.history?.length) {
    chart.clear()
    chart.setOption({
      title: {
        text: '暂无训练曲线数据',
        left: 'center',
        top: 'middle',
        textStyle: { color: '#c0c4cc', fontSize: 13, fontWeight: 'normal' }
      }
    })
    return
  }
  chart.setOption(buildOption(), true)
}

onMounted(() => {
  chart = echarts.init(chartRef.value)
  render()
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(chartRef.value)
})

watch(() => props.history, render, { deep: true })

onUnmounted(() => {
  observer?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.epoch-chart {
  width: 100%;
}
</style>
