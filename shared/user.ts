/** 登录用户信息（/api/v1/auth/me、login、register 的响应体），工作台与后台共用 */
export interface UserInfo { id: number; username: string; role: string }
