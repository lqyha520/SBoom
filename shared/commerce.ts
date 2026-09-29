/** 两端共用订单/退款状态，后台筛选仍保留退款派生状态。 */
export const orderLabels = { created: '待付款', pending: '待确认付款', paid: '已付款', closed: '已关闭', refunded: '已退款' }
export const refundLabels = { requested: '退款待审核', processing: '退款处理中', success: '退款成功', closed: '退款已关闭', abnormal: '退款需人工处理', rejected: '退款未通过' }
export const adminRefundLabels = { requested: '待审核', processing: '处理中', success: refundLabels.success, closed: '已关闭', abnormal: '需人工处理', rejected: '未通过' }
export const orderFilterLabels = { ...orderLabels, refund_requested: refundLabels.requested, refund_processing: refundLabels.processing, refund_abnormal: refundLabels.abnormal, refund_closed: refundLabels.closed }
export type OrderStatus = keyof typeof orderLabels
export type RefundStatus = keyof typeof refundLabels
