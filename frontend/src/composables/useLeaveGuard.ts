import { ElMessageBox } from 'element-plus'
import { onBeforeUnmount, onMounted } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'

/** 有未保存内容时，路由离开与关闭页面都先确认；导出页/设置页/上传页共用。 */
export function useLeaveGuard(isDirty: () => boolean) {
  function onBeforeUnload(event: BeforeUnloadEvent) {
    if (!isDirty()) return
    event.preventDefault()
    event.returnValue = ''
  }

  onMounted(() => window.addEventListener('beforeunload', onBeforeUnload))
  onBeforeUnmount(() => window.removeEventListener('beforeunload', onBeforeUnload))

  onBeforeRouteLeave(async () => {
    if (!isDirty()) return true
    try {
      await ElMessageBox.confirm('有未保存的修改，确定离开？', '未保存的修改', {
        type: 'warning', confirmButtonText: '离开', cancelButtonText: '留下'
      })
      return true
    } catch {
      return false
    }
  })
}
