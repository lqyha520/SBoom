# 监控配置与验收

最低配置为外部 HTTPS 拨测、宿主只读检查、异地备份成功心跳。仓库提供模板，没有安装采集服务、启用定时器或发送真实通知。

## 宿主检查

`scripts/ops_check.py` 检查 `/readyz`、剩余磁盘（至少5 GiB且15%）、备份成功回执（27小时内）、TLS证书（至少14天）和维护失败增量。输出一个JSON对象，全部通过返回0，否则返回1；不发送消息。第一次采集已有非零失败计数也返回1，之后保存基线，进程重启后重新出现的失败仍会报告。直接执行不设 `OPS_STATE_FILE` 则不写任何文件，每次报告当前总数。

1. 建立无登录账号 `learn-coach-monitor`，授予脚本读权限、磁盘统计权限和备份回执目录读权限；不要授予数据库和密钥读取权。
2. 将 `monitor.env.example` 复制到 `/etc/learn-coach/monitor.env`，填域名和路径。`OPS_BACKUP_STATUS` 指向 `release.env` 的 `OPS_STATUS_DIR` 下的 `backup.json`。回执使用独立组，按下述步骤设置。回执仅在restic上传和校验成功后原子替换；手动伪造文件不能作为备份证据。
3. app的9090仅在Compose网络内部开放。Prometheus加入该网络后抓取 `app:9090`；宿主检查需要额外的仅loopback可达转发/代理，或在同一网络内执行脚本。配置前先验证目标，不能把9090直接公开。
4. 以监控账号先手动运行 `python3 /opt/learn-coach/scripts/ops_check.py`，确认JSON中五项结果有效，然后安装service/timer。

```bash
sudo install -m 644 deploy/learn-coach-ops-check.service deploy/learn-coach-ops-check.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now learn-coach-ops-check.timer
systemctl list-timers 'learn-coach-*'
journalctl -u learn-coach-ops-check.service --since today
```

脚本只使用Python标准库（项目统一Python3.12）。StateDirectory保存计数基线，检查失败会显示为systemd失败状态；接入现有日志/告警平台时可消费JSON和退出码。

### 回执最小权限

先确认GID10002未被其他服务占用，已有同名组则核对并使用其实际GID，同步修改 `release.env` 的 `OPS_STATUS_GID`。以下命令仅适用于明确选定的新目录，不要对业务数据目录递归改权限：

```bash
getent group 10002
sudo groupadd --gid 10002 learn-coach-receipts
sudo usermod -a -G learn-coach-receipts learn-coach-monitor
sudo install -d -o 10001 -g learn-coach-receipts -m 2750 /var/lib/learn-coach/ops-status
```

完成一轮真实备份后，以实际监控账号读取新回执；再次备份并原子替换后重复检查。应为 `10001:10002 640`，目录应为2750。重启监控服务使补充组生效。不能授予监控用户 `service.env`、`restic-password` 或数据库访问权限。

```bash
stat -c '%u:%g %a %n' /var/lib/learn-coach/ops-status/backup.json
sudo -u learn-coach-monitor cat /var/lib/learn-coach/ops-status/backup.json
sudo systemctl restart learn-coach-ops-check.service
```

用隔离测试配置验证正常、过期和缺失回执，后两者必须失败；不要改写真实回执时间。共享组验收与异地仓库恢复验收分别登记。

## 外部拨测与采集

在独立于应用宿主的监控平台配置 `https://域名/readyz`，每分钟检查一次，连续两次失败告警，并设置证书到期预警。从公网拨测能够覆盖SSH隧道、反向代理、DNS与TLS链路；只在宿主跑timer无法发现宿主断电和timer漏跑。每日备份与月度恢复分别使用独立的成功心跳，详见 [部署手册](../../docs/deploy.md)。联系人和通知渠道在监控平台单独配置，配置文件不含真实地址。

已有Prometheus可使用 `prometheus.yml.example` 与 `alerts.yml.example`。分别复制为 `/etc/prometheus/prometheus.yml` 和 `/etc/prometheus/learn-coach-alerts.yml`（与rule_files保持一致），先运行 `promtool check config /etc/prometheus/prometheus.yml` 与 `promtool check rules /etc/prometheus/learn-coach-alerts.yml`；再在现有Alertmanager中配置接收人。本仓库没有启动Prometheus/Alertmanager或宣称通知已经送达。

## 投产验收

- 公网readyz正常；在隔离演练中关闭探测端点后告警、恢复后恢复通知。
- 使用临时配置把磁盘阈值调高、备份回执指向不存在文件、TLS阈值调高，检查应返回1。不要修改真实回执或停止生产服务做测试。
- 连续采集维护计数：首次零值通过、出现增量失败、无新失败通过、计数重置后新增失败仍失败。
- 由操作者确认外部平台通知可达、漏心跳会报错，再登记接收人和验收时间。仅存在模板或timer active不等于监控完成。
