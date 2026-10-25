/** Keep display-name rules consistent across the mini app and administrator form. */
export function registrationAccountError(input: string): string {
  return /^[A-Za-z0-9_-]{2,32}$/.test(input.trim()) ? '' : '账号需为 2-32 位英文字母、数字、下划线或短横线，不能使用中文'
}

export function clipNickname(input: string): string {
  const characters = Array.from(input)
  return characters.length > 32 ? characters.slice(0, 32).join('') : input
}

export function nicknameError(input: string): string {
  if (/[\u0000-\u001f\u007f-\u009f\u2028\u2029\u202a-\u202e\u2066-\u2069]/u.test(input)) return '昵称不能包含换行或控制字符'
  const value = input.trim()
  if (!value) return '昵称不能为空'
  if (Array.from(value).length > 32) return '昵称需为 1-32 个字符'
  return ''
}
