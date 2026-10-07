// 检查失败只表示未确认登录态，不能把已有账号状态改成失效。
export function accountStatusAfterCheck(previousStatus, checkStatus) {
  if (checkStatus === 'valid') return '正常'
  if (checkStatus === 'invalid') return '异常'
  if (checkStatus === 'unknown') return previousStatus
  throw new Error('后端返回了未知的账号检查状态')
}
