# 开源首发 Checklist

## 1. 目的

本文档用于指导 Maestro Flow 首次公开发布前的最终检查。

它和 `docs/release_regression_checklist.md` 的区别是：

- `release_regression_checklist.md` 关注运行与回归
- 本文档关注“是否已经达到可对外发布”的整体完成度

## 2. 版本与发布信息

- [ ] `pyproject.toml` 中的版本号正确
- [ ] `CHANGELOG.md` 的 `Unreleased` 内容已整理
- [ ] 首发版本号已确认
- [ ] `LICENSE` 已存在并与项目定位一致

## 3. GitHub 基础文件

- [ ] `README.md` 已对齐当前产品定位
- [ ] `CONTRIBUTING.md` 已存在
- [ ] `CHANGELOG.md` 已存在
- [ ] Issue templates 已存在
- [ ] PR template 已存在

## 4. 文档一致性

- [ ] `docs/MVP_definition.md` 与 README 说法一致
- [ ] `docs/support_matrix.md` 与当前实现状态一致
- [ ] `docs/codex_integration_roadmap.md` 与当前 Codex 接入状态一致
- [ ] `docs/validated_setups.md` 已更新当前已验证组合

## 5. 默认主路径

- [ ] 新用户可以按 README 跑通一次 `run --mock`
- [ ] 新用户可以按 README 跑通一次真实 `run`
- [ ] 新用户知道去哪里看：
  - `summary.md`
  - `run_state.json`
  - `policy_report.json`

## 6. 宿主集成

- [ ] `OpenCode` 接入路径可用
- [ ] `Codex` skills 安装路径可用
- [ ] README 中对各宿主的支持边界描述正确

## 7. 发布前回归

- [ ] `python -m pytest -q`
- [ ] `python -m pytest -q tests/test_release_smoke.py`
- [ ] `docs/release_regression_checklist.md` 中的最小手工回归已通过

## 8. 对外表述

- [ ] 没有把高级执行能力表述成默认主路径
- [ ] 没有把 Codex 表述成“完整深度支持”
- [ ] 没有把“代码内置 provider”误写成“全部实战验证完成”

## 9. 首发建议

如果以上项目都通过，首发建议优先突出：

- CLI 本体
- 可审查的多 Agent 流程
- 可追溯运行产物
- OpenCode 推荐路径
- Codex 默认主路径 skills

不建议在首发时把重点放在：

- 高级执行闭环
- 自动回写主工作区
- 宿主平台深度集成
