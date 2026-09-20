<template>
  <div ref="chartRef" class="fold-eer-chart" :style="{ height: height + 'px' }" />
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  folds: { type: Array, default: () => [] },
  height: { type: Number, default: 260 }
})

const chartRef = ref(null)
let chart = null
let observer = null

function render() {
  if (!chart) return
  const list = (props.folds || []).filter((item) => item.eer !== null && item.eer !== undefined)
  if (!list.length) {
    chart.clear()
    chart.setOption({
      title: {
        text: '暂无各折 EER 数据',
        left: 'center',
        top: 'middle',
        textStyle: { color: '#c0c4cc', fontSize: 13, fontWeight: 'normal' }
      }
    })
    return
  }

  const values = list.map((item) => Number(item.eer))
  const best = Math.min(...values)

  chart.setOption(
    {
      tooltip: {
        trigger: 'axis',
        valueFormatter: (value) =>
          value === null || value === undefined ? '-' : `${Number(value).toFixed(3)}%`
      },
      grid: { left: 52, right: 24, top: 24, bottom: 36 },
      xAxis: {
        type: 'category',
        data: list.map((item) => `第 ${item.fold} 折`),
        axisTick: { show: false }
      },
      yAxis: {
        type: 'value',
        name: 'EER',
        axisLabel: { formatter: (value) => `${Number(value).toFixed(2)}%`, fontSize: 11 },
        splitLine: { lineStyle: { color: '#f0f2f5' } }
      },
      series: [
        {
          type: 'bar',
          barMaxWidth: 48,
          data: values.map((value) => ({
            value,
            itemStyle: { color: value === best ? '#67c23a' : '#409eff', borderRadius: [4, 4, 0, 0] }
          })),
          label: {
            show: true,
            position: 'top',
            fontSize: 11,
            formatter: ({ value }) => `${Number(value).toFixed(2)}%`
          },
          markLine: {
            silent: true,
            symbol: 'none',
            lineStyle: { type: 'dashed', color: '#e6a23c' },
            data: [{ yAxis: values.reduce((a, b) => a + b, 0) / values.length, name: '平均 EER' }],
            label: { formatter: '平均', fontSize: 11, color: '#e6a23c' }
          }
        }
      ]
    },
    true
  )
}

onMounted(() => {
  chart = echarts.init(chartRef.value)
  render()
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(chartRef.value)
})

watch(() => props.folds, render, { deep: true })

onUnmounted(() => {
  observer?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.fold-eer-chart {
  width: 100%;
}
</style>
