---
created: 2026-04-28
source: Agent 自动蒸馏
category: 电商大促
role: strategist
---

# strategist_遇到指定 record_id 的任务时，_96e8e0a1

## 元信息
- 分类：电商大促
- 角色：strategist

## 正文
## 场景
在接到“某护肤品牌-电商大促-record_id: recvi6UYLkxw3U”的策略任务时，用户要求我按标准四步流程执行（读取上游、内部搜索、外部调研、写入策略并建内容排期），但当前会话环境未激活该记录，且我无法直接切换到指定 record_id。

## 策略
我先进行执行前校验，确认是否具备对目标记录调用 read_project/write_project/batch_create_content 的权限与上下文；发现不可直连后，没有跳过流程硬生成策略，而是立即向用户说明阻塞点，并给出两种可落地的补救路径（激活该记录或补充四项关键输入字段）。

## 结果
避免了在缺失真实上游数据和不可写目标记录的情况下产出不可落地方案，确保后续策略制定仍可追溯、可写回、可交付；但本次未进入实质策略产出阶段，属于“流程前置拦截成功、任务待解锁”。

## 经验教训
遇到指定 record_id 的任务时，第一步先做“可执行性检查”：若 1 分钟内不能确认可对该记录执行 read/write/create，就立即暂停并一次性向用户索要最小补充集（brief_analysis、brand_tone、dept_style、project_type 或激活记录），不要先产出策略草案。


> 来源角色: strategist
