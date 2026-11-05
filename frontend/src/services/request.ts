/**
 * HTTP 请求封装（01-auth/frontend.md §8）
 * - 自动附加 Bearer Token
 * - 401 + code 40101 时自动刷新并重放请求（挂起请求等待刷新结果）
 * - 刷新失败跳转登录页
 */
import Taro from '@tarojs/taro'
import { useAuthStore } from '@/stores/authStore'

const BASE_URL = process.env.TARO_APP_API || 'https://api.pingpongai.com/api/v1'

let isRefreshing = false
let pendingRequests: Array<(success: boolean) => void> = []

/** 单飞刷新：并发 401 时仅执行一次 refresh，其余请求挂起等待结果 */
async function refreshAndRetry(): Promise<boolean> {
  if (isRefreshing) {
    return new Promise((resolve) => {
      pendingRequests.push(resolve)
    })
  }
  isRefreshing = true
  const success = await useAuthStore.getState().refreshAccessToken()
  isRefreshing = false
  if (success) {
    pendingRequests.forEach((resolve) => resolve(true))
    pendingRequests = []
  } else {
    // 刷新失败：唤醒挂起请求（等待方收到 false 后跳转登录）
    pendingRequests.forEach((resolve) => resolve(false))
    pendingRequests = []
  }
  return success
}

/** 统一响应封装（后端 app/core/response.py success()：{ code, message, data, timestamp }） */
export interface ApiResponse<T = any> {
  statusCode: number
  data: {
    code: number
    message: string
    data: T
    timestamp: string
  }
}

const request = {
  async get<T = any>(url: string, params?: Record<string, any>): Promise<ApiResponse<T>> {
    return this._request('GET', url, null, params) as Promise<ApiResponse<T>>
  },

  async post<T = any>(url: string, data?: any): Promise<ApiResponse<T>> {
    return this._request('POST', url, data) as Promise<ApiResponse<T>>
  },

  async patch<T = any>(url: string, data?: any): Promise<ApiResponse<T>> {
    return this._request('PATCH', url, data) as Promise<ApiResponse<T>>
  },

  async delete<T = any>(url: string, data?: any): Promise<ApiResponse<T>> {
    return this._request('DELETE', url, data) as Promise<ApiResponse<T>>
  },

  async _request(method: string, url: string, data?: any, params?: any) {
    const token = Taro.getStorageSync('access_token')
    const header: Record<string, string> = {
      'Content-Type': 'application/json',
    }
    if (token) {
      header['Authorization'] = `Bearer ${token}`
    }

    const res = await Taro.request({
      url: `${BASE_URL}${url}`,
      method: method as any,
      data: method === 'GET' ? params : data,
      header,
    })

    // Token 过期 → 自动刷新并重放
    if (res.statusCode === 401 && res.data?.code === 40101) {
      const refreshed = await refreshAndRetry()
      if (refreshed) {
        return this._request(method, url, data, params) // 重试
      }
      // 刷新失败 → 跳转登录
      Taro.reLaunch({ url: '/pages/auth/login/index' })
      throw new Error('Login expired')
    }

    // 权限不足
    if (res.statusCode === 403) {
      throw new Error(res.data?.message || 'Permission denied')
    }

    if (res.statusCode >= 400) {
      throw new Error(res.data?.message || 'Request failed')
    }

    return res
  },
}

export default request
