# 真实回归样本

## 1. 目的

本文档用于记录 Maestro Flow 已经参与过真实开发过程的项目样本。

和 `docs/release_regression_checklist.md` 不同，这里记录的不是本地 mock 冒烟，而是：

`这套工具链是否在真实项目中留下了可识别的使用痕迹，并且产出了可访问的实际结果。`

## 2. 使用规则

一个项目可以被收录为真实回归样本，至少应满足以下条件中的大部分：

- 仓库内存在 `.maestro/specs`、宿主/agent 约束文件、阶段性清单或过程记录等痕迹
- 能看出 requirement/spec/skill/过程记录与实际交付结果之间的关联
- 存在可访问的部署预览地址，或至少存在明确可运行的项目仓库
- 项目类型对后续回归验证有代表性

## 3. 样本列表

### Sample 01: lunargleamloo-blog

- 项目仓库：
  [xxloocee/lunargleamloo-blog](https://github.com/xxloocee/lunargleamloo-blog)
- 线上预览：
  [lunargleamloo-blog.pages.dev](https://lunargleamloo-blog.pages.dev)
- 项目类型：
  Astro 博客 / 内容站
- 当前状态：
  已验证

#### 观察到的使用痕迹

- 仓库内存在 `.maestro/specs/`
- 仓库内存在项目级 agent 约束文件与流程提示资产
- 存在结构化功能清单：`feature_list.json`
- 存在过程记录：`claude-progress.txt`

#### 代表性验证点

- spec 驱动内容生产流程
- 项目专用 agent 约束页面设计与实现
- 结构化功能清单驱动功能交付
- 交付结果已上线，可通过真实页面验证

#### 对后续回归的价值

这个样本适合帮助验证以下方向是否回退：

- requirement/spec 驱动工作流是否仍然可用
- 项目级宿主/agent 约束接入是否仍然顺畅
- 内容型 / 站点型项目是否仍然适配当前流程
- 宿主接入与产物组织方式是否还适合真实仓库

## 4. 后续补充建议

当前只有一个真实样本时，建议后续优先补齐：

- 一个偏前端交互型项目
- 一个偏工具 / 脚本型项目
- 一个偏代码改造或维护型项目

这样回归样本集会更有代表性。
